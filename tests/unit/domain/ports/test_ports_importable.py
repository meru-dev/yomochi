import pytest

from app.domain.ports import (  # noqa: F401 — smoke: verify all ports import cleanly
    CategoryIdGenerator,
    InsightIdGenerator,
    PasswordHasher,
    TransactionIdGenerator,
    UserIdGenerator,
)
from app.domain.value_objects import RawPassword, UserPasswordHash
from tests.fakes.id_generator import (
    FakeCategoryIdGenerator,
    FakeInsightIdGenerator,
    FakeTransactionIdGenerator,
    FakeUserIdGenerator,
)
from tests.fakes.password_hasher import PlaintextHasher


def test_fake_user_id_generator_returns_user_id() -> None:
    gen = FakeUserIdGenerator()
    uid = gen()
    assert str(uid)


def test_fake_generators_return_distinct_ids_by_default() -> None:
    gen = FakeTransactionIdGenerator()
    assert gen() != gen()


def test_fake_generators_return_fixed_id_when_set() -> None:
    import uuid

    fixed = uuid.uuid4()
    gen = FakeCategoryIdGenerator(fixed=fixed)
    assert gen() == gen()


def test_fake_insight_id_generator() -> None:
    gen = FakeInsightIdGenerator()
    result = gen()
    assert result is not None


@pytest.mark.asyncio
async def test_plaintext_hasher_round_trip() -> None:
    hasher = PlaintextHasher()
    pw = RawPassword("correcthorse")

    hashed = await hasher.hash(pw)

    assert isinstance(hashed, UserPasswordHash)
    assert await hasher.verify(pw, hashed) is True
    assert await hasher.verify(RawPassword("wrongpassword"), hashed) is False


def test_search_ports_importable() -> None:
    from app.application.search.ports.search_cache import SearchCache  # noqa: F401
    from app.application.search.ports.transaction_reader import TransactionReader  # noqa: F401
    from app.application.search.ports.transaction_searcher import TransactionSearcher  # noqa: F401


def test_consumer_owned_ports_importable() -> None:
    """Smoke: ports introduced 2026-05-25 to retire cross-BC imports."""
    from app.application.common.ports.user_plan_lookup import UserPlanLookup  # noqa: F401
    from app.application.transactions.ports.category_list_reader import (  # noqa: F401
        CategoryListItem,
        CategoryListReader,
    )
    from app.application.transactions.ports.dirty_period_marker import (  # noqa: F401
        DirtyPeriodMarker,
    )

    # Adapters
    from app.outbound.adapters.sqla.transactions.category_list_reader import (  # noqa: F401
        SqlaCategoryListReader,
    )
    from app.outbound.adapters.sqla.transactions.dirty_period_marker import (  # noqa: F401
        SqlaDirtyPeriodMarker,
    )
    from app.outbound.adapters.sqla.users.user_plan_lookup import (  # noqa: F401
        SqlaUserPlanLookup,
    )
