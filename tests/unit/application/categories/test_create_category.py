import uuid
from datetime import UTC, datetime

import pytest

from app.application.categories.use_cases.create_category import (
    CreateCategoryCommand,
    CreateCategoryUseCase,
)
from app.domain.entities.category import Category
from app.domain.exceptions.domain_errors import (
    CategoryNameAlreadyExistsError,
    CategoryParentIsLeafError,
    CategoryParentNotFoundError,
    CategoryTypeMismatchError,
)
from app.domain.value_objects.enums import CategoryType
from app.domain.value_objects.ids import CategoryId, UserId
from tests.fakes.id_generator import FakeCategoryIdGenerator
from tests.fakes.repositories import FakeCategoryRepository, FakeFlusher


def _make_uc(repo: FakeCategoryRepository) -> CreateCategoryUseCase:
    return CreateCategoryUseCase(
        category_repo=repo,
        flusher=FakeFlusher(),
        id_generator=FakeCategoryIdGenerator(),
    )


def _make_group(
    repo: FakeCategoryRepository,
    user_id: UserId,
    type_: CategoryType = CategoryType.EXPENSE,
) -> Category:
    group = Category(
        id_=CategoryId(uuid.uuid4()),
        name="Food & Drink",
        icon=None,
        color=None,
        is_system=True,
        user_id=None,
        parent_id=None,
        type=type_,
        created_at=datetime.now(UTC),
    )
    repo._store[group.id_] = group
    return group


async def test_creates_group_category() -> None:
    repo = FakeCategoryRepository()
    uc = _make_uc(repo)
    user = UserId(uuid.uuid4())

    result = await uc(
        CreateCategoryCommand(user_id=user, name="My group", type=CategoryType.EXPENSE)
    )

    cat = (await repo.list_for_user(user))[0]
    assert cat.name == "My group"
    assert cat.is_group is True
    assert cat.type == CategoryType.EXPENSE
    assert result.category_id == str(cat.id_)


async def test_creates_leaf_under_group() -> None:
    repo = FakeCategoryRepository()
    uc = _make_uc(repo)
    user = UserId(uuid.uuid4())
    group = _make_group(repo, user)

    await uc(
        CreateCategoryCommand(
            user_id=user,
            name="Groceries",
            type=CategoryType.EXPENSE,
            parent_id=group.id_,
        )
    )

    cats = await repo.list_for_user(user)
    leaf = next(c for c in cats if c.name == "Groceries")
    assert leaf.is_leaf is True
    assert leaf.parent_id == group.id_


async def test_raises_when_parent_not_found() -> None:
    repo = FakeCategoryRepository()
    uc = _make_uc(repo)
    user = UserId(uuid.uuid4())
    nonexistent = CategoryId(uuid.uuid4())

    with pytest.raises(CategoryParentNotFoundError):
        await uc(
            CreateCategoryCommand(
                user_id=user,
                name="X",
                type=CategoryType.EXPENSE,
                parent_id=nonexistent,
            )
        )


async def test_raises_when_parent_is_leaf() -> None:
    repo = FakeCategoryRepository()
    uc = _make_uc(repo)
    user = UserId(uuid.uuid4())
    group = _make_group(repo, user)

    leaf = Category(
        id_=CategoryId(uuid.uuid4()),
        name="Existing Leaf",
        icon=None,
        color=None,
        is_system=False,
        user_id=user,
        parent_id=group.id_,
        type=CategoryType.EXPENSE,
        created_at=datetime.now(UTC),
    )
    repo._store[leaf.id_] = leaf

    with pytest.raises(CategoryParentIsLeafError):
        await uc(
            CreateCategoryCommand(
                user_id=user,
                name="Child of leaf",
                type=CategoryType.EXPENSE,
                parent_id=leaf.id_,
            )
        )


async def test_raises_on_type_mismatch() -> None:
    repo = FakeCategoryRepository()
    uc = _make_uc(repo)
    user = UserId(uuid.uuid4())
    group = _make_group(repo, user, type_=CategoryType.INCOME)

    with pytest.raises(CategoryTypeMismatchError):
        await uc(
            CreateCategoryCommand(
                user_id=user,
                name="Leaf",
                type=CategoryType.EXPENSE,
                parent_id=group.id_,
            )
        )


async def test_raises_on_duplicate_name() -> None:
    repo = FakeCategoryRepository()
    uc = _make_uc(repo)
    user = UserId(uuid.uuid4())

    await uc(CreateCategoryCommand(user_id=user, name="My gym", type=CategoryType.EXPENSE))

    with pytest.raises(CategoryNameAlreadyExistsError):
        await uc(CreateCategoryCommand(user_id=user, name="My gym", type=CategoryType.EXPENSE))


async def test_same_name_allowed_for_different_users() -> None:
    repo = FakeCategoryRepository()
    user_a = UserId(uuid.uuid4())
    user_b = UserId(uuid.uuid4())

    await _make_uc(repo)(
        CreateCategoryCommand(user_id=user_a, name="My gym", type=CategoryType.EXPENSE)
    )
    await _make_uc(repo)(
        CreateCategoryCommand(user_id=user_b, name="My gym", type=CategoryType.EXPENSE)
    )

    assert len(await repo.list_for_user(user_a)) == 1
    assert len(await repo.list_for_user(user_b)) == 1
