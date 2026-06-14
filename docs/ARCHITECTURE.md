# ARCHITECTURE.md — Yomochi

## 1. Architectural principles

1. **Clean Architecture + DDD + Hexagonal.** Dependencies point inward: domain ← application ← inbound / outbound. Naming follows hexagonal direction-of-flow.
2. **Modular monolith with bounded contexts.** One deployable codebase, six processes. Cross-module communication only via outbox-emitted events or explicitly exported use cases.
3. **Ports and adapters at every real external dependency.** AI providers, email, future FX behind ports. Repositories also behind ports for testability. Ports are `typing.Protocol`, not ABC.
4. **Imperative SQLAlchemy mappings with composite value objects.** Domain entities pure Python; mappings in `outbound/persistence_sqla/mappings/` use `composite(ValueObject, column)`.
5. **Outbox pattern for cross-module integration events.** Postgres transactional outbox → outbox-worker → Kafka → consumers. At-least-once with per-row retry/quarantine. Consumer-side idempotency via Redis.
6. **Async all the way.** FastAPI async routes, async SQLAlchemy, async Redis, async Kafka via FastStream.
7. **Bounded concurrency on every external call.** Per-process semaphores around OpenAI and bcrypt. Circuit breaker on every external service. `OpenAIGateway` enforces: `httpx.Limits` TCP cap, `aiolimiter.AsyncLimiter(rpm)` token bucket, `purgatory.AsyncCircuitBreaker` fast-fail, per-endpoint `httpx.Timeout`, SDK retry/backoff with `Retry-After`.
8. **Test-driven.** Every domain rule and use case covered by unit tests; every adapter by integration tests with testcontainers.
9. **Observable from day one.** structlog (JSON in prod) + OpenTelemetry traces + Prometheus metrics + Loki logs.

## 2. Layer structure

