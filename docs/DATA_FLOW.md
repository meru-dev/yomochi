# DATA_FLOW.md — Yomochi

> Traces every major user action from HTTP request through all async workers to final DB state.
> For architecture principles and process topology see `ARCHITECTURE.md`. Remaining work: `TODO.md`. Known issues: `bugs.md`. Architecture-review backlog: `features.md`.

## System map

```
┌─────────────────────────────────────────────────────────────────┐
│  HTTP Client (Browser / API consumer)                            │
└────────────┬────────────────────────────────────────────────────┘
             │ HTTPS
┌────────────▼──────────────────────────────────────────────────┐
│  FastAPI api process                                            │
│  Middleware: RequestId → RateLimit (Redis) → Idempotency       │
│             → HttpMetrics → SecurityHeaders                     │
│  Auth: JWT cookie → IdentityContext(user_id, plan)             │
└──────────────┬─────────────────────────────────────────────────┘
               │ Dishka DI (Scope.REQUEST per route)
     ┌─────────┴──────┬─────────────────┬──────────────────┐
     │                │                 │                  │
  Transactions     Insights          Chat              Alerts
  Categories       (request)         (query/stream)    (list/read)
  Users/Auth       Reports           Search            Recurring
  Ingestion
     │
     ▼
┌──────────────────┬──────────────┬──────────────────────────────┐
│  PostgreSQL 17   │  Redis 7     │  Kafka (KRaft)               │
│  + pg_trgm       │              │                              │
└──────────────────┴──────────────┴──────────────┬─────────────-┘
                                                  │
           ┌──────────────────────────────────────┴──────────────┐
           │                                                      │
                                        ▼ yomochi.insights.v1
                                ┌─────────────────────────────────┐
                                │  insight-worker (FastStream)     │
                                │  run insight pipeline            │
                                │   (deterministic SQL)            │
                                └─────────────────────────────────┘
   (transaction-worker + yomochi.transactions.v1 removed)

  ┌───────────────────────────────────┐
  │  outbox-worker                    │
  │  Polls outbox_events → Kafka      │
  │  Per-row TX + retry/quarantine    │
  │  FAILED rows replayable (F17:     │
  │  scripts/replay_outbox.py)        │
  └───────────────────────────────────┘
```

---

## 1. Transaction creation

```
POST /v1/transactions
        │
        ▼
CreateTransactionUseCase
  ├── [quota check — skipped if bypass_quota=True (recurring rules)]
  │   UserPlanLookup.get_plan(user_id) → Plan
  │   TransactionRepository.count_created_in_month(user_id, year, month) → used
  │   plan.monthly_limit(QuotaResource.TRANSACTIONS) → limit
  │   If used >= limit → QuotaExceededError → HTTP 429
  │   (counted from DB, atomic with work TX — no Redis refund path)
  │
  ├── CategoryListReader.resolve(category_id) → Category
  │
  ├── TransactionRepository.save(transaction)
  │       └── INSERT INTO transactions (id, user_id, amount, currency,
  │               category_id, date, type, description, ...)
  │
  ├── AuditLog.append(TransactionCreated audit event)
  │
  └── Flusher.flush() → COMMIT
```

**No transaction outbox/Kafka path.** Transactions do not emit outbox events;
the `transaction-worker` process and the `yomochi.transactions.v1` topic were
removed. The outbox relay and Kafka carry **insight** events
(`yomochi.insights.v1`) — see §4.

---

## 2. Behavioral-shift alert detection (scheduler)

Runs **daily at 02:00 UTC** as `detect_shift_alerts_job` in the scheduler-worker:

```
detect_shift_alerts_job
  │
  └── for each recently-active user_id:
        │
        ├── BudgetSummaryReader.read_month(user_id, year, month)
        │       └── SELECT transactions JOIN categories
        │           GROUP BY currency, type, category
        │
        ├── BudgetSummaryReader.read_history_months(user_id, year, month, n=3)
        │       └── same, for 3 previous months
        │
        ├── MonthlyAggregator.aggregate() → MonthlyAggregation per currency
        │       (total income, total expense, savings rate,
        │        top categories, day-of-month distribution)
        │
        ├── BehavioralShiftDetector.detect(current, history)
        │       Compares current month vs prior 3 months:
        │       • expense_spike:    expenses rose >15% / >30%
        │       • income_drop:      income fell >10% / >20%
        │       • savings_collapse: savings rate < 15%
        │       • savings_decline:  savings rate dropped >8%
        │       • category_spike:   anomalous category growth
        │
        └── AlertWriter.write_shift_alerts(user_id, year, month, shifts)
                └── For each shift where alert_threshold.is_alertworthy():
                    INSERT INTO user_alerts (type, subtype, ...)
                    ON CONFLICT (user_id, subtype,
                                period_year, period_month)
                    DO NOTHING  ← idempotent
```

