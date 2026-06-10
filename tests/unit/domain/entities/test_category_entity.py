import uuid
from datetime import UTC, datetime

import pytest

from app.domain.entities.category import Category
from app.domain.exceptions.domain_errors import CategoryIsGroupError, CategoryParentIsLeafError
from app.domain.value_objects.enums import CategoryType
from app.domain.value_objects.ids import CategoryId, UserId


def _make_category(parent_id: CategoryId | None = None) -> Category:
    return Category(
        id_=CategoryId(uuid.uuid4()),
        name="Test",
        icon=None,
        color=None,
        is_system=False,
        user_id=UserId(uuid.uuid4()),
        parent_id=parent_id,
        type=CategoryType.EXPENSE,
        created_at=datetime.now(UTC),
    )


def test_category_with_no_parent_is_group() -> None:
    cat = _make_category(parent_id=None)
    assert cat.is_group is True
    assert cat.is_leaf is False


def test_category_with_parent_is_leaf() -> None:
    parent_id = CategoryId(uuid.uuid4())
    cat = _make_category(parent_id=parent_id)
    assert cat.is_leaf is True
    assert cat.is_group is False


def test_group_validate_assignable_raises() -> None:
    group = _make_category(parent_id=None)
    with pytest.raises(CategoryIsGroupError):
        group.validate_assignable()


def test_leaf_validate_assignable_passes() -> None:
    leaf = _make_category(parent_id=CategoryId(uuid.uuid4()))
    leaf.validate_assignable()  # must not raise


def test_leaf_validate_can_be_parent_raises() -> None:
    leaf = _make_category(parent_id=CategoryId(uuid.uuid4()))
    with pytest.raises(CategoryParentIsLeafError):
        leaf.validate_can_be_parent()


def test_group_validate_can_be_parent_passes() -> None:
    group = _make_category(parent_id=None)
    group.validate_can_be_parent()  # must not raise
