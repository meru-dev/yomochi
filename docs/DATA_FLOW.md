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
│  + pgvector      │              │                              │
└──────────────────┴──────────────┴──────────────┬─────────────-┘
                                                  │
           ┌──────────────────────────────────────┴──────────────┐
           │                                                      │
           ▼ yomochi.transactions.v1              ▼ yomochi.insights.v1
  ┌────────────────────┐                 ┌─────────────────────────────┐
  │  transaction-worker│                 │  insight-worker              │
  │  (FastStream)      │                 │  (FastStream)                │
  │  mark dirty_periods│                 │  run insight pipeline        │
  │  No OpenAI.        │                 │  + embedding refresh (30s)   │
  └────────────────────┘                 └─────────────────────────────┘

  ┌───────────────────────────────────┐
  │  portrait-worker (background)     │
  │  No Kafka. Refresh 60s.           │
  │  portrait_queue → 4-month chunks  │
  └───────────────────────────────────┘

  ┌───────────────────────────────────┐
  │  outbox-worker                    │
  │  Polls outbox_events → Kafka      │
  │  Per-row TX + retry/quarantine    │
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
  ├── DirtyPeriodMarker.mark_dirty(user_id, year, month)
  │       └── INSERT INTO dirty_periods (user_id, year, month)
  │           ON CONFLICT DO NOTHING        ← idempotent, same DB TX
  │
  ├── OutboxRepository.append(TransactionCreated)
  │       └── INSERT INTO outbox_events (event_type="TransactionCreated",
  │               payload={user_id, transaction_id, date, ...},
  │               trace_context={traceparent, tracestate},  ← W3C carrier
  │               status=PENDING)
  │
  ├── AuditLog.append(TransactionCreated audit event)
  │
  └── Flusher.flush() → COMMIT
```

**Outbox relay** (outbox-worker, polling loop):
```
OutboxPoller.run_once()
  ├── Snapshot PENDING row IDs (no lock held during publish)
  └── For each row_id:
      ├── Re-lock row (FOR UPDATE SKIP LOCKED)
      ├── Extract trace_context JSONB → attach via TraceContextTextMapPropagator
      │       as parent span context (handles NULL / garbage / empty safely)
      ├── Open INTERNAL span `outbox.publish` under resumed parent
      ├── Kafka.publish(topic="yomochi.transactions.v1", key=user_id.bytes)
      │       → KafkaTelemetryMiddleware adds PRODUCER span + injects traceparent
      │         header so the consumer resumes the same trace
      ├── UPDATE outbox_events SET status=SENT
      └── On failure:
          ├── retry_count < max_retries → bump retry_count + last_error
          └── retry_count ≥ max_retries → SET status=FAILED, failed_at=now()
```

**Transaction consumer** (transaction-worker, Kafka):
```
Topic: yomochi.transactions.v1
on_transaction_event(body)
  ├── ConsumerIdempotencyStore.is_processed(event_id) → skip if already seen
  ├── DirtyPeriodRepository.mark_dirty(user_id, year, month)
  │       ← secondary path; primary mark happens in api TX above.
  │         Needed for future external transaction sources.
  └── store.mark_processed(event_id, ttl=...)
      On error: publish to DLQ topic