```
app/
├── domain/                # Pure business logic. No outbound/inbound imports.
│   ├── entities/          # User, Transaction, Category, Insight, Alert, RecurringRule
│   ├── value_objects/     # Money, Currency, Email, RawPassword, UserPasswordHash,
│   │                      # IDs, BudgetSummarySnapshot, ParsedReceipt, ReportingPeriod
│   ├── services/          # MonthlyAggregator, BehavioralShiftDetector,
│   │                      # AlertThreshold, PortraitAggregator
│   ├── ports/             # PasswordHasher; per-entity ID generator protocols
│   │                      # (UserIdGenerator, TransactionIdGenerator, CategoryIdGenerator,
│   │                      # InsightIdGenerator, SessionIdGenerator,
│   │                      # PasswordResetTokenIdGenerator, RecurringRuleIdGenerator)
│   └── exceptions/        # Domain-specific errors
│
├── application/           # Use cases. Orchestrates domain + ports.
│   ├── users/             # CreateUser, Login, Logout, ChangePassword,
│   │                      # StartPasswordReset, ConfirmPasswordReset, ListAuditEvents
│   ├── transactions/      # CreateTransaction, UpdateTransaction, DeleteTransaction,
│   │                      # GetTransaction, ListTransactions, ParseTransactionText,
│   │                      # GetBudgetSummary, GetSpendTrend
│   ├── categories/        # CreateCategory, ListCategories
│   ├── insights/          # RequestInsight, ProcessInsight, GetInsight, ListInsights
│   │   ├── embedding_pipeline.py   # Refresh monthly_summary + behavioral_shift chunks
│   │   ├── portrait_pipeline.py    # Refresh user_portrait chunk (4-month aggregation)
│   │   ├── use_cases/
│   │   │   └── _process_insight_steps.py  # TX-bounded steps: claim/assemble/complete/record_failure
│   │   └── ports/         # AIInsightClient, BudgetSummaryReader, ChunkRetriever,
│   │                      # ChunkWriter, DirtyPeriodRepository, PortraitQueue,
│   │                      # TextEmbedder, TransactionReader, AlertWriter, WorkUnit
│   ├── alerts/            # ListAlerts, MarkAlertRead, ClearAlerts
│   ├── chat/              # ChatQuery, ChatStream (SSE), ListChatHistory, ClearChatHistory
│   │   ├── _retrieval.py  # Shared RAG retrieval helper (portrait + monthly + shift chunks)
│   │   └── ports/         # ChatAIClient, ChatHistoryStore, ChatTokenBudget
│   ├── search/            # SearchTransactions
│   ├── recurring/         # CreateRecurringRule, UpdateRecurringRule, DeleteRecurringRule,
│   │                      # GetRecurringRule, ListRecurringRules, FireDueRules
│   ├── ingestion/         # ParseReceipt (receipt OCR, no media retained)
│   └── common/
│       ├── context_quality.py      # assess_quality(chunks) → FULL | PARTIAL | NONE (shared by chat + insights)
│       ├── ai_errors.py            # AITimeoutError, AIUnavailableError, AIInvalidRequestError
│       ├── cursor.py               # base64 keyset cursor helpers
│       ├── outbox_event.py         # OutboxEvent value object
│       ├── exceptions.py           # Cross-cutting application errors
│       └── ports/         # Flusher, IdentityContext, OutboxRepository, EventPublisher,
│                          # TextEmbedder, Clock, MetricsRecorder, UserPlanLookup,
│                          # ChunkRetriever, QuotaCheck, ConsumerIdempotencyStore
│                          # (request-level Idempotency-Key cache lives in the HTTP
│                          # middleware, not here; TX scope = session_factory.begin(),
│                          # no TransactionManager port)
│
├── inbound/               # Adapters that bring requests INTO the application.
│   ├── http/
│   │   ├── controllers/   # Router factories: make_<feature>_router()
│   │   │   ├── auth/, users/, transactions/, categories/, insights/
│   │   │   ├── alerts/, chat/, search/, recurring/, reports/, ingestion/
│   │   ├── auth/          # AuthCookieMiddleware, cookie manager, identity resolver
│   │   ├── middleware/    # RequestId, RateLimit, Idempotency, HttpMetrics, SecurityHeaders
│   │   └── errors/        # Error-envelope translators
│   └── messaging/         # FastStream Kafka consumers
│       ├── transaction_consumer.py  # Marks dirty_periods on TransactionCreated/Updated/Deleted
│       └── insight_consumer.py      # Runs insight pipeline on InsightRequested
│
├── outbound/              # Adapters this app calls OUT to.
│   ├── adapters/
│   │   ├── sqla/          # Repository implementations per bounded context
│   │   ├── redis/         # Sessions, consumer idempotency,
│   │   │                  # rate limiter, search cache, chat token budget,
│   │   │                  # CachedTextEmbedder (decorator, 24h TTL, SHA-256 key)
│   │   ├── kafka/         # KafkaEventPublisher (FastStream producer)
│   │   ├── openai/        # OpenAIInsightClient, OpenAITextEmbedder,
│   │   │                  # OpenAIChatClient, OpenAITransactionTextParser,
│   │   │                  # OpenAIReceiptExtractor, EmbeddingBatcher,
│   │   │                  # pricing.py (per-model $ cost catalog for cost telemetry)
│   │   │   └── _gateway/  # OpenAIGateway: rate limit + circuit breaker + timeout
│   │   ├── image/         # Pillow-based image preprocessor (ingestion)
│   │   └── system/        # SystemClock, Uuid7IdGenerator, BcryptPasswordHasher,
│   │                      # ConfigUploadPolicy, StdoutMailer, NoOpQuotaCheck (worker DI)
│   ├── persistence_sqla/
│   │   ├── mappings/      # Imperative ORM mappings with composite(VO, column)
│   │   ├── alembic/       # Migrations (1 squashed baseline `000000000001_init.py`
│   │   │                  # outbox.trace_context JSONB column included)
│   │   ├── constraint_names.py
│   │   └── registry.py
│   ├── persistence_redis/ # Reserved namespace (currently empty — Redis adapters live
│   │                      # under adapters/redis/)
│   ├── outbox/
│   │   └── poller.py      # Per-row TX: snapshot → lock → publish → SENT | retry/quarantine
│   ├── auth/              # JWT encoder/decoder (n-key rotation window via
│   │                      # JWT_VERIFICATION_KEYS CSV)
│   └── observability/     # otel.py (tracer/meter providers), prometheus.py + exporter,
│                          # prometheus_metrics_recorder.py, propagation.py
│                          # (shared W3C TraceContextTextMapPropagator)
│
└── main/                  # One composition root per process
    ├── config/            # Pydantic settings (shared across all processes)
    ├── logging.py         # structlog config (shared)
    ├── ioc/               # Dishka providers (api + worker variants)
    │   ├── providers.py
    │   └── worker_providers.py
    ├── api/
    │   ├── app_factory.py # make_app(): FastAPI factory
    │   └── asgi.py        # uvicorn entry: app.main.api.asgi:app
    ├── outbox/
    │   └── main.py        # Polls outbox_events, publishes to Kafka
    ├── transaction/
    │   └── main.py        # FastStream consumer: TransactionCreated → dirty_periods
    ├── insight/
    │   ├── main.py        # FastStream consumer: InsightRequested → pipeline
    │   │                  # + background embedding refresh loop (30s)
    │   └── refresh_tick.py
    ├── portrait/
    │   ├── main.py        # Background portrait refresh loop (60s). No Kafka.
    │   └── refresh_tick.py
    └── scheduler/
        └── main.py        # APScheduler: 7 scheduled jobs (see §4)
```

## 3. Bounded contexts

