import pytest


# The insight-DLQ kill-test exercises only the Redis-backed failure counter +
# idempotency store; it needs no Postgres. Override the parent integration
# conftest's autouse `truncate_tables` (which pulls in postgres_url + migrations)
# with a no-op so these tests run against Redis alone.
@pytest.fixture(autouse=True)
async def truncate_tables() -> None:
    return
