"""
Transaction outbox + consumer integration tests removed in arch-simplification task 1.

The transaction-worker and its Kafka path (yomochi.transactions.v1) were deleted.
dirty_periods is now marked synchronously inside the API DB transaction, making
the Kafka consumer redundant. No outbox events are emitted for Transaction* events.

Outbox relay for insight events is tested in test_e2e_insight_flow.py.
"""