| Context | Owns | Talks to |
|---|---|---|
| `users` | `User`, auth sessions, password reset, audit log | — |
| `transactions` | `Transaction`, `Category`, multi-currency invariants, `BudgetSummary` + `SpendTrend` read models | publishes `TransactionCreated`, `TransactionUpdated`, `TransactionDeleted` |
| `categories` | `Category` hierarchy (system + user), assignability rules | — |
| `insights` | `Insight`, RAG chunk store, embedding pipelines, dirty_periods, `BehavioralShiftDetector`, `PortraitPipeline` | consumes `TransactionCreated/Updated/Deleted` (mark dirty_periods); publishes `InsightRequested`, `InsightCompleted` |
| `alerts` | `Alert`, 90-day retention purge | written by embedding pipeline when behavioural shifts detected |
| `chat` | `ChatTurn`, chat history, streaming AI client, token budget | reads chunk store (portrait + monthly + shift chunks) |
| `search` | semantic search index, query parser | reads from transactions and chunk store |
| `recurring` | `RecurringRule` state machine | scheduler-worker fires due rules → creates `Transaction`s |
| `ingestion` | `ParsedReceiptDraft`, receipt extractor + image preprocessor | one-shot pre-step in front of `POST /v1/transactions`; no media retained |

Cross-context communication happens through outbox-emitted events. No direct imports of one module's domain entities into another.

## 4. Runtime topology

```
                        ┌──────────────┐
              Browser ──▶│  FastAPI api │── HTTPS
                        └──────┬───────┘
                               │ Dishka DI
       ┌───────────────────────┼────────────────────┐
       ▼                       ▼                    ▼
  ┌─────────┐            ┌──────────┐          ┌──────────┐
  │ Postgres│            │  Redis   │          │  Kafka   │
  │+pgvector│            │ sessions │          │  (KRaft) │
  └────┬────┘            │  idemp.  │          └────┬─────┘
       │                 │  ratelim │               │
       │                 │  ratelim │      ┌────────┴──────────┐
       │                 │  cache   │      │                   │
       │                 └──────────┘      ▼                   ▼
       │                            yomochi.             yomochi.
       │                            transactions.v1      insights.v1
       │                                 │                    │
       │   ┌──────────────┐              │                    │
       └───┤ outbox-worker├──────────────┴────────────────────┘
           │ (relay to    │              (publishes to Kafka)
           │  Kafka)      │
           └──────────────┘

  ┌────────────────────────────────────┐
  │ transaction-worker (FastStream)    │
  │ topic: yomochi.transactions.v1     │
  │ → mark dirty_periods(user,yr,mo)   │
  │ No OpenAI. No embedding.           │
  └────────────────────────────────────┘

  ┌────────────────────────────────────────────────────────────┐
  │ insight-worker (FastStream)                                 │
  │ topic: yomochi.insights.v1                                  │
  │ on_insight_event:                                           │
  │   EmbeddingPipeline.refresh() → pgvector RAG → OpenAI chat │
  │   → Insight COMPLETED                                       │
  │ background loop (every 30s):                                │
  │   pop dirty_periods → EmbeddingPipeline.refresh()           │
  │   → monthly_summary + behavioral_shift chunks in pgvector   │
  └────────────────────────────────────────────────────────────┘

  ┌────────────────────────────────────────────────────────────┐
  │ portrait-worker (background only, no Kafka)                 │
  │ loop (every 60s):                                           │
  │   pop portrait_queue → PortraitPipeline.refresh(user_id)   │
  │   → 4-month aggregation → embed → user_portrait chunk       │
  │ On error: requeue user_id (no data loss)                    │
  └────────────────────────────────────────────────────────────┘

  ┌────────────────────────────────────────────────────────────┐
  │ scheduler-worker (APScheduler, UTC)                         │
  │ • 00:05 daily:      FireDueRulesUseCase (recurring txns)    │
  │ • 00:30 monthly:    manage_audit_partitions (create+drop)   │
  │ • 01:00 monthly:    mark all users' prev month → dirty      │
  │ • 03:30 Sunday:     purge alerts older than 90 days         │
  │ • 03:00 Monday:     mark_all_dirty on portrait_queue        │
  │ • 04:00 daily:      purge SENT outbox rows > 7 days         │
  │ • every 10 min:     reaper_tick (requeue orphaned insights)  │
  └────────────────────────────────────────────────────────────┘
```

**Six processes in V1:**