```

---

## 2. Embedding refresh (insight-worker background loop)

insight-worker background loop runs **every 30 seconds**:

```
_embedding_refresh_loop
  │
  ├── SqlaDirtyPeriodRepository.pop_dirty(limit=20)
  │       └── DELETE FROM dirty_periods
  │           WHERE (user_id, year, month) IN (
  │               SELECT ... FOR UPDATE SKIP LOCKED LIMIT 20
  │           ) RETURNING *
  │
  └── for each DirtyPeriod:
        EmbeddingPipeline.refresh(user_id, year, month)
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
          ├── _write_monthly_chunk()
          │       ├── format_monthly_summary(agg) → natural language text
          │       ├── compute_semantic_hash(agg)
          │       ├── TextEmbedder.embed(text) → vector[1536]  (OpenAI)
          │       └── ChunkWriter.upsert(chunk_type="monthly_summary")
          │               └── INSERT INTO user_financial_chunks
          │                   ON CONFLICT (user_id, chunk_type, period_year, period_month)
          │                   DO UPDATE WHERE semantic_hash != EXCLUDED.semantic_hash
          │                   (no-op if data unchanged)
          │
          └── _write_shift_chunk()
                  ├── BehavioralShiftDetector.detect(current, history)
                  │       Compares current month vs prior 3 months:
                  │       • expense_spike:    expenses rose >15% / >30%
                  │       • income_drop:      income fell >10% / >20%
                  │       • savings_collapse: savings rate < 15%
                  │       • savings_decline:  savings rate dropped >8%
                  │       • category_spike:   anomalous category growth
                  │
                  ├── If shifts found:
                  │       ├── format_shift_text() → natural language
                  │       ├── TextEmbedder.embed() → vector[1536]
                  │       ├── ChunkWriter.upsert(chunk_type="behavioral_shift")
                  │       └── AlertWriter.write_shift_alerts(user_id, shifts)
                  │               └── For each shift where alert_threshold.is_alertworthy():
                  │                   INSERT INTO user_alerts
                  │                   ON CONFLICT (user_id, type, currency,
                  │                               period_year, period_month)
                  │                   DO NOTHING  ← idempotent
                  │
                  └── If no shifts → nothing written for shift chunk
```

**Dedup guarantee:** `dirty_periods` has unique constraint on `(user_id, year, month)` — a burst of N transactions marks dirty once, triggers one refresh cycle. `semantic_hash` check inside `EmbeddingPipeline` means the upsert is a no-op if the aggregate is unchanged.

---

## 3. Portrait refresh (portrait-worker background loop)

Portrait = aggregated behavioral profile for a user, built from 4 months of transactions. One chunk per user (`period_year=0, period_month=0`).

portrait-worker loop runs **every 60 seconds**:

```
_portrait_refresh_loop
  │
  ├── SqlaPortraitQueue.pop_dirty(limit=10)
  │       └── DELETE FROM portrait_queue
  │           WHERE user_id IN (
  │               SELECT user_id ORDER BY marked_at LIMIT 10
  │               FOR UPDATE SKIP LOCKED
  │           ) RETURNING user_id
  │
  └── for each user_id:
        PortraitPipeline.refresh(user_id)
          │
          ├── BudgetSummaryReader.read_history_months(user_id, n=4)
          │       └── last 4 months of transactions
          │
          ├── MonthlyAggregator.aggregate() per month → MonthlyAggregation[]
          │
          ├── PortraitAggregator.format_portrait_text(recent, baselines)
          │       → spending patterns, income trends, category dynamics
          │
          ├── compute_semantic_hash(all_aggs)
          │
          ├── TextEmbedder.embed(portrait_text) → vector[1536]
          │
          └── ChunkWriter.upsert(
                  chunk_type="user_portrait",
                  period_year=0, period_month=0,
                  content=portrait_text,
                  embedding=vector
              )

        On refresh error:
          └── SqlaPortraitQueue.mark_dirty(uid)  ← requeue, no data loss
