#!/bin/bash
# k3s single-node bootstrap for Hetzner CX32 / similar VPS (Ubuntu 24.04).
#
# What this gets you:
#   - k3s (control-plane + worker on the same node), traefik disabled, servicelb disabled
#   - ingress-nginx (chart uses nginx annotations — keeps values-prod.yaml portable)
#   - cert-manager + letsencrypt-prod ClusterIssuer
#   - kube-prometheus-stack (Prometheus Operator + Grafana + Alertmanager)
#   - sealed-secrets controller
#   - 2 GB swap (CX32 RAM is tight with kafka + LGTM-equivalents)
#   - ufw locked to 22/80/443
#
# Idempotent. Re-run after upgrades. Reads CLUSTER_DOMAIN + ACME_EMAIL from env.
#
# Usage:
#   sudo CLUSTER_DOMAIN=yomochi.example.com ACME_EMAIL=ops@example.com bash deploy/k3s/bootstrap.sh

set -euo pipefail

CLUSTER_DOMAIN="${CLUSTER_DOMAIN:-}"
ACME_EMAIL="${ACME_EMAIL:-}"
K3S_VERSION="${K3S_VERSION:-v1.31.3+k3s1}"

log() { echo "[k3s-bootstrap] $*"; }
die() { echo "[k3s-bootstrap] ERROR: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "must run as root (sudo bash $0)"
[[ -n "$CLUSTER_DOMAIN" ]] || die "CLUSTER_DOMAIN env var required (e.g. yomochi.example.com)"
[[ -n "$ACME_EMAIL"     ]] || die "ACME_EMAIL env var required (Let's Encrypt contact)"

# ---------------------------------------------------------------------------
# 1. Host prep — swap, sysctl, base packages, firewall
# ---------------------------------------------------------------------------
if [[ ! -f /swapfile ]]; then
  log "creating 2G swapfile"
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

cat > /etc/sysctl.d/99-yomochi.conf <<'EOF'
vm.swappiness = 10
vm.max_map_count = 262144
net.core.somaxconn = 1024
net.ipv4.tcp_max_syn_backlog = 1024
# k8s networking
net.bridge.bridge-nf-call-iptables = 1
net.ipv4.ip_forward = 1
EOF
sysctl --system >/dev/null

apt-get update -y
apt-get install -y ca-certificates curl gnupg git ufw fail2ban jq

ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
# k3s uses 6443 (API) — restrict to your IP via `ufw allow from <ip> to any port 6443`
ufw --force enable

# ---------------------------------------------------------------------------
# 2. k3s install — disable traefik (we use nginx) + servicelb (single node, no LB)
# ---------------------------------------------------------------------------
if ! command -v k3s >/dev/null 2>&1; then
  log "installing k3s ${K3S_VERSION}"
  curl -sfL https://get.k3s.io | \
    INSTALL_K3S_VERSION="$K3S_VERSION" \
    INSTALL_K3S_EXEC="server --disable traefik --disable servicelb --write-kubeconfig-mode=600" \
    sh -
fi

export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
mkdir -p /root/.kube
ln -sf /etc/rancher/k3s/k3s.yaml /root/.kube/config

# Wait for node ready
log "waiting for k3s node ready"
until kubectl get node | grep -q ' Ready '; do sleep 2; done

# ---------------------------------------------------------------------------
# 3. helm install
# ---------------------------------------------------------------------------
if ! command -v helm >/dev/null 2>&1; then
  log "installing helm"
  curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx 2>/dev/null || true
helm repo add jetstack https://charts.jetstack.io 2>/dev/null || true
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts 2>/dev/null || true
helm repo add sealed-secrets https://bitnami-labs.github.io/sealed-secrets 2>/dev/null || true
helm repo add cnpg https://cloudnative-pg.github.io/charts 2>/dev/null || true
helm repo add bitnami https://charts.bitnami.com/bitnami 2>/dev/null || true
helm repo update

# ---------------------------------------------------------------------------
# 4. ingress-nginx — terminates 80/443 on host network (single-node, no LB)
# ---------------------------------------------------------------------------
log "installing ingress-nginx"
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace \
  --set controller.kind=DaemonSet \
  --set controller.hostNetwork=true \
  --set controller.hostPort.enabled=true \
  --set controller.service.type=ClusterIP \
  --set controller.publishService.enabled=false \
  --set controller.metrics.enabled=true \
  --set controller.metrics.serviceMonitor.enabled=true \
  --set controller.metrics.serviceMonitor.additionalLabels.release=kube-prometheus-stack \
  --wait

# ---------------------------------------------------------------------------
# 5. cert-manager + Let's Encrypt ClusterIssuer
# ---------------------------------------------------------------------------
log "installing cert-manager"
helm upgrade --install cert-manager jetstack/cert-manager \
  --namespace cert-manager --create-namespace \
  --set crds.enabled=true \
  --wait

cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: ${ACME_EMAIL}
    privateKeySecretRef:
      name: letsencrypt-prod-account-key
    solvers:
      - http01:
          ingress:
            class: nginx
EOF

# ---------------------------------------------------------------------------
# 6. kube-prometheus-stack — Prometheus Operator + Grafana + Alertmanager
# ---------------------------------------------------------------------------
log "installing kube-prometheus-stack"
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  --set prometheus.prometheusSpec.retention=15d \
  --set prometheus.prometheusSpec.resources.requests.memory=512Mi \
  --set prometheus.prometheusSpec.resources.limits.memory=1Gi \
  --set grafana.adminPassword="$(openssl rand -hex 16)" \
  --set grafana.persistence.enabled=true \
  --set grafana.persistence.size=2Gi \
  --set alertmanager.enabled=false \
  --wait

# Label namespace so worker NetworkPolicy ingress rule (monitoring.scrapeNamespace=monitoring) matches.
kubectl label namespace monitoring kubernetes.io/metadata.name=monitoring --overwrite

# ---------------------------------------------------------------------------
# 7. sealed-secrets controller
# ---------------------------------------------------------------------------
log "installing sealed-secrets controller"
helm upgrade --install sealed-secrets sealed-secrets/sealed-secrets \
  --namespace sealed-secrets --create-namespace \
  --wait

# ---------------------------------------------------------------------------
# 8. CloudNativePG operator — manages Postgres clusters declaratively
# ---------------------------------------------------------------------------
log "installing cloudnative-pg operator"
helm upgrade --install cnpg-operator cnpg/cloudnative-pg \
  --namespace cnpg-system --create-namespace \
  --wait

# ---------------------------------------------------------------------------
# 9. yomochi namespace + in-cluster data stores
#    Pre-create the namespace so Redis/Kafka install before the app chart.
#    The app chart uses --create-namespace too, so this is idempotent.
# ---------------------------------------------------------------------------
kubectl create namespace yomochi --dry-run=client -o yaml | kubectl apply -f -
kubectl label namespace yomochi kubernetes.io/metadata.name=yomochi --overwrite

log "installing redis (standalone, no auth — NetworkPolicy-protected)"
helm upgrade --install yomochi-redis bitnami/redis \
  --namespace yomochi \
  --set architecture=standalone \
  --set auth.enabled=false \
  --set master.resources.requests.cpu=50m \
  --set master.resources.requests.memory=64Mi \
  --set master.resources.limits.cpu=300m \
  --set master.resources.limits.memory=256Mi \
  --set master.persistence.size=2Gi \
  --wait

log "installing kafka (KRaft combined mode, single node)"
helm upgrade --install yomochi-kafka bitnami/kafka \
  --namespace yomochi \
  --set controller.replicaCount=1 \
  --set broker.replicaCount=0 \
  --set listeners.client.protocol=PLAINTEXT \
  --set controller.resources.requests.cpu=200m \
  --set controller.resources.requests.memory=256Mi \
  --set controller.resources.limits.cpu=500m \
  --set controller.resources.limits.memory=768Mi \
  --set controller.persistence.size=5Gi \
  --wait

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
log "done."
log ""
log "Cluster ready. Next steps:"
log "  1. Point DNS A record for ${CLUSTER_DOMAIN} at this VPS IP."
log "  2. Create yomochi secrets via sealed-secrets (see deploy/sealed-secrets/README.md)."
log "  3. Install yomochi:"
log ""
log "       helm upgrade --install yomochi deploy/helm/yomochi \\"
log "         --namespace yomochi --create-namespace \\"
log "         --values deploy/helm/yomochi/values-vps.yaml \\"
log "         --set ingress.hosts[0].host=${CLUSTER_DOMAIN} \\"
log "         --set ingress.tls[0].hosts[0]=${CLUSTER_DOMAIN} \\"
log "         --atomic --wait --timeout 10m"
log ""
log "  Grafana admin password:"
log "    kubectl -n monitoring get secret kube-prometheus-stack-grafana \\"
log "      -o jsonpath='{.data.admin-password}' | base64 -d; echo"
log "  Grafana port-forward:"
log "    kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80"