1. **api** — FastAPI HTTP. All user-facing requests. Reads/writes Postgres, publishes outbox events for cross-context facts. Also marks `dirty_periods` synchronously on transaction create/update/delete (in the same DB transaction).
2. **outbox-worker** — Polls `outbox_events` with per-row `FOR UPDATE SKIP LOCKED`. Publishes to Kafka. On publish failure: retries up to `max_retries`, then quarantines the row as `FAILED` (status + `last_error` + `failed_at`). Successful rows in the same batch are unaffected.
3. **transaction-worker** — FastStream Kafka consumer on `yomochi.transactions.v1`. Marks `dirty_periods(user_id, year, month)`. No OpenAI dependency. Idempotent via Redis consumer store.
4. **insight-worker** — FastStream Kafka consumer on `yomochi.insights.v1`. On `InsightRequested`: runs `EmbeddingPipeline.refresh()` → pgvector RAG retrieval → OpenAI chat → `Insight COMPLETED`. Early-fails with `FAILED` status if context_quality = NONE. Background loop (30s): `pop_dirty(limit=20)` → `EmbeddingPipeline.refresh()` per dirty period. Pre-warms chunks between insight requests.
5. **portrait-worker** — Background-only loop (60s). `pop_dirty(limit=10)` from `portrait_queue` → `PortraitPipeline.refresh(user_id)`: reads last 4 months of transactions → aggregates → embeds → upserts `user_portrait` chunk. On per-user error: requeues the user_id. Sized independently from insight-worker so long insight jobs cannot delay portrait refresh.
6. **scheduler-worker** — APScheduler with seven scheduled jobs (see topology diagram above). No Dishka; directly instantiates adapters. `SELECT FOR UPDATE SKIP LOCKED` + unique constraints make multiple replicas safe. `reaper_tick` runs every 10 min: requeues orphaned-`PROCESSING` insights (lease expired, `retry_count < max_retries`) via outbox re-emit; marks exhausted ones `FAILED`. `manage_audit_partitions_job` runs monthly (00:30 UTC) and at startup to pre-create upcoming partitions and detach+drop those older than 12 months. `purge_sent_outbox_job` runs daily (04:00 UTC), batch-deleting SENT outbox rows older than 7 days.

No object storage. Uploaded receipts (ingestion) are extracted and discarded — only the extracted JSON survives.

**V1 single-points-of-failure (accepted, documented):**

- **One Kafka broker, RF=1.** Broker death loses in-flight messages. The outbox table is the source of truth — broker recovery + outbox-worker restart re-publishes pending events. Mitigation in V2: 3-broker cluster, RF=3, `acks=all`.
- **One Postgres instance.** Failures cause full outage. Mitigation: managed Postgres with PITR backups or `cloudnative-pg`. Read replica planned for V2.
- **One Redis instance.** Session loss = forced re-login. Idempotency cache loss = some retries may proceed twice. Acceptable.
- **One replica of each worker.** Crash causes queue lag until restart.

## 5. Key data flows

### 5.1 Manual transaction creation

```
POST /v1/transactions
  1. api: validate Pydantic body → domain Money + Category lookup
  2. api: in one DB transaction:
       - INSERT into transactions
       - UPSERT dirty_periods (user_id, year, month)  ← synchronous, same TX
       - INSERT into outbox_events: "TransactionCreated"
       - INSERT into audit_events
  3. api: cache response in Redis (Idempotency-Key, 24h)
  4. api: respond 201 with TransactionResponse

Async tail (within seconds):
  5. outbox-worker → publishes "TransactionCreated" to Kafka
  6. transaction-worker (on_transaction_event):
       a. check consumer idempotency (Redis)
       b. UPSERT dirty_periods (user_id, year, month)  ← secondary path for
          events from other future sources; idempotent with step 2

Background pre-warm (within 30s):
  7. insight-worker background loop:
       a. pop_dirty(limit=20)
       b. EmbeddingPipeline.refresh(user_id, year, month):
            - read transactions for period from DB
            - aggregate → format_monthly_summary text
            - detect behavioral shifts vs prior 3 months
            - embed text → OpenAI text-embedding-3-small → vector[1536]
            - UPSERT user_financial_chunks (monthly_summary, behavioral_shift)
            - if shifts detected → INSERT user_alerts (idempotent)
```

`Idempotency-Key` header on POST guards against double-submits. `dirty_periods` has a unique constraint on `(user_id, year, month)` — a burst of 30 transactions in a month marks dirty once, triggers one refresh. `EmbeddingPipeline` computes `semantic_hash` of aggregated data; upsert skips re-embedding if hash unchanged.

### 5.2 Insight generation

```
1. Browser POST /v1/insights/requests {period: "monthly"}
2. api: COUNT transactions for (user_id, year, month); check ≥ min_transactions_for_insight
        (read from `InsightWorkerConfig`, default 3, set via env `MIN_TRANSACTIONS_FOR_INSIGHT`);
        create Insight(status=PENDING); emit outbox event "InsightRequested"
3. outbox-worker → Kafka → insight-worker
4. insight-worker (on_insight_event):
   a. mark Insight PROCESSING
   b. EmbeddingPipeline.refresh() for period (idempotent; no-op if chunks fresh)
   c. embed query text → pgvector cosine search → top-3 monthly_summary + top-2 behavioral_shift
   d. ChunkRetriever.get_portrait(user_id) → prepend portrait chunk if present
   e. assess ContextQuality:
        FULL    = has monthly_summary AND behavioral_shift chunks
        PARTIAL = has one of the two
        NONE    = no chunks found → mark Insight FAILED, stop
   f. call OpenAI gpt-4o structured output → {title, description, impact_score}
   g. read BudgetSummarySnapshot (income/expense totals per currency)
   h. mark Insight COMPLETED (title, description, impact_score, context_quality, budget_summary)
5. Browser polls GET /v1/insights/{id} every 2s until status = COMPLETED | FAILED
```

