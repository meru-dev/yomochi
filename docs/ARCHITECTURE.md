# ARCHITECTURE.md — Yomochi

## 1. Architectural principles

1. **Clean Architecture + DDD + Hexagonal.** Dependencies point inward: domain ← application ← inbound / outbound. Naming follows hexagonal direction-of-flow.
2. **Modular monolith with bounded contexts.** One deployable codebase, four processes. Cross-module communication only via outbox-emitted events or explicitly exported use cases.
3. **Ports and adapters at every real external dependency.** AI providers, email, future FX behind ports. Repositories also behind ports for testability. Ports are `typing.Protocol`, not ABC.
4. **Imperative SQLAlchemy mappings with composite value objects.** Domain entities pure Python; mappings in `outbound/persistence_sqla/mappings/` use `composite(ValueObject, column)`.
5. **Outbox pattern for cross-module integration events.** Postgres transactional outbox → outbox-worker → Kafka → consumers. At-least-once with per-row retry/quarantine. Consumer-side idempotency via Redis.
6. **Async all the way.** FastAPI async routes, async SQLAlchemy, async Redis, async Kafka via FastStream.
7. **Bounded concurrency on every external call.** Per-process semaphores around OpenAI and bcrypt. Circuit breaker on every external service. `OpenAIGateway` enforces: `httpx.Limits` TCP cap, **per-endpoint-class `aiolimiter.AsyncLimiter` token buckets** (`chat`/`vision`/`parse` — a vision/parse burst can't starve interactive chat) with a bounded waiter queue (fast-reject on overflow), **per-endpoint `purgatory.AsyncCircuitBreaker`** fast-fail, per-endpoint `httpx.Timeout`, SDK retry/backoff with `Retry-After`.
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
│   │                      # AlertThreshold
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
│   │   ├── use_cases/
│   │   │   └── _process_insight_steps.py  # TX-bounded steps: claim/assemble/complete/record_failure
│   │   └── ports/         # AIInsightClient, BudgetSummaryReader, TransactionReader,
│   │                      # AlertWriter, WorkUnit
│   ├── alerts/            # ListAlerts, MarkAlertRead, ClearAlerts
│   ├── chat/              # ChatQuery, ChatStream (SSE), ListChatHistory, ClearChatHistory
│   │   └── ports/         # ChatAIClient, ChatHistoryStore, ChatTokenBudget, ChatTools
│   ├── search/            # SearchTransactions
│   ├── recurring/         # CreateRecurringRule, UpdateRecurringRule, DeleteRecurringRule,
│   │                      # GetRecurringRule, ListRecurringRules, FireDueRules
│   ├── ingestion/         # ParseReceipt (receipt OCR, no media retained)
│   └── common/
│       ├── ai_errors.py            # AITimeoutError, AIUnavailableError, AIInvalidRequestError
│       ├── cursor.py               # base64 keyset cursor helpers
│       ├── outbox_event.py         # OutboxEvent value object
│       ├── exceptions.py           # Cross-cutting application errors
│       └── ports/         # Flusher, IdentityContext, OutboxRepository, EventPublisher,
│                          # Clock, MetricsRecorder, UserPlanLookup,
│                          # QuotaCheck, ConsumerIdempotencyStore
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
│       └── insight_consumer.py      # Runs insight pipeline on InsightRequested
│
├── outbound/              # Adapters this app calls OUT to.
│   ├── adapters/
│   │   ├── sqla/          # Repository implementations per bounded context
│   │   ├── redis/         # Sessions, consumer idempotency,
│   │   │                  # rate limiter, search cache, chat token budget
│   │   ├── kafka/         # KafkaEventPublisher (FastStream producer)
│   │   ├── openai/        # OpenAIInsightClient, OpenAIChatClient,
│   │   │                  # OpenAITransactionTextParser, OpenAIReceiptExtractor,
│   │   │                  # pricing.py (per-model $ cost catalog for cost telemetry)
│   │   │   └── _gateway/  # OpenAIGateway: per-endpoint rate-limit buckets + breaker + timeout
│   │   ├── insight_fallback/ # FallbackAIInsightClient + DeterministicInsightClient (F2)
│   │   ├── image/         # Pillow-based image preprocessor (ingestion)
│   │   └── system/        # SystemClock, Uuid7IdGenerator, BcryptPasswordHasher,
│   │                      # ConfigUploadPolicy, StdoutMailer, NoOpQuotaCheck (worker DI)
│   ├── persistence_sqla/
│   │   ├── mappings/      # Imperative ORM mappings with composite(VO, column)
│   │   ├── alembic/       # Migrations: `000000000001_init.py` (squashed baseline)
│   │   │                  # `000000000002_drop_vector_store.py` (drops user_financial_chunks,
│   │   │                  # dirty_periods, portrait_queue + vector extension)
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
    ├── insight/
    │   └── main.py        # FastStream consumer: InsightRequested → deterministic pipeline
    └── scheduler/
        └── main.py        # APScheduler: 6 scheduled jobs (see §4)
```

## 3. Bounded contexts

| Context | Owns | Talks to |
|---|---|---|
| `users` | `User`, auth sessions, password reset, audit log | — |
| `transactions` | `Transaction`, `Category`, multi-currency invariants, `BudgetSummary` + `SpendTrend` read models | no outbox events emitted for transactions |
| `categories` | `Category` hierarchy (system + user), assignability rules | — |
| `insights` | `Insight`, deterministic aggregator, `BehavioralShiftDetector` | publishes `InsightRequested`, `InsightCompleted` |
| `alerts` | `Alert`, 90-day retention purge | written by `detect_shift_alerts_job` (scheduler) |
| `chat` | `ChatTurn`, chat history, streaming AI client, token budget, `ChatTools` | reads from `transactions` via function-calling tools |
| `search` | pg_trgm fuzzy search, query parser | reads from `transactions` |
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
  │+pg_trgm │            │ sessions │          │  (KRaft) │
  └────┬────┘            │  idemp.  │          └────┬─────┘
       │                 │  ratelim │               │
       │                 │  ratelim │      ┌────────┴──────────┐
       │                 │  cache   │      │                   │
       │                 └──────────┘      ▼
       │                            yomochi.insights.v1
       │                                        │
       │   ┌──────────────┐                    │
       └───┤ outbox-worker├────────────────────┘
           │ (relay to    │   (publishes to Kafka)
           │  Kafka)      │
           └──────────────┘

  ┌────────────────────────────────────────────────────────────┐
  │ insight-worker (FastStream)                                 │
  │ topic: yomochi.insights.v1                                  │
  │ on_insight_event:                                           │
  │   read month aggregate + prior 3 months (deterministic)    │
  │   MonthlyAggregator + BehavioralShiftDetector               │
  │   → OpenAI gpt-4o structured output → Insight COMPLETED     │
  └────────────────────────────────────────────────────────────┘

  ┌────────────────────────────────────────────────────────────┐
  │ scheduler-worker (APScheduler, UTC)                         │
  │ • 00:05 daily:      FireDueRulesUseCase (recurring txns)    │
  │ • 00:30 monthly:    manage_audit_partitions (create+drop)   │
  │ • 02:00 daily:      detect_shift_alerts_job (BehavioralShiftDetector per user) │
  │ • 03:30 Sunday:     purge alerts older than 90 days         │
  │ • 04:00 daily:      purge SENT outbox rows > 7 days         │
  │ • every 10 min:     reaper_tick (requeue orphaned insights)  │
  └────────────────────────────────────────────────────────────┘
```

**Four processes in V1:**

1. **api** — FastAPI HTTP. All user-facing requests. Reads/writes Postgres, publishes outbox events for cross-context facts.
2. **outbox-worker** — Polls `outbox_events` with per-row `FOR UPDATE SKIP LOCKED`. Publishes to Kafka. On publish failure: retries up to `max_retries`, then quarantines the row as `FAILED` (status + `last_error` + `failed_at`). Successful rows in the same batch are unaffected.
3. **insight-worker** — FastStream Kafka consumer on `yomochi.insights.v1`. On `InsightRequested`: reads period's month aggregate and prior 3 months via `BudgetSummaryReader`, runs `MonthlyAggregator` + `BehavioralShiftDetector`, formats deterministic context, calls OpenAI gpt-4o structured output → `Insight COMPLETED`. Early-fails with `FAILED` status if context_quality = NONE (no transaction rows for the period).
4. **scheduler-worker** — APScheduler with six scheduled jobs (see topology diagram above). No Dishka; directly instantiates adapters. `SELECT FOR UPDATE SKIP LOCKED` + unique constraints make multiple replicas safe. `detect_shift_alerts_job` runs daily (02:00 UTC): for each recently-active user, reads monthly aggregates via `BudgetSummaryReader`, runs `BehavioralShiftDetector`, and writes alerts idempotently. `reaper_tick` runs every 10 min: requeues orphaned-`PROCESSING` insights (lease expired, `retry_count < max_retries`) via outbox re-emit; marks exhausted ones `FAILED`. `manage_audit_partitions_job` runs monthly (00:30 UTC) and at startup to pre-create upcoming partitions and detach+drop those older than 12 months. `purge_sent_outbox_job` runs daily (04:00 UTC), batch-deleting SENT outbox rows older than 7 days.

No object storage. Uploaded receipts (ingestion) are extracted and discarded — only the extracted JSON survives.

**V1 single-points-of-failure (accepted, documented):**

- **One Kafka broker, RF=1.** Broker death loses in-flight messages. The outbox table is the source of truth — broker recovery + outbox-worker restart re-publishes pending events. Mitigation in V2: 3-broker cluster, RF=3, `acks=all`.
- **One Postgres instance.** Failures cause full outage. Mitigation: managed Postgres with PITR backups or `cloudnative-pg`. Read replica planned for V2.
- **One Redis instance.** Session loss = forced re-login. Idempotency cache loss = some retries may proceed twice. Acceptable.
- **One replica of each worker.** Crash causes queue lag until restart.

### 4.1 Delivery guarantees (per consumer)

Every Kafka consumer is **at-least-once**: a message is committed only after the
handler succeeds, so a crash or handler exception causes redelivery. Handlers
must therefore be **idempotent**. The end-to-end chain is at-least-once on both
hops — outbox-worker re-publishes un-acked rows, and consumers re-process
un-committed messages.

**insight-worker** (`yomochi.insights.v1`, group `insight-worker`,
`app/inbound/messaging/insight_consumer.py`):

| Concern | Mechanism |
|---|---|
| Ack semantics | `ack_policy=AckPolicy.NACK_ON_ERROR` (`app/main/insight/main.py`). Commit on success; on handler exception, seek back → redelivery. |
| Idempotency | Redis key `consumer:idempotency:{event_id}` (`RedisConsumerIdempotencyStore`). `is_processed` short-circuits duplicates before any work; `mark_processed` (TTL `consumer_idempotency_ttl_seconds`, default 24 h) is set on success **and** on DLQ park. |
| Bounded redelivery | Redis counter `consumer:failures:{event_id}` (`INCR`+`EXPIRE`). Each failed attempt increments it; the handler `raise`s (→ NACK → redelivery) while `failures < consumer_max_retries` (default 3). |
| Terminal park (DLQ) | On the `consumer_max_retries`-th failure the original body + `x_error` is published to the DLQ topic (`KAFKA_TOPIC_DLQ`, default `yomochi.dlq.v1`), the event is marked processed, `consumer_dlq_event` metric is recorded, and the handler returns (no further redelivery). |
| Already-terminal events | `InsightAlreadyTerminalError` / `InsightNotFoundError` (re-delivery of a durably-done insight) are treated as success — marked processed, never DLQ'd. |

Because the DLQ park sets the idempotency key, **a naïve replay of a parked event
is skipped as a duplicate** until that key's TTL expires. Replaying therefore
requires clearing the Redis idempotency/failure keys first — see the
DLQ drain/replay runbook (§10.5). The guarantee is covered by
the kill-test `tests/integration/messaging/test_insight_dlq.py`.

## 5. Key data flows

### 5.1 Manual transaction creation

```
POST /v1/transactions
  1. api: validate Pydantic body → domain Money + Category lookup
  2. api: in one DB transaction:
       - INSERT into transactions
       - INSERT into audit_events
  3. api: cache response in Redis (Idempotency-Key, 24h)
  4. api: respond 201 with TransactionResponse
```

`Idempotency-Key` header on POST guards against double-submits. There is no async Kafka path for transaction events.

### 5.2 Insight generation

```
1. Browser POST /v1/insights/requests {period: "monthly"}
2. api: COUNT transactions for (user_id, year, month); check ≥ min_transactions_for_insight
        (read from `InsightWorkerConfig`, default 3, set via env `MIN_TRANSACTIONS_FOR_INSIGHT`);
        create Insight(status=PENDING); emit outbox event "InsightRequested"
3. outbox-worker → Kafka → insight-worker
4. insight-worker (on_insight_event):
   a. mark Insight PROCESSING
   b. BudgetSummaryReader.read_month(user_id, year, month) → current month aggregate
      BudgetSummaryReader.read_history_months(user_id, year, month, n=3) → prior 3 months
   c. MonthlyAggregator.aggregate() per month → MonthlyAggregation[]
   d. BehavioralShiftDetector.detect(current, history) → shifts (if any)
   e. assess ContextQuality (deterministic, no vector search):
        NONE    = no transaction rows for the period → mark Insight FAILED, stop
                  (AI is never called without user data)
        FULL    = rows present AND behavioral shifts detected
        PARTIAL = rows present AND no shifts detected
   f. format deterministic context:
        monthly_summary_text  (from MonthlyAggregator)
        behavioral_shift_text (from BehavioralShiftDetector, if shifts present)
   g. AIInsightClient.generate → OpenAI gpt-4o structured output → {title, description, impact_score}
      (system: financial analyst persona; context: monthly summary + shift text).
      Wrapped by FallbackAIInsightClient (F2): on any OpenAI gateway failure
      (rate-limit / timeout / 5xx / breaker OPEN) it degrades to a vendor-free
      deterministic templated summary instead of failing the insight.
   h. read BudgetSummarySnapshot (income/expense totals per currency)
   i. mark Insight COMPLETED (title, description, impact_score, context_quality, budget_summary)
5. Browser receives the result via SSE (F4): GET /v1/insights/{id}/stream pushes status
   transitions + the terminal COMPLETED/FAILED payload the instant it lands (then closes;
   ~2-min timeout sentinel). A low-frequency GET /v1/insights/{id} poll remains as a backstop
   when SSE is unavailable. (Generation is out-of-band in the worker, so the stream watches
   the row, not the LLM tokens.)
```

### 5.3 Chat (non-streaming and SSE streaming)

Chat answers a question by running a bounded OpenAI function-calling loop over a typed
`ChatTools` query library — there is no embedding / pgvector retrieval on the chat path.

```
POST /v1/chat          → ChatQueryUseCase (returns full answer)
POST /v1/chat/stream   → ChatStreamUseCase (SSE, streams tokens)

Both use the same tools loop:
  1. ChatHistoryStore.last_n(user_id, n=5) → last 5 turns (chronological)
  2. ChatAIClient.chat_with_tools / stream_with_tools:
       model: gpt-4o-mini, temperature=0.4, max_tokens=800
       system: financial assistant that fetches data via tools
       history: last 5 turns
       user: current message
       tools: the typed ChatTools schemas (bounded iteration cap)
  3. Save 2 ChatTurns: user turn stamped with first clock.now(), assistant turn
     with a second clock.now(); ordering relies on monotone UUIDv7 id tie-break
     (ORDER BY created_at DESC, id DESC). No +1µs arithmetic.
  4. Return {turn_id, answer, context_quality, created_at}
     context_quality is always FULL (the field is retained for response-contract
     stability; chat no longer has a partial/none retrieval state).

Token budget: Redis-backed ChatTokenBudget enforces per-user per-period cap.
On client disconnect (SSE cut before the usage sentinel arrives), ChatStreamUseCase
records an estimated spend via estimate_tokens_from_text (chars // 4 + 1) and logs
chat_stream_usage_estimated, so consumed capacity is never silently skipped.
```

Six user-scoped tools are available: `get_month_summary`, `get_category_trend`,
`get_spend_window`, `get_user_profile`, `search_transactions`, and `list_categories`.
`search_transactions` performs a fuzzy text match backed by the existing pg_trgm GIN
indexes on `transactions.merchant` and `transactions.notes` — no vector search. The loop
has a bounded iteration cap to prevent run-away tool calls. Tool results are treated as
untrusted data (OWASP LLM01 treatment). `ChatTools` opens a fresh short-lived DB session
per tool call and releases it before the next OpenAI round-trip, preserving the §10.4
connection-release invariant — no DB connection is held across OpenAI calls.

### 5.4 Behavioral-shift alert detection (scheduler)

```
Daily, 02:00 UTC — detect_shift_alerts_job (scheduler-worker):
  for each recently-active user:
    1. BudgetSummaryReader.read_month(user_id, year, month) → current aggregate
    2. BudgetSummaryReader.read_history_months(user_id, year, month, n=3) → prior 3 months
    3. BehavioralShiftDetector.detect(current, history) → shifts (if any)
    4. AlertWriter.write_shift_alerts(user_id, year, month, shifts)
           └── For each shift where alert_threshold.is_alertworthy():
               INSERT INTO user_alerts (type, subtype, title, body, ...)
               ON CONFLICT (user_id, subtype, period_year, period_month)
               DO NOTHING  ← idempotent
```

### 5.5 Search

```
1. Browser POST /v1/search {query: "how much on cafes in April"}
2. api: LLM query parser (gpt-4o-mini) → {category: "food", period_start: 2026-04-01, …}
3. api: SearchTransactions use case — pg_trgm fuzzy match on merchant/notes,
        filtered by user_id, category, period
4. api: returns ranked transactions (Redis cache for repeated identical queries)
```

## 6. Dependency injection

Single Dishka container with two scopes:

- `Scope.APP` — singletons: engines, pools, HTTP clients, AI clients, settings.
- `Scope.REQUEST` — per-request: AsyncSession, repositories, use cases.

**Provider sets**, registered at process startup:

- `providers.py` — `HttpProviders`: FastAPI process (full provider set).
- `worker_providers.py` — modular provider sets composed per process:
  - `WorkerInfraProvider` + `WorkerAdaptersBaseProvider` + `WorkerAdaptersInsightProvider` + `InsightPersistenceProvider` + `InsightUseCasesProvider` → insight-worker (handles the Kafka insight consumer)

scheduler-worker does not use Dishka; directly instantiates adapters (no DI overhead for a simple cron process).

## 7. Cross-cutting concerns

| Concern | Approach |
|---|---|
| Auth | HS256 JWT in `HttpOnly; Secure; SameSite=Lax` cookie; Redis-backed sessions (`session:<sid>`); per-user sorted-set index `user_sessions:<uid>` scored by `expires_at` for O(log N) listing + automatic stale-trim. |
| Quota | Per-user per-period limits via `QuotaCheck` port. API process wires `SqlaQuotaCheck` (counts from source tables via half-open `created_at` range predicates, backed by `ix_transactions_user_id_created_at`; atomic with the work-TX — no Redis compensating-refund). Workers wire `NoOpQuotaCheck`. Used by `RequestInsight` and `CreateTransaction`. Limits read from `Plan` value object. |
| Idempotency | `Idempotency-Key` header on every non-idempotent POST; Redis-stored response cache for 24h. Key includes `user_id` to prevent cross-user replay. Distributed `SET NX` lock eliminates TOCTOU race on concurrent duplicate requests. |
| Rate limiting | Redis sliding-window middleware. Per-user, per-endpoint. Chat enforces per-user 20/min in its controller via pipelined Redis `INCR`+`EXPIRE` (closes race that could lock the user out on crash). |
| AI concurrency control | `OpenAIGateway`: `httpx.Limits` TCP cap; **per-endpoint-class token buckets** (`aiolimiter.AsyncLimiter` for `chat`/`vision`/`parse`, partitioning the account RPM so one class can't starve another) with a **bounded waiter queue** (`openai_limiter_max_queue` → fast-reject `AIRateLimitedError` + `openai_limiter_rejected_total` on overflow, no unbounded pile-up); **per-endpoint `purgatory.AsyncCircuitBreaker`** fast-fail; per-endpoint `httpx.Timeout`; SDK retry/backoff. Bounded thread pool for bcrypt (work factor 12, pool size 8). (F19) |
| Prompt caching (F1) | OpenAI prompt-caching exploited: stable system prefix first, volatile data last; `prompt_cache_key=user_id` pins a user's requests to the same backend so their prefix stays hot. `openai_cached_tokens_total{endpoint,model}` tracks cache hits; `estimate_cost` discounts cached tokens to 50% so `openai_cost_usd_total` reflects real spend. |
| Soft vs hard AI dependency | `OpenAITransactionTextParser` (parse-text) and `OpenAIReceiptExtractor` (ingestion) are **soft** dependencies: on breaker OPEN or failure, frontend leaves form blank. `OpenAIInsightClient` (insights) is wrapped by **`FallbackAIInsightClient`** (F2): on any gateway failure (rate-limit / timeout / 5xx / breaker OPEN) it **degrades to a vendor-free deterministic templated summary** (`DeterministicInsightClient`) instead of failing the insight — `insight_fallback_total{reason}`. Only an unexpected non-gateway error still lands in the DLQ. (Real second-vendor failover = Anthropic is deferred → F32.) |
| Outbox reliability | Per-row transaction scope in poller. On publish failure: retry up to `max_retries`, then quarantine as `FAILED` (status + `last_error` + `failed_at`). **FAILED is replayable, not terminal** (F17): a dedicated `OutboxAdmin` port (`SqlaOutboxAdmin`, segregated from the append-only request-path `OutboxRepository`) + the `scripts/replay_outbox.py` admin CLI flip FAILED→PENDING (retry_count reset) with filters / min-age backoff / dry-run — see the outbox-replay runbook (§10.6). Kafka consumers send unprocessable messages to a DLQ topic (DLQ-replay runbook §10.5). |
| Audit log | `audit_events` table populated by domain events. Partitioned by month via Postgres native partitioning. `user_id` nullable with `ON DELETE SET NULL` — account deletion preserves audit history. |
| Insight quality guard | `ProcessInsightUseCase` classifies context quality deterministically, without vector search: NONE = no transaction rows for the period (AI never called, insight marked FAILED); FULL = rows present and behavioral shifts detected; PARTIAL = rows present and no shifts. AI is never called without user data. |
| AI error classification | `ai_errors.py` defines `AITimeoutError` / `AIUnavailableError` (transient) vs `AIInvalidRequestError`, all under base `OpenAICallError`. On the **insight** path these are caught by `FallbackAIInsightClient` (F2) → deterministic fallback, so the insight still completes (degraded) rather than failing. The **reaper** still requeues insights orphaned in `PROCESSING` by a worker *crash* (lease expiry), which is a separate concern from AI errors. Classification is at the `OpenAIGateway` / client layer; use cases never catch raw `httpx` or SDK errors. |
| Chat token budget | `ChatTokenBudget` (Redis) caps total tokens consumed per user per billing period. Enforced in `ChatStreamUseCase` via `StreamUsage` callback. On client disconnect (usage sentinel never arrives), an estimate_tokens_from_text fallback (chars // 4 + 1) records an estimated spend so capacity is never silently skipped; logs `chat_stream_usage_estimated`. |
| Chat retrieval | Chat is tools-only: a bounded OpenAI function-calling loop over the `ChatTools` query library (`search_transactions` uses pg_trgm GIN indexes — no pgvector on the chat path). Tool results are treated as untrusted data (OWASP LLM01 treatment). `ChatTools` opens a fresh short-lived DB session per tool call to preserve the §10.4 connection-release invariant. |
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
| DB | Postgres 17 + pg_trgm |
| Cache / sessions / idempotency / rate limit / token budget | Redis 7 |
| Message bus | Kafka via FastStream |
| AI | OpenAI: `gpt-4o` (insights structured output), `gpt-4o-mini` (chat function-calling + parse-text + receipt vision). Upgrade via env var. |
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
- **Chat tools**: tool results returned from the function-calling loop are treated as untrusted data (OWASP LLM01) — the system prompt instructs the model to treat tool result content as raw data, not as instructions. Chat history `role` whitelisted against `{user, assistant}` on replay.
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
| `insight-worker` | `python -m app.main.insight.main` | FastStream consumer on `yomochi.insights.v1`. Claims insight with `processing_deadline = now() + 15 min` (lease). |
| `scheduler-worker` | `python -m app.main.scheduler.main` | APScheduler — 6 scheduled jobs (see §4). No Dishka |

Same Docker image, different `command:` per Helm Deployment (childprofile pattern). All Kafka consumers + outbox support horizontal scaling (Kafka rebalance / `SKIP LOCKED`).

### 10.2 Resource limits (Helm requests)

| Worker | CPU | Memory | Notes |
|---|---|---|---|
| `outbox-worker` | 0.25 | 256M | Lightweight DB poll + Kafka publish |
| `insight-worker` | 0.5 | 448M | Heaviest — insight gen (structured OpenAI output) |
| `scheduler-worker` | 0.25 | 256M | Idle 99% of the time |

### 10.3 Failure modes runbook

| Symptom | Cause | Fix |
|---|---|---|
| Insights stuck at QUEUED | outbox-worker not running | restart outbox-worker |
| Insights stuck at PROCESSING | insight-worker crashed mid-pipeline | reaper_tick auto-requeues when `processing_deadline` expires (≤15 min); exhausted rows (≥`reaper_max_retries`) flip to FAILED automatically |
| Outbox rows stranded as FAILED | Kafka/broker outage longer than `max_retries × poll_interval` quarantined them | after the broker recovers, replay via `scripts/replay_outbox.py` — see the outbox-replay runbook (§10.6) |
| High Kafka lag on `yomochi.insights.v1` | OpenAI degraded or slow | check rate-limit headers + breaker state. Note: insights still complete (degraded deterministic summary, F2) rather than failing while OpenAI is down |
| Behavioral-shift alerts not generated | scheduler-worker not running or crashed | restart scheduler-worker; check `detect_shift_alerts_job` logs |

### 10.4 Connection pool

Explicit pool config: `pool_size=10, max_overflow=5, recycle=1800s`. Hot paths explicitly release DB connections before long-running external calls: `ProcessInsightUseCase` (claim TX → no-TX OpenAI calls → save TX), and `ChatQueryUseCase` / `ChatStreamUseCase` (TX1 short read — history fetched and committed → LLM call with no session held → TX2 fresh short write to persist turns). `ChatTools` opens a fresh short session per tool call (via the APP-scoped session factory) so no connection is held across the OpenAI tool-selection round-trips.

### 10.5 Runbook — DLQ drain & replay (insight-worker)

A message lands in the DLQ topic (`KAFKA_TOPIC_DLQ`, default `yomochi.dlq.v1`) after
the handler fails it `CONSUMER_MAX_RETRIES` (default 3) times; the DLQ body is the
original event + an injected `x_error`. Signal: `consumer_dlq_event` /
`consumer_dlq_events_total{topic}` climbing. See §4.1 for the delivery semantics;
kill-test `tests/integration/messaging/test_insight_dlq.py`.

**Inspect** (read without consuming; `$BROKERS` e.g. `localhost:9092`):

```bash
kcat -b "$BROKERS" -t yomochi.dlq.v1 -C -o beginning -e -q   # or kafka-console-consumer.sh
```

Per message decide **discard** (bad data — leave it; documents itself via `x_error`)
or **replay** (transient cause now fixed — broker outage, downstream 5xx, deploy bug).

**Replay — clear the Redis idempotency keys FIRST (critical).** Parking an event sets
its idempotency key, so republishing the same `event_id` is **skipped as a duplicate**
until the key's 24 h TTL expires. Delete both keys per replayed `event_id`:

```bash
# REDIS=host:port, EVENT_ID=the event's event_id
redis-cli -h "${REDIS%:*}" -p "${REDIS#*:}" DEL \
  "consumer:idempotency:${EVENT_ID}" "consumer:failures:${EVENT_ID}"
```

Then republish to the main topic, stripped of `x_error`:

```bash
kcat -b "$BROKERS" -t yomochi.dlq.v1 -C -o beginning -c1 -e -q \
  | jq -c 'del(.x_error)' | kcat -b "$BROKERS" -t yomochi.insights.v1 -P
```

Verify: `process_insight` succeeds / the insight reaches `COMPLETED`; `consumer_dlq_event`
stops climbing. If it re-parks, the cause is **not** transient — fix forward, don't loop replays.

### 10.6 Runbook — outbox FAILED replay

The outbox-worker quarantines a row as `FAILED` after `max_retries` (default 5) publish
failures (`status=FAILED` + `last_error` + `failed_at`; `outbox_relay_total{status="quarantined"}`).
A broker outage longer than `max_retries × poll_interval` strands every in-flight event there.

Inspect: `SELECT id, event_type, retry_count, failed_at, left(last_error,200) FROM outbox_events
WHERE status='FAILED' ORDER BY failed_at;`. Replay (after the downstream is healthy) flips
selected rows back to PENDING (`retry_count` reset) so the poller re-drives them — no worker
restart needed. Always `--dry-run` first:

```bash
DATABASE_URL=… uv run python -m scripts.replay_outbox --all --dry-run
DATABASE_URL=… uv run python -m scripts.replay_outbox --all --min-age-minutes 10 --limit 200
```

| Flag | Effect |
|---|---|
| `--id <uuid>` (repeatable) / `--event-type <t>` / `--all` | selector — at least one required (refuses otherwise) |
| `--min-age-minutes N` | only rows whose `failed_at` is older than N min (backoff for a recovering downstream) |
| `--limit N` | cap, oldest-failure-first |
| `--dry-run` | list only, no write |

Selection uses `FOR UPDATE SKIP LOCKED` (safe while the poller runs). Verify the FAILED count
drops and those rows reach `SENT`. If a row re-quarantines immediately, the cause is not
transient — fix forward. (Port `OutboxAdmin` / `SqlaOutboxAdmin`; integration test
`tests/integration/outbox/test_outbox_replay.py`.)

## 11. Out-of-scope architectural choices

- Microservices split — rejected. Modular monolith is the unit of deploy.
- GraphQL / gRPC — rejected. REST + OpenAPI 3.1.
- WebSocket — chat streaming uses SSE. Push notifications deferred.
- Read replicas, sharding, Citus — deferred. Single Postgres handles current scale.
- Saga / Event Sourcing / standalone CQRS — outbox + state machines suffice.
- Local AI — deferred (memory: `project_p4a_deferred.md`). OpenAI on hot path; Ollama/local embedder would be reintroduced via new ports if/when local AI lands.
- Per-transaction embedding chunks — rejected. Monthly aggregation is sufficient granularity.
- Vector store / pgvector / RAG — **removed**. `user_financial_chunks`, `dirty_periods`, `portrait_queue`, the embedding refresh loop, the portrait pipeline, and all related ports (`TextEmbedder`, `ChunkRetriever`, `ChunkWriter`, `DirtyPeriodRepository`, `PortraitQueue`) were deleted. Migration `000000000002_drop_vector_store` drops the tables and the `vector` extension. The `pg_trgm` extension (used by `search_transactions`) is retained.
- Celery — rejected. Incompatible with async SQLAlchemy.
- Arq migration — **CANCELLED** (memory: `project_v3_arq_migration.md`). Arq stays in maintenance-only evaluation; APScheduler retained for V1. K8s `CronJob` per schedule is the migration path considered for V2 (see `features.md` F8).