**Idempotency:** the unique constraint `ux_user_alerts_dedup` on `(user_id, subtype, period_year, period_month)` means re-running the job on the same period is safe. `subtype` is the shift type (or `"<type>:<category>"` for category spikes), so one alert per distinct shift per period.

---

## 4. Insight generation

### 4a. HTTP request (user side)

```
POST /v1/insights/requests {period: "monthly"}
        │
        ▼
RequestInsightUseCase
  ├── UserPlanLookup.get_plan(user_id) → Plan
  │   InsightRepository.count_created_in_month(user_id, year, month) → used
  │   plan.monthly_limit(QuotaResource.INSIGHTS) → limit
  │   If used >= limit → QuotaExceededError → HTTP 429
  │
  ├── TransactionReader.count_for_period(user_id, year, month)
  │       If < min_transactions_for_insight → InsufficientTransactionsError → HTTP 422
  │       (read from InsightWorkerConfig; default 3; env MIN_TRANSACTIONS_FOR_INSIGHT)
  ├── Insight.create(status=PENDING)
  ├── OutboxRepository.append(InsightRequested)
  └── COMMIT
  → HTTP 202 with {insight_id}
```

### 4b. Async pipeline (insight-worker)

```
outbox-worker → Kafka yomochi.insights.v1 (InsightRequested)
        │
insight-worker: on_insight_event
        │
        ▼
ProcessInsightUseCase
  │
  ├── TX1 (claim): InsightRepository.claim_for_processing(insight_id, user_id, deadline)
  │       deadline = now() + 15 min (lease)
  │       SELECT FOR UPDATE: QUEUED → PROCESSING, stamp processing_deadline
  │       Wrong user_id → InsightNotFoundError (defense-in-depth)
  │       Already terminal → InsightAlreadyTerminalError → consumer marks processed, no DLQ
  │
  ├── build_insight_context (DETERMINISTIC — no embeddings, no vector search):
  │       BudgetSummaryReader.read_month(user_id, year, month) → current aggregate
  │       BudgetSummaryReader.read_history_months(user_id, year, month, n=3) → prior 3
  │       MonthlyAggregator.aggregate() per month → MonthlyAggregation[]
  │       BehavioralShiftDetector.detect(current, history) → shifts (if any)
  │       format_monthly_summary(agg) + format_shift_text(shifts) → InsightContextChunk[]
  │         (deterministic context passed to the AI client)
  │
  ├── assess_quality (deterministic):
  │       NONE    = no transaction rows for the period → mark_failed, stop
  │                 (AI never called without user data)
  │       FULL    = rows present AND behavioral shifts detected
  │       PARTIAL = rows present AND no shifts
  │
  ├── BudgetSummaryReader.read_month() → BudgetSummarySnapshot (per-currency totals)
  │
  ├── AIInsightClient.generate(InsightRequest)   ← FallbackAIInsightClient (F2)
  │       primary → OpenAI gpt-4o (structured output):
  │         system: financial analyst persona
  │         context: deterministic monthly summary + behavioral shift text
  │         prompt_cache_key=user_id (F1 prompt caching)
  │         → { title, description, impact_score, tokens_used }
  │       on OpenAI gateway failure (rate-limit / timeout / 5xx / breaker OPEN):
  │         → DeterministicInsightClient: vendor-free templated summary from the
  │           same context chunks (insight_fallback_total{reason}); insight still
  │           completes (degraded) instead of dying.
  │
  └── insight.mark_completed(title, description, impact_score,
          context_quality, generated_at, budget_summary)
      SAVE → UPDATE insights SET status=COMPLETED, ...

On unexpected (non-gateway) error: → publish to DLQ topic

Reaper (scheduler-worker, every 10 min):
  lease expired + retry_count < max_retries → flip PROCESSING → QUEUED + re-emit InsightRequested
  lease expired + retry_count >= max_retries → flip PROCESSING → FAILED
```

**Delivery to browser (F4):** `GET /v1/insights/{id}/stream` (SSE) pushes status
transitions + the terminal COMPLETED/FAILED payload the instant the worker writes
the row, then closes (~2-min timeout sentinel). A low-frequency `GET /v1/insights/{id}`
poll remains as a backstop. Generation is out-of-band in the worker, so the stream
watches the row, not LLM tokens.

