from dataclasses import dataclass
from uuid import uuid4

import pytest

from app.domain.entities.base import EntityMixin
from app.domain.value_objects.ids import UserId


@dataclass(eq=False)
class _Sample(EntityMixin):
    id_: UserId
    name: str


@dataclass(eq=False)
class _Other(EntityMixin):
    id_: UserId
    name: str


class TestIdentitySemantics:
    def test_equal_when_same_id_and_class(self) -> None:
        uid = UserId(uuid4())
        a = _Sample(id_=uid, name="a")
        b = _Sample(id_=uid, name="b")  # name differs, id same
        assert a == b
        assert hash(a) == hash(b)

    def test_not_equal_across_entity_types_with_same_id(self) -> None:
        uid = UserId(uuid4())
        a = _Sample(id_=uid, name="a")
        b = _Other(id_=uid, name="a")
        # Different concrete classes => not equal even with same id_
        assert a != b
        assert hash(a) != hash(b)


class TestIdImmutability:
    def test_id_reassignment_rejected(self) -> None:
        e = _Sample(id_=UserId(uuid4()), name="a")
        with pytest.raises(AttributeError, match="id_ is immutable"):
            e.id_ = UserId(uuid4())

    def test_other_fields_still_mutable(self) -> None:
        e = _Sample(id_=UserId(uuid4()), name="a")
        e.name = "b"
        assert e.name == "b"