```

**When portrait_queue is populated:**
- Weekly (Monday 03:00 UTC): scheduler calls `mark_all_dirty()` → all users enqueued
- Potentially after significant transaction changes (future enhancement)

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
  │       If < MIN_TRANSACTIONS → InsufficientTransactionsError → HTTP 422
  │       (MIN_TRANSACTIONS is currently the hardcoded constant `5` in
  │        `app/application/insights/use_cases/request_insight.py`;
  │        `InsightWorkerSettings.min_transactions_for_insight=3` exists but is
  │        not wired — see bugs.md)
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
  ├── EmbeddingPipeline.refresh(user_id, year, month)
  │       ← ensures chunks are fresh before retrieval (idempotent)
  │
  ├── TextEmbedder.embed("Financial insights for {year}-{month}")
  │       → query_vector[1536]
  │
  ├── ChunkRetriever.search(user_id, query_vector,
  │       monthly_top_k=3, shift_top_k=2)
  │       └── SELECT ... ORDER BY embedding <=> query_vector
  │           WHERE user_id=? AND chunk_type IN (monthly_summary, behavioral_shift)
  │           → top-3 monthly_summary + top-2 behavioral_shift
  │
  ├── ChunkRetriever.get_portrait(user_id)
  │       └── SELECT ... WHERE chunk_type='user_portrait' AND user_id=?
  │           if exists → prepend to chunks
  │
  ├── assess_quality(chunks):
  │       FULL    = has monthly_summary AND behavioral_shift chunks
  │       PARTIAL = has only one type
  │       NONE    = no chunks → mark_failed, stop (AI never called)
  │
  ├── _trim_chunks(chunks, budget=12_000 tokens):
  │       tiktoken count total prompt tokens (4/msg formula + 11 overhead)
  │       evict lowest-similarity non-portrait chunks until within budget
  │       portrait (similarity=1.0) always pinned
  │       logs token_budget_trim (WARNING per eviction) + token_budget_trimmed (INFO summary)
  │
  ├── BudgetSummaryReader.read_month() → BudgetSummarySnapshot (per-currency totals)
  │
  ├── AIInsightClient.generate(InsightRequest)
  │       → OpenAI gpt-4o (structured output):
  │         system: financial analyst persona
  │         context: portrait + monthly summaries + behavioral shifts
  │         → { title, description, impact_score, tokens_used }
  │
  └── insight.mark_completed(title, description, impact_score,
          context_quality, generated_at, budget_summary)
      SAVE → UPDATE insights SET status=COMPLETED, ...

On error: → publish to DLQ topic

Reaper (scheduler-worker, every 10 min):
  lease expired + retry_count < max_retries → flip PROCESSING → QUEUED + re-emit InsightRequested
  lease expired + retry_count >= max_retries → flip PROCESSING → FAILED
```

**Polling:** Browser polls `GET /v1/insights/{id}` every 2s until `status = COMPLETED | FAILED`.

---

## 5. Chat

Both endpoints share the same retrieval and AI call path.

```
POST /v1/chat          → ChatQueryUseCase   (returns full response at once)
POST /v1/chat/stream   → ChatStreamUseCase  (SSE: streams tokens as they arrive)

Shared retrieval path:
  ├── chat_rate_limit dependency:
  │       Redis INCR "rl:chat:{user_id}:{minute_window}"
  │       If > 20 → HTTP 429
  │
  ├── TextEmbedder.embed(user_message) → query_vector[1536]
  │
  ├── ChunkRetriever.search(user_id, query_vector,
  │       monthly_top_k=2, shift_top_k=2)
  │       → 2 monthly_summary + 2 behavioral_shift (max 4)
  │
  ├── ChunkRetriever.get_portrait(user_id)
  │       If exists → prepend: portrait + 2 monthly + 2 shift = 5 chunks max
  │
  ├── assess_quality(chunks) → FULL | PARTIAL | NONE
  │
  ├── ChatHistoryStore.last_n(user_id, n=5)
  │       └── SELECT ... WHERE user_id=?
  │           ORDER BY created_at DESC LIMIT 5
  │           → reversed() → chronological order
  │
  ├── [ChatStream only] ChatTokenBudget.check(user_id)
  │       → Redis: enforce per-user token cap for the billing period
  │
  ├── ChatAIClient.chat(ChatRequest)
  │       model: gpt-4o-mini, temperature=0.4, max_tokens=800
  │       [system]: "You are a personal finance assistant..."
  │       [system]: chunks as financial context
  │       [history]: last 5 turns (role=user/assistant)
  │       [user]: current message
  │       → answer text (or token stream for SSE)
  │
  ├── [ChatStream only] ChatTokenBudget.record(user_id, tokens_used)
  │
  ├── ChatHistoryStore.save_turns(user_id, [
  │       ChatTurn(role="user",      content=message,  chunks_used=()),
  │       ChatTurn(role="assistant", content=answer,
  │                chunks_used=[{chunk_type, period_label, similarity}, ...],
  │                created_at=user_turn.created_at + 1μs)
  │   ])
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

Alerts are created **automatically** during embedding refresh (step 2) — not by user request.

### Storage

```
user_alerts:
  id           UUID
  user_id      UUID → FK users
  type         VARCHAR  (SPENDING_SPIKE | INCOME_DROP | SAVINGS_COLLAPSE |
                          SAVINGS_DECLINE | CATEGORY_SPIKE)
  title        TEXT
  body         TEXT     (amounts, currency, % change)
  currency     VARCHAR
  period_year  INT
  period_month INT
  is_read      BOOLEAN  DEFAULT false
  created_at   TIMESTAMPTZ

