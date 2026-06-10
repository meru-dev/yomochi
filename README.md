# Yomochi

> AI-powered expense understanding. Log multi-currency spending, ask questions in natural language, get monthly insights that compare today against your own past. No bank integrations. No data sale. Single user, by design.

## What it is

You log transactions manually (or snap a receipt — there's a narrowed OCR endpoint), and Yomochi holds your full multi-currency history. Once a month you ask for an **Insight**: a short AI-written summary that compares this month's spending against your own past and surfaces patterns you'd otherwise miss. You ask follow-up questions in natural language and chat back-and-forth, using your own data as context.

## Features

| | |
|---|---|
| **AI Memory over your own history** | `monthly_summary` + `behavioral_shift` + `user_portrait` chunks in pgvector. Insights, Chat, and Search all read from the same memory layer. |
| **Conversational Q&A with RAG** | Ask *"When did my spending on cafés start increasing?"* — answer comes from your data, not generic advice. SSE streaming. |
| **Multi-currency, honest reporting** | JPY, USD, EUR shown side-by-side without fake unified totals. |
| **`ContextQuality` badge** | Explicit signal when the AI has too little data to be confident — `FULL` / `PARTIAL` / `NONE`. |
| **Receipt parse without retention** | Snap a photo → get a pre-filled form → no bytes survive the request. |
| **Behavioural-shift alerts** | Passive notifications when spending patterns shift ≥30% MoM. Zero extra AI cost — fed by the same pipeline. |

## Architecture

Strict **Clean Architecture + DDD + Hexagonal**, organised as a **modular monolith** with bounded contexts. One image, multiple processes.

```mermaid
flowchart LR
    Browser((Browser))
    Browser -->|HTTPS| API[FastAPI<br/>api process]

    API --> PG[(Postgres 17<br/>+ pgvector)]
    API --> RED[(Redis 7<br/>sessions · idemp · rate-limit)]
    API -->|writes outbox_events| PG
    API -.->|sync vision call| OAI((OpenAI))

    PG --> OBW[outbox-worker<br/>relay]
    OBW -->|publish| KAF[(Kafka<br/>KRaft single-broker)]

    KAF --> TXW[transaction-worker<br/>mark dirty periods]
    KAF --> INW[insight-worker<br/>RAG + AI chat]

    TXW --> PG
    INW --> PG
    INW -.-> OAI

    PG --> PRW[portrait-worker<br/>weekly user portrait]
    PRW -.-> OAI

    SCH[scheduler-worker<br/>recurring · purge · pre-warm] --> PG
```

Six processes, one Docker image. The outbox pattern gives at-least-once cross-context delivery with consumer-side idempotency. Full topology, data flows, and TX scoping in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/DATA_FLOW.md`](docs/DATA_FLOW.md).

### Layer structure

```
app/
├── domain/         # Pure entities, value objects, ports — no I/O
├── application/    # Use cases + ports (per bounded context)
├── inbound/        # FastAPI controllers + FastStream Kafka consumers
├── outbound/       # SQLA, Redis, Kafka, OpenAI, system adapters
└── main/           # Composition root per process
```

Dependencies always point inward. Ports are `typing.Protocol`. Bounded-context boundaries enforced by `import-linter`.

### Bounded contexts

| Context | Owns | Talks to |
|---|---|---|
| `users` | Identity, auth sessions, audit log | — |
| `transactions` | `Transaction` + `Category` + multi-currency invariants + report read models | publishes `TransactionCreated/Updated/Deleted` |
| `categories` | System + user categories, 2-level hierarchy | — |
| `insights` | `Insight`, RAG chunk store, AI client, `BehavioralShiftDetector` | consumes `Transaction*`, publishes `InsightCompleted` |
| `search` | pg_trgm + cached natural-language search | reads from `transactions` + chunk store |
| `chat` | SSE streaming Q&A, conversation history | reads chunks + history |
| `alerts` | In-app behavioural-shift notifications | written by insights pipeline |
| `recurring` | User-defined recurring rules | scheduler-worker fires → creates transactions |
| `ingestion` | Receipt OCR endpoint (no media persistence) | one-shot pre-step before `POST /v1/transactions` |

## Tech stack

| Layer | Choice |
|---|---|
| **HTTP** | FastAPI (async) |
| **DI** | Dishka — `APP` / `REQUEST` scopes, per-process providers |
| **ORM** | SQLAlchemy 2 async + imperative mappings + Alembic |
| **Database** | PostgreSQL 17 + pgvector (HNSW per hash partition) |
| **Cache · sessions · idempotency · rate-limit** | Redis 7 |
| **Message bus** | Kafka KRaft via FastStream |
| **AI** | OpenAI: `gpt-4o-mini` (chat + parse-text), `gpt-4o` (insights + receipt vision), `text-embedding-3-small` (RAG) |
| **Auth** | Self-hosted: HS256 JWT in httpOnly cookie + Redis session store + bcrypt with bounded thread pool |
| **Observability** | OpenTelemetry + Prometheus + Grafana + Loki + Tempo |
| **Resilience** | Per-process semaphores + `aiolimiter` (RPM) + `purgatory` async circuit breakers around every external call |
| **Tests** | pytest + pytest-asyncio + testcontainers + Playwright + golden-set evals |
| **Lint / format / type** | Ruff + mypy strict + import-linter + deptry + slotscheck |
| **Frontend** | Next.js 15 (App Router, Turbopack) + React 19 + shadcn/ui + TanStack Query + Zustand + react-hook-form + zod |
| **Deploy** | Docker Compose (dev) · k3s + Helm chart (single-node VPS or multi-node prod) |

## Quick start

Prereqs: Docker + Docker Compose v2 + `make`.

### 1. Configure `.env`

```bash
cp .env.example .env
```

Required secrets to fill in:

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | Your OpenAI API key (`sk-...`) |
| `JWT_SECRET` | Min 32-byte secret — generate with `openssl rand -hex 32` |
| `POSTGRES_PASSWORD` | Postgres password (any string for local dev) |
| `GF_SECURITY_ADMIN_PASSWORD` | Grafana admin password |

All other values in `.env.example` work out of the box for local Docker Compose.

### 2. Run

```bash
make dev
```

Brings up: postgres+pgvector, redis, kafka, api, outbox-worker, transaction-worker, insight-worker, portrait-worker, scheduler-worker, web (Next.js), and the LGTM observability stack.

| Service | URL |
|---|---|
| Web UI | http://localhost:3000 |
| API / OpenAPI | http://localhost:8000/docs |
| Grafana | http://localhost:3001 |

> Insights are produced asynchronously via Kafka. Without `outbox-worker` + `insight-worker` running, `POST /v1/insights/requests` returns `QUEUED` and never advances. `make dev` starts all workers.


### 3. Seed demo data (optional)

Populates a ready-to-use demo persona with 90 days of realistic transactions directly into the DB — no running API needed.

```bash
DATABASE_URL=postgresql://yomochi:changeme@localhost:5432/yomochi \
  make seed-demo
```

## Project structure

```
yomochi/
├── app/                  # Python backend (Clean Arch + DDD + Hexagonal)
├── deploy/               # k3s bootstrap · Helm chart · observability configs
├── docs/                 # ARCHITECTURE.md, DATA_FLOW.md, DEPLOY.md, OBSERVABILITY.md
├── scripts/              # Dev utilities (evals bootstrap, DR drill, metrics publisher)
├── tests/
│   ├── unit/             # Mirrors app/ — pure tests, no I/O
│   ├── integration/      # testcontainers (real postgres + redis)
│   ├── evals/            # Golden-set AI evals
│   ├── smoke/            # Post-deploy probes
│   ├── migrations/       # Alembic stairway test
│   ├── fakes/            # In-memory port implementations
│   └── fixtures/         # Shared test data (personas, …)
└── web/                  # Next.js 15 frontend
    └── src/features/<feature>/{components,hooks}/
```

## Documentation

| Document | Purpose |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Layers, bounded contexts, runtime topology, security, ops |
| [`docs/DATA_FLOW.md`](docs/DATA_FLOW.md) | End-to-end data flows for the main user journeys |
