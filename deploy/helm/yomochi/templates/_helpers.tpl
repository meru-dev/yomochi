{{/*
Expand the name of the chart.
*/}}
{{- define "yomochi.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "yomochi.fullname" -}}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "yomochi.labels" -}}
helm.sh/chart: {{ include "yomochi.chart" . }}
{{ include "yomochi.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "yomochi.selectorLabels" -}}
app.kubernetes.io/name: {{ include "yomochi.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Chart label
*/}}
{{- define "yomochi.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common egress rules: DNS + datastore ports + external HTTPS.
Used by api and worker NetworkPolicies.
*/}}
{{- define "yomochi.commonEgressRules" -}}
# DNS — kube-system (CoreDNS / kube-dns)
- to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: kube-system
  ports:
    - protocol: UDP
      port: 53
    - protocol: TCP
      port: 53
# In-cluster datastores (postgres / redis / kafka). Resolved by Service name.
- to:
    - namespaceSelector: {}
  ports:
    - protocol: TCP
      port: {{ .Values.networkPolicy.ports.postgres | default 5432 }}
    - protocol: TCP
      port: {{ .Values.networkPolicy.ports.redis | default 6379 }}
    - protocol: TCP
      port: {{ .Values.networkPolicy.ports.kafka | default 9092 }}
# External HTTPS — OpenAI, OTLP-HTTP. Anything else is denied.
- to:
    - ipBlock:
        cidr: 0.0.0.0/0
        except:
          - 10.0.0.0/8
          - 172.16.0.0/12
          - 192.168.0.0/16
  ports:
    - protocol: TCP
      port: 443
{{- end }}

{{/*
Service account name
*/}}
{{- define "yomochi.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "yomochi.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