Unique: (user_id, type, currency, period_year, period_month)
→ one alert per type per period
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
        │
        ├─ [sync]  → transactions table
        ├─ [sync]  → dirty_periods UPSERT (same DB TX)
        └─ [async] → outbox → Kafka yomochi.transactions.v1

transaction-worker (Kafka)
        └─ UPSERT dirty_periods (secondary, for future external sources)

insight-worker: embedding_refresh_loop (every 30s)
        ├─ pop_dirty → EmbeddingPipeline.refresh(user_id, year, month)
        ├─ aggregate transactions → monthly_summary text + behavioral_shift text
        ├─ embed → store chunks in user_financial_chunks (pgvector)
        └─ if shifts detected → write user_alerts (idempotent)

portrait-worker: portrait_refresh_loop (every 60s, weekly scheduler trigger)
        ├─ pop portrait_queue
        ├─ read 4 months → format_portrait_text
        └─ embed → upsert user_portrait chunk in user_financial_chunks

User requests insight
        ├─ [sync]  → Insight(PENDING) + InsightRequested in outbox
        └─ [async] → Kafka yomochi.insights.v1

insight-worker: on_insight_event
        ├─ EmbeddingPipeline.refresh (ensures chunks are current)
        ├─ embed query → vector search: 3 monthly + 2 shift + portrait
        ├─ assess_quality → FULL / PARTIAL / NONE
        ├─ OpenAI gpt-4o (structured output) → title, description, impact_score
        └─ save Insight(COMPLETED) + BudgetSummarySnapshot

User reads alerts
        └─ SELECT user_alerts (already populated by embedding pipeline)

User chats
        ├─ embed question → vector search: portrait + 2 monthly + 2 shift
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
| `dirty_periods` | Queue for embedding refresh; unique (user_id, year, month) |
| `user_financial_chunks` | RAG chunks with pgvector embeddings (monthly_summary, behavioral_shift, user_portrait) |
| `insights` | Generated insights + budget_snapshot JSONB |
| `user_alerts` | Behavioral shift alerts (spending spike, income drop, etc.) |
| `portrait_queue` | Queue for portrait rebuild; one row per user |
| `chat_turns` | Chat history (role + chunks_used JSONB) |
| `outbox_events` | Transactional outbox → Kafka (status: PENDING / SENT / FAILED) |
| `recurring_rules` | Recurring transaction rules state machine |
| `audit_events` | Login, transaction CRUD, insight requests (partitioned by month) |
| `password_reset_tokens` | Short-lived tokens for password reset flow |

**Migration baseline:** Alembic ships a single squashed migration `000000000001_squash.py` (collapsed history as of 2026-06-07). The squash already includes the `outbox_events.trace_context JSONB` column from the cross-Kafka trace-propagation work and the `(user_id, created_at DESC, id DESC)` keyset index on `insights`. New schema changes append fresh revisions on top of the squash.

---

## 10. External dependencies

| Service | Usage |
|---------|-------|
| **OpenAI text-embedding-3-small** | All embeddings: monthly chunks, shift chunks, portrait, chat queries, search queries |
| **OpenAI gpt-4o** | Insight generation (structured output: title, description, impact_score) |
| **OpenAI gpt-4o-mini** | Chat (non-streaming + SSE), parse-text, receipt extraction |
| **Kafka** | TransactionCreated/Updated/Deleted, InsightRequested/Completed, DLQ |
| **Redis** | Sessions, rate limiting (IP + per-user chat), consumer idempotency, search cache, chat token budget, cached text embedder |
| **PostgreSQL 17 + pgvector** | Primary store + vector similarity search (cosine, HNSW index) |
