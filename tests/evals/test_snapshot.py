from __future__ import annotations

from tests.evals.snapshot import SnapshotStore, snapshot_key


def test_key_is_stable_for_same_inputs() -> None:
    k1 = snapshot_key(prompt="hello", model="gpt-4o-mini", inputs={"a": 1, "b": 2})
    k2 = snapshot_key(prompt="hello", model="gpt-4o-mini", inputs={"b": 2, "a": 1})
    assert k1 == k2


def test_key_changes_when_prompt_changes() -> None:
    k1 = snapshot_key(prompt="hello", model="gpt-4o-mini", inputs={})
    k2 = snapshot_key(prompt="HELLO", model="gpt-4o-mini", inputs={})
    assert k1 != k2


def test_key_is_16_hex_chars() -> None:
    k = snapshot_key(prompt="x", model="x", inputs={})
    assert len(k) == 16
    assert all(c in "0123456789abcdef" for c in k)


def test_snapshot_store_roundtrip(tmp_path) -> None:
    store = SnapshotStore(root=tmp_path, component="insights")
    from tests.evals.snapshot import SnapshotRecord

    record = SnapshotRecord(
        key="abcdef0123456789",
        prompt="x",
        model="gpt-4o-mini",
        request_kwargs={"temperature": 0},
        response={"title": "t", "description": "d", "impact_score": 5},
        tokens_prompt=100,
        tokens_completion=50,
        cost_usd=0.001,
        captured_at=SnapshotStore.now_iso(),
    )
    store.save(record)
    loaded = store.load("abcdef0123456789")
    assert loaded == record


def test_snapshot_store_returns_none_on_miss(tmp_path) -> None:
    store = SnapshotStore(root=tmp_path, component="insights")
    assert store.load("missing") is None