---

## 5. Chat

Chat is **tools-only**: an OpenAI **function-calling** loop over a typed
`ChatTools` library — 6 user-scoped tools (`get_month_summary`,
`get_category_trend`, `get_spend_window`, `get_user_profile`,
`search_transactions`, `list_categories`). The model requests exactly the data
it needs; the use case provides a `tool_executor` closure bound to the request
`user_id` (server-side — the model cannot supply a user id). `search_transactions`
is a pg_trgm fuzzy match on `merchant`/`notes` (no vector search — chat does not
touch the embedder or pgvector). The loop is iteration-capped; tool results are
treated as untrusted data. `ChatTools` opens a fresh short DB session per call
(no connection held across OpenAI rounds). Tool-round + final-answer tokens are
all charged to `ChatTokenBudget`.

Both endpoints (`/v1/chat`, `/v1/chat/stream`) share the same save-turns +
token-budget tail.

```
POST /v1/chat          → ChatQueryUseCase   (returns full response at once)
POST /v1/chat/stream   → ChatStreamUseCase  (SSE: streams tokens as they arrive)

Shared tools path:
  ├── chat_rate_limit dependency:
  │       Redis INCR "rl:chat:{user_id}:{minute_window}"
  │       If > 20 → HTTP 429
  │
  ├── ChatHistoryStore.last_n(user_id, n=5)
  │       └── SELECT ... WHERE user_id=?
  │           ORDER BY created_at DESC LIMIT 5
  │           → reversed() → chronological order
  │
  ├── ChatTokenBudget.check(user_id)
  │       → Redis: enforce per-user token cap for the billing period
  │
  ├── ChatAIClient.chat_with_tools / stream_with_tools(ChatToolsRequest)
  │       model: gpt-4o-mini, temperature=0.4, max_tokens=800
  │       prompt_cache_key=user_id (F1 prompt caching — stable prefix kept hot)
  │       [system]: finance assistant that fetches data via tools
  │       [history]: last 5 turns (role=user/assistant)
  │       [user]: current message
  │       [tools]: typed ChatTools schemas (bounded iteration cap)
  │       → answer text (or token stream for SSE)
  │
  ├── ChatTokenBudget.record(user_id, tokens_used)
  │       On client disconnect (usage sentinel never arrives):
  │       estimate_tokens_from_text fallback (chars // 4 + 1) records an
  │       estimated spend; logs chat_stream_usage_estimated.
  │
  ├── ChatHistoryStore.save_turns(user_id, [
  │       ChatTurn(role="user",      content=message,  chunks_used=(),
  │                created_at=clock.now()),        ← first clock.now() call
  │       ChatTurn(role="assistant", content=answer,
  │                chunks_used=[{tool: name}, ...],
  │                created_at=clock.now())         ← second call; later by wall clock
  │   ])
  │   Ordering guaranteed by monotone UUIDv7 id tie-break:
  │       ORDER BY created_at DESC, id DESC
  │   Keyset cursor: (created_at, CAST(id AS uuid)) — no text-lexicographic compare.
  │   └── INSERT INTO chat_turns (id, user_id, role, content,
  │           chunks_used::jsonb, created_at)
  │
  └── → {turn_id, answer, context_quality, created_at}

GET /v1/chat/history
  └── ListChatHistoryUseCase (cursor-based pagination)

DELETE /v1/chat/history
  └── ClearChatHistoryUseCase → DELETE FROM chat_turns WHERE user_id=?
```

---

## 6. Alerts

Alerts are created **automatically** by `detect_shift_alerts_job` (scheduler-worker, daily 02:00 UTC) — not by user request.

### Storage

```
user_alerts:
  id           UUID
  user_id      UUID → FK users
  type         VARCHAR(30)   (SPENDING_SPIKE | INCOME_DROP | SAVINGS_COLLAPSE)
  subtype      VARCHAR(100)  (shift type, or "<type>:<category>" for category
                              spikes — part of the dedup key)
  title        TEXT
  body         TEXT     (amounts, currency, % change)
  metadata     JSONB
  period_year  SMALLINT
  period_month SMALLINT
  is_read      BOOLEAN  DEFAULT false
  created_at   TIMESTAMPTZ

Unique: ux_user_alerts_dedup (user_id, subtype, period_year, period_month)
→ one alert per distinct shift subtype per period
```

### HTTP endpoints