### 5.3 Chat (non-streaming and SSE streaming)

```
POST /v1/chat          → ChatQueryUseCase (returns full answer)
POST /v1/chat/stream   → ChatStreamUseCase (SSE, streams tokens)

Both use the same retrieval path:
  1. Embed user message → query_vector[1536]
  2. ChunkRetriever.search(user_id, query_vector,
         monthly_top_k=2, shift_top_k=2)
  3. ChunkRetriever.get_portrait(user_id) → prepend if present
     → portrait + 2 monthly + 2 shift = up to 5 chunks
  4. assess_quality → FULL | PARTIAL | NONE
  5. ChatHistoryStore.last_n(user_id, n=5) → last 5 turns (chronological)
  6. ChatAIClient.chat(request):
       model: gpt-4o-mini, temperature=0.4, max_tokens=800
       system: financial assistant + chunks as context
       history: last 5 turns
       user: current message
  7. Save 2 ChatTurns: user turn stamped with first clock.now(), assistant turn
     with a second clock.now(); ordering relies on monotone UUIDv7 id tie-break
     (ORDER BY created_at DESC, id DESC). No +1µs arithmetic.
  8. Return {turn_id, answer, context_quality, created_at}

Token budget: Redis-backed ChatTokenBudget enforces per-user per-period cap.
On client disconnect (SSE cut before the usage sentinel arrives), ChatStreamUseCase
records an estimated spend via estimate_tokens (chars // 4 + 1) and logs
chat_stream_usage_estimated, so consumed capacity is never silently skipped.
```

### 5.4 Portrait refresh

```
Weekly (Monday 03:00 UTC), scheduler marks all users dirty in portrait_queue.
portrait-worker loop (every 60s):
  1. pop_dirty(limit=10) from portrait_queue (FOR UPDATE SKIP LOCKED)
  2. for each user_id:
       PortraitPipeline.refresh(user_id):
         a. BudgetSummaryReader.read_history_months(user_id, n=4)
         b. aggregate() per month → MonthlyAggregation[]
         c. PortraitAggregator.format_portrait_text(recent, baselines)
            → spending patterns, income trends, category dynamics
         d. compute_semantic_hash(all_aggs)
         e. TextEmbedder.embed(portrait_text) → vector[1536]
         f. ChunkWriter.upsert(chunk_type="user_portrait",
                period_year=0, period_month=0,  ← one per user
                content=portrait_text, embedding=vector)
  3. On per-user error: requeue → portrait_queue (no data loss)
```

### 5.5 Monthly embedding pre-warm (scheduler)

```
1st of month, 01:00 UTC:
  scheduler-worker: SELECT all user_ids → UPSERT dirty_periods (user_id, prev_year, prev_month)
  → insight-worker background loop picks up within 30s
  → EmbeddingPipeline.refresh() for each user's previous month
  → chunks ready before users request insights
```

### 5.6 Search

```
1. Browser POST /v1/search {query: "how much on cafes in April"}
2. api: LLM query parser (gpt-4o-mini) → {category: "food", period_start: 2026-04-01, …}
3. api: embed query → pgvector search on transaction chunks, filtered by user_id + period
4. api: returns ranked transactions (Redis cache for repeated identical queries)
```

## 6. Dependency injection

Single Dishka container with two scopes:

- `Scope.APP` — singletons: engines, pools, HTTP clients, AI clients, settings.
- `Scope.REQUEST` — per-request: AsyncSession, repositories, use cases.

**Provider sets**, registered at process startup:

- `providers.py` — `HttpProviders`: FastAPI process (full provider set).
- `worker_providers.py` — modular provider sets composed per process:
  - `WorkerInfraProvider` + `WorkerAdaptersBaseProvider` + `WorkerAdaptersInsightProvider` + `InsightPersistenceProvider` + `InsightUseCasesProvider` → insight-worker
  - `WorkerInfraProvider` + `WorkerAdaptersBaseProvider` + `TransactionPersistenceProvider` → transaction-worker
  - `WorkerInfraProvider` + `PortraitAdaptersProvider` → portrait-worker

scheduler-worker does not use Dishka; directly instantiates adapters (no DI overhead for a simple cron process).

## 7. Cross-cutting concerns

