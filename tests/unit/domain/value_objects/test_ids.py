import uuid

from app.domain.value_objects.ids import CategoryId, InsightId, TransactionId, UserId


def test_all_ids_str() -> None:
    uid = uuid.uuid4()
    assert str(UserId(uid)) == str(uid)
    assert str(TransactionId(uid)) == str(uid)
    assert str(CategoryId(uid)) == str(uid)
    assert str(InsightId(uid)) == str(uid)


def test_transaction_id_equality() -> None:
    uid = uuid.uuid4()
    assert TransactionId(uid) == TransactionId(uid)
    assert TransactionId(uid) != TransactionId(uuid.uuid4())


def test_ids_are_not_interchangeable() -> None:
    uid = uuid.uuid4()
    mixed: set[object] = {UserId(uid), TransactionId(uid), CategoryId(uid), InsightId(uid)}
    assert len(mixed) == 4


def test_id_is_hashable() -> None:
    uid = uuid.uuid4()
    s = {UserId(uid), UserId(uid)}
    assert len(s) == 1