```
GET  /v1/alerts
  └── ListAlertsUseCase
      ├── AlertRepository.list_for_user(user_id, limit, cursor, unread_only?)
      │       SELECT ... WHERE user_id=? [AND is_read=false]
      │       ORDER BY created_at DESC
      │       Cursor: base64({created_at, id})
      └── → {items: [...], next_cursor, unread_count}

GET  /v1/alerts/unread-count
  └── AlertRepository.unread_count(user_id)
      └── SELECT COUNT(*) WHERE user_id=? AND is_read=false

PATCH /v1/alerts/{id}/read
  └── MarkAlertReadUseCase
      └── UPDATE user_alerts SET is_read=true WHERE id=? AND user_id=?

DELETE /v1/alerts
  └── ClearAlertsUseCase
      └── DELETE FROM user_alerts WHERE user_id=?
```

**Weekly purge** (scheduler, Sunday 03:30 UTC):
```
DELETE FROM user_alerts WHERE created_at < NOW() - INTERVAL '90 days'
```

---

## 7. Receipt ingestion (parse-receipt)

No media is retained. The uploaded file is processed in-memory and discarded.

```
POST /v1/ingestion/parse-receipt  (multipart/form-data, image file)
        │
        ▼
ParseReceiptUseCase
  ├── UploadPolicy.validate(file)           ← size + MIME type check
  ├── ImagePreprocessor.preprocess(bytes)   ← Pillow: resize + normalize
  ├── ReceiptExtractor.extract(image_bytes)
  │       → OpenAI gpt-4o-mini vision (soft dependency)
  │         → ParsedReceipt(amount, currency, date, merchant, category_hint)
  │         On breaker OPEN or error → return empty draft (frontend fills manually)
  └── → ParsedReceiptDraft (JSON, no DB write, no file stored)
```

---

## 8. Complete chain: transaction → all features

```
User creates transaction
        └─ [sync]  → transactions table + audit_events (same DB TX)
           (no outbox/Kafka path for transactions)

scheduler-worker: detect_shift_alerts_job (02:00 UTC daily)
        ├─ for each recently-active user: read month + 3-month history
        ├─ MonthlyAggregator + BehavioralShiftDetector → shifts
        └─ write user_alerts (idempotent)

User requests insight
        ├─ [sync]  → Insight(PENDING) + InsightRequested in outbox
        └─ [async] → Kafka yomochi.insights.v1

insight-worker: on_insight_event  (DETERMINISTIC)
        ├─ read month aggregate + prior 3 months (BudgetSummaryReader)
        ├─ MonthlyAggregator + BehavioralShiftDetector → deterministic context (InsightContextChunk[])
        ├─ assess_quality → NONE (no rows) / FULL (rows+shift) / PARTIAL (rows, no shift)
        ├─ OpenAI gpt-4o (structured output) → title, description, impact_score
        └─ save Insight(COMPLETED) + BudgetSummarySnapshot

User reads alerts
        └─ SELECT user_alerts (populated by detect_shift_alerts_job)

User chats  (function-calling / tools loop)
        ├─ OpenAI function-calling over ChatTools (6 tools, SQL + pg_trgm)
        ├─ load last 5 chat turns
        ├─ OpenAI gpt-4o-mini (plain text or SSE stream)
        └─ save 2 chat_turns (user + assistant)
```

---

## 9. Storage schema

| Table | Purpose |
|-------|---------|
| `users` | Accounts, subscription plan |
| `transactions` | All financial operations |
| `categories` | Category hierarchy (system + user-defined) |
| `insights` | Generated insights + budget_snapshot JSONB |
| `user_alerts` | Behavioral shift alerts (spending spike, income drop, etc.) |
| `chat_turns` | Chat history (role + tool calls JSONB) |
| `outbox_events` | Transactional outbox → Kafka (status: PENDING / SENT / FAILED) |
| `recurring_rules` | Recurring transaction rules state machine |
| `audit_events` | Login, transaction CRUD, insight requests (partitioned by month) |
| `password_reset_tokens` | Short-lived tokens for password reset flow |


---

## 10. External dependencies

| Service | Usage |
|---------|-------|
| **OpenAI gpt-4o** | Insight generation (structured output: title, description, impact_score) |
| **OpenAI gpt-4o-mini** | Chat function-calling loop (tools mode, non-streaming + SSE), parse-text, receipt extraction |
| **Kafka** | InsightRequested/Completed, DLQ (transaction events removed) |
| **Redis** | Sessions, rate limiting (IP + per-user chat), consumer idempotency, search cache, chat token budget |
| **PostgreSQL 17 + pg_trgm** | Primary store + pg_trgm fuzzy search (`search_transactions` via GIN index on merchant/notes) |