| Concern | Approach |
|---|---|
| Auth | HS256 JWT in `HttpOnly; Secure; SameSite=Lax` cookie; Redis-backed sessions (`session:<sid>`); per-user sorted-set index `user_sessions:<uid>` scored by `expires_at` for O(log N) listing + automatic stale-trim. |
| Quota | Per-user per-period limits via `QuotaCheck` port. API process wires `SqlaQuotaCheck` (counts from source tables via half-open `created_at` range predicates, backed by `ix_transactions_user_id_created_at`; atomic with the work-TX — no Redis compensating-refund). Workers wire `NoOpQuotaCheck`. Used by `RequestInsight` and `CreateTransaction`. Limits read from `Plan` value object. |
| Idempotency | `Idempotency-Key` header on every non-idempotent POST; Redis-stored response cache for 24h. Key includes `user_id` to prevent cross-user replay. Distributed `SET NX` lock eliminates TOCTOU race on concurrent duplicate requests. |
| Rate limiting | Redis sliding-window middleware. Per-user, per-endpoint. Chat enforces per-user 20/min in its controller via pipelined Redis `INCR`+`EXPIRE` (closes race that could lock the user out on crash). |
| AI concurrency control | `OpenAIGateway`: `httpx.Limits` TCP cap, `aiolimiter.AsyncLimiter(rpm)` token bucket, `purgatory.AsyncCircuitBreaker` fast-fail, per-endpoint `httpx.Timeout`, SDK retry/backoff. Bounded thread pool for bcrypt (work factor 12, pool size 8). |
| Soft vs hard AI dependency | `OpenAITransactionTextParser` (parse-text) and `OpenAIReceiptExtractor` (ingestion) are **soft** dependencies: on breaker OPEN or failure, frontend leaves form blank. `OpenAIInsightClient` is a **hard** dependency: failures propagate as `INSIGHT_FAILED`. |
| Outbox reliability | Per-row transaction scope in poller. On publish failure: retry up to `max_retries`, then quarantine as `FAILED` (status + `last_error` + `failed_at`). Kafka consumers send unprocessable messages to DLQ topic. |
| Audit log | `audit_events` table populated by domain events. Partitioned by month via Postgres native partitioning. `user_id` nullable with `ON DELETE SET NULL` — account deletion preserves audit history. |
| Vector chunks | `user_financial_chunks` hash-partitioned by `user_id` (16 partitions). HNSW index per partition. Chunk types: `monthly_summary` (one per user·month), `behavioral_shift` (one per user·month when shifts detected), `user_portrait` (one per user, `period_year=0, period_month=0`). |
| Embedding refresh dedup | `dirty_periods` unique constraint on `(user_id, year, month)` — burst marks dirty once. `EmbeddingPipeline` computes `semantic_hash`; upsert skips re-embedding if hash unchanged. N transactions in a month → at most one embedding API call per refresh cycle. |
| Insight quality guard | `ProcessInsightUseCase` classifies context as FULL/PARTIAL/NONE after RAG retrieval. NONE → `Insight.mark_failed()`. AI is never called without user data. |
| AI error classification | `ai_errors.py` defines `AITimeoutError` / `AIUnavailableError` (transient — reaper requeues) vs `AIInvalidRequestError` (terminal — mark failed). Classification is at the `OpenAIGateway` / client layer; use cases never catch raw `httpx` or SDK errors. |
| Chat token budget | `ChatTokenBudget` (Redis) caps total tokens consumed per user per billing period. Enforced in `ChatStreamUseCase` via `StreamUsage` callback. On client disconnect (usage sentinel never arrives), an estimate_tokens fallback (chars // 4 + 1) records an estimated spend so capacity is never silently skipped; logs `chat_stream_usage_estimated`. |
| Errors | Single error envelope: `{error: {code, message, details, request_id}}`. |
| Pagination | Cursor-based for lists; cursor = base64(`(created_at, id)`). |
| Per-user isolation | `user_id` column on every tenant-scoped table. Repositories receive `user_id` from `IdentityContext`. Authorization checked at use-case boundary. |
| Trace propagation across Kafka | W3C carrier injected into `outbox_events.trace_context` JSONB column (`SqlaOutboxRepository.append` uses `TraceContextTextMapPropagator`). `OutboxPoller._process_one` extracts the carrier and attaches it as parent before opening the `outbox.publish` INTERNAL span and invoking `KafkaTelemetryMiddleware` (PRODUCER span). End-to-end one trace: `yomochi-api` → `yomochi-outbox` → Kafka → `yomochi-insight-worker`. Shared propagator in `app/outbound/observability/propagation.py`. |
| Trace ↔ log correlation | `_inject_otel_context` structlog processor reads `trace.get_current_span().get_span_context()` and adds `trace_id` (32 hex), `span_id` (16 hex), `trace_sampled` to every record. Added before redaction so foreign-pre-chain (stdlib loggers: sqlalchemy, uvicorn) also get it. Loki `derivedFields` regex `trace_id=([a-f0-9]+)` → Tempo on the deploy side. |
| OTel sampling | `ParentBased(ALWAYS_ON)` for V1; tail-sampling at the collector for scale. `configure_otel` is idempotent (detects `ProxyTracerProvider`) so repeated init in tests / workers does not double-register. |

## 8. Technology summary

| Layer | Choice |
|---|---|
| HTTP | FastAPI |
| ORM | SQLAlchemy 2 async + imperative mappings + Alembic |
| DI | Dishka |
| DB | Postgres 17 + pgvector |
| Cache / sessions / idempotency / rate limit / token budget / cached embedder | Redis 7 |
| Message bus | Kafka via FastStream |
| AI | OpenAI: `gpt-4o` (insights structured output), `gpt-4o-mini` (chat + parse-text), `text-embedding-3-small` (all embeddings). Upgrade via env var. |
| Object storage | None. Uploaded receipts extracted and discarded. |
| Frontend | Next.js 15 + React 19 + shadcn/ui + TanStack Query |
| Observability | OpenTelemetry + Prometheus + Grafana + Loki + Tempo |
| Deploy | Docker Compose (dev), Helm + Kubernetes (prod) |
| Tests | pytest + pytest-asyncio + testcontainers + Playwright |
| Lint / format | Ruff + mypy strict + import-linter |

## 9. Security & auth

### 9.1 Identity

- Single identity model: `User`. No `Account` / `Organization` / `Workspace`.
- Email unique system-wide, case-insensitive (`UNIQUE` on `users.email_lower`).
- Password: bcrypt work factor 12, run in `BoundedThreadPoolExecutor` (pool size 8 per process) to bound CPU under burst login. `PasswordHasher` port allows future Argon2id / passkey swap.
- Registration enforces `MIN_LENGTH=12` + ≥1 letter + ≥1 digit (NIST SP 800-63B — length is the security knob, not special characters).

### 9.2 Sessions

- Login creates Redis hash `session:<sid>` with `user_id`, `created_at`, `expires_at`, `user_agent`, `ip`. JWT carries only `sid` + `sub`; Redis lookup is the source of truth for revocation.
- Per-user active-sessions index: Redis **sorted set** `user_sessions:<uid>` scored by `expires_at`. `ZREMRANGEBYSCORE 0 NOW()` on every login drops expired members → `ZRANGE` returns only live sessions for `GET /v1/auth/sessions`.
- Cookie: `HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=2592000`. `Secure` only omitted for local HTTP dev.
- Password change / reset revokes all other sessions for the user.

### 9.3 Password reset

- `POST /v1/auth/password-reset/start` always returns 204 (no enumeration).
- Token: 32-byte URL-safe random; SHA-256 hash stored in **Postgres** `password_reset_tokens(token_hash, user_id, expires_at, used_at)` with 30-min TTL. Postgres (not Redis) chosen because a Redis pod restart during managed maintenance would invalidate freshly-sent reset emails.
- Login attempts always run `bcrypt.checkpw` against a dummy hash when the user is not found — prevents user enumeration via timing.

### 9.4 Authorization

- Single rule: every authenticated request resolves `current_user` via `CurrentUserService`; every domain query/command filters / asserts by `user_id == current_user.id`. No RBAC, no per-resource ACL.
- Enforcement points: repository (`user_id` param required), use case (asserts `resource.user_id == current_user.id` → 403 on mismatch), one integration test per repository asserts cross-user isolation.

### 9.5 Indirect-prompt-injection defenses (OWASP LLM01/LLM08)

- **Receipt vision**: OpenAI structured-output (`client.beta.chat.completions.parse` with Pydantic schema) — the model cannot emit free-form text that gets re-injected.
- **Transaction-text parser**: user-controlled categories fenced inside `<CATEGORIES>` / `<TRANSACTION_INPUT>` tags in the user-role message (not interpolated into the system prompt).
- **Chat RAG**: retrieved chunks placed in a `user`-role message inside `<FINANCIAL_DATA>` tags; system prompt explicitly tells the model to treat tag contents as raw data. Chat history `role` whitelisted against `{user, assistant}` on replay.
- **Output heuristic**: assistant answers scanned for `ignore prior instructions`, `you are now`, `<system>` markers and logged silently (no client-visible signal).

### 9.6 Audit log

Append-only `audit_events` table partitioned by month. Written via `AuditLog` port from use cases (not middleware) so the row reflects the actual business outcome. Columns: see `app/outbound/persistence_sqla/alembic/versions/000000000001_init.py` (audit_events table). `user_id` is `ON DELETE SET NULL` — account deletion preserves audit history for compliance.

### 9.7 Secrets

- Local: `.env` (never committed); `.env.example` carries variable names only.
- Prod: External Secrets Operator → cloud KMS / Vault. Sealed-Secrets in the cluster for bootstrap.
- `JWT_SECRET` rotation: **n-key verification window**. App always signs new JWTs with `JWT_SECRET`. At decode time `JwtCodec` tries `(JWT_SECRET, *JWT_VERIFICATION_KEYS)` in order; only `InvalidSignatureError` continues to the next candidate (terminal errors `ExpiredSignature` / `MissingRequiredClaim` / malformed token short-circuit). `JWT_VERIFICATION_KEYS` is a CSV; each entry must be ≥32 bytes. Rotation procedure: append the new key to `JWT_VERIFICATION_KEYS`, deploy, then swap `JWT_SECRET` to the new key and drop the old one from `JWT_VERIFICATION_KEYS` after the access-token TTL has elapsed. Sessions survive rotation because the Redis session row is the source of truth.

### 9.8 Output controls

Never logged: raw or hashed passwords (`RawPassword` has `repr=False`), full JWTs (log `session_id` only), OpenAI prompts containing user data (log model + token counts + outcome), full Pydantic request bodies. `db.statement` in OTel capped to 1 KB, parameter-substituted (no bound values).

## 10. Processes & operations

### 10.1 Process roster

| Process | Entry point | Workload |
|---|---|---|
| `api` | `app.main.api.asgi:app` (uvicorn) | FastAPI HTTP, full Dishka provider set |
| `outbox-worker` | `python -m app.main.outbox.main` | Polls `outbox_events` → Kafka. `SELECT FOR UPDATE SKIP LOCKED`, per-row TX, retry/quarantine |
| `transaction-worker` | `python -m app.main.transaction.main` | FastStream consumer on `yomochi.transactions.v1`. No OpenAI dependency |
| `insight-worker` | `python -m app.main.insight.main` | FastStream consumer on `yomochi.insights.v1` + 30s dirty-period embedding refresh loop (per-period TX, concurrent via `Semaphore(4)`). Claims insight with `processing_deadline = now() + 15 min` (lease). |
| `portrait-worker` | `python -m app.main.portrait.main` | 60s portrait refresh loop, concurrent via `Semaphore(3)`. No Kafka |
| `scheduler-worker` | `python -m app.main.scheduler.main` | APScheduler — 7 scheduled jobs (see §4). No Dishka |

Same Docker image, different `command:` per Helm Deployment (childprofile pattern). All Kafka consumers + outbox/portrait support horizontal scaling (Kafka rebalance / `SKIP LOCKED`).

### 10.2 Resource limits (Helm requests)

| Worker | CPU | Memory | Notes |
|---|---|---|---|
| `outbox-worker` | 0.25 | 256M | Lightweight DB poll + Kafka publish |
| `transaction-worker` | 0.25 | 192M | No OpenAI, no embedding |
| `insight-worker` | 0.5 | 384M | Heaviest — chat + embedding |
| `portrait-worker` | 0.25 | 256M | Embedding only |
| `scheduler-worker` | 0.25 | 256M | Idle 99% of the time |

### 10.3 Failure modes runbook

| Symptom | Cause | Fix |
|---|---|---|
| Insights stuck at QUEUED | outbox-worker not running | restart outbox-worker |
| Insights stuck at PROCESSING | insight-worker crashed mid-pipeline | reaper_tick auto-requeues when `processing_deadline` expires (≤15 min); exhausted rows (≥`reaper_max_retries`) flip to FAILED automatically |
| High Kafka lag on `yomochi.transactions.v1` | transaction-worker slow | scale replicas |
| High Kafka lag on `yomochi.insights.v1` | OpenAI degraded or slow | check rate-limit headers + breaker state |
| `dirty_periods` growing | refresh loop stuck or OpenAI down | restart insight-worker |
| Portraits stale | portrait-worker crashed | restart portrait-worker |

### 10.4 Connection pool

Explicit pool config: `pool_size=10, max_overflow=5, recycle=1800s`. Two hot paths explicitly release DB connections before long-running external calls: `ProcessInsightUseCase` (claim TX → no-TX OpenAI calls → save TX), and `ChatQueryUseCase` / `ChatStreamUseCase` (TX1 short read via `ChatWorkUnitFactory` — context + history fetched and committed → embedder + LLM call with no session held → TX2 fresh short write to persist turns).

## 11. Out-of-scope architectural choices

- Microservices split — rejected. Modular monolith is the unit of deploy.
- GraphQL / gRPC — rejected. REST + OpenAPI 3.1.
- WebSocket — chat streaming uses SSE. Push notifications deferred.
- Read replicas, sharding, Citus — deferred. Single Postgres handles current scale.
- Saga / Event Sourcing / standalone CQRS — outbox + state machines suffice.
- Local AI — deferred (memory: `project_p4a_deferred.md`). OpenAI on hot path; Ollama/local embedder behind same ports later.
- Per-transaction embedding chunks — rejected. Monthly aggregation is sufficient granularity.
- Celery — rejected. Incompatible with async SQLAlchemy.
- Arq migration — **CANCELLED** (memory: `project_v3_arq_migration.md`). Arq stays in maintenance-only evaluation; APScheduler retained for V1. K8s `CronJob` per schedule is the migration path considered for V2 (see `features.md` F8).
