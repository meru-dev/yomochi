from datetime import date, datetime
from uuid import UUID

from app.application.common.outbox_event import OutboxEvent
from app.application.transactions.ports.category_list_reader import CategoryListItem
from app.application.users.audit_event import AuditEvent
from app.application.users.password_reset_token import PasswordResetToken
from app.application.users.session import Session
from app.domain.entities.category import Category
from app.domain.entities.transaction import Transaction
from app.domain.entities.user import User
from app.domain.value_objects.email import Email
from app.domain.value_objects.ids import (
    CategoryId,
    PasswordResetTokenId,
    SessionId,
    TransactionId,
    UserId,
)


class FakeUserRepository:
    def __init__(self) -> None:
        self._store: dict[UserId, User] = {}

    async def save(self, user: User) -> None:
        self._store[user.id_] = user

    async def get_by_id(self, user_id: UserId) -> User | None:
        return self._store.get(user_id)

    async def get_by_email(self, email: Email) -> User | None:
        return next((u for u in self._store.values() if u.email == email), None)


class FakeSessionStore:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], Session] = {}
        self._revoked: set[str] = set()

    async def save(self, session: Session) -> None:
        key = (str(session.id_), str(session.user_id))
        self._store[key] = session

    async def get(self, session_id: SessionId, user_id: UserId) -> Session | None:
        if str(session_id) in self._revoked:
            return None
        return self._store.get((str(session_id), str(user_id)))

    async def revoke(self, session_id: SessionId, user_id: UserId) -> None:
        self._revoked.add(str(session_id))
        self._store.pop((str(session_id), str(user_id)), None)

    async def list_active(self, user_id: UserId) -> list[Session]:
        return [s for s in self._store.values() if s.user_id == user_id]

    async def revoke_all(self, user_id: UserId) -> None:
        keys = [k for k, s in self._store.items() if s.user_id == user_id]
        for k in keys:
            self._revoked.add(k[0])
            del self._store[k]


class FakeAuditLog:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def record(self, event: AuditEvent) -> None:
        self.events.append(event)


class FakePasswordResetTokenStore:
    def __init__(self) -> None:
        self._store: dict[str, PasswordResetToken] = {}

    async def save(self, token: PasswordResetToken) -> None:
        self._store[token.token_hash] = token

    async def get_valid(self, token_hash: str) -> PasswordResetToken | None:
        from datetime import UTC, datetime

        token = self._store.get(token_hash)
        if token is None or token.expires_at < datetime.now(UTC):
            return None
        return token

    async def invalidate(self, token_id: PasswordResetTokenId) -> None:
        self._store = {h: t for h, t in self._store.items() if t.id_ != token_id}


class FakeTransactionRepository:
    def __init__(self) -> None:
        self._store: dict[TransactionId, Transaction] = {}

    async def save(self, transaction: Transaction) -> None:
        self._store[transaction.id_] = transaction

    async def get_by_id(self, transaction_id: TransactionId, user_id: UserId) -> Transaction | None:
        tx = self._store.get(transaction_id)
        if tx is None or tx.user_id != user_id:
            return None
        return tx

    async def list_by_user(
        self,
        user_id: UserId,
        limit: int,
        cursor: tuple[date, datetime, UUID] | None,
        type_filter: str | None = None,
        currency_filter: str | None = None,
        category_id_filter: str | None = None,
    ) -> list[Transaction]:
        from uuid import UUID as _UUID

        owned = [tx for tx in self._store.values() if tx.user_id == user_id]
        owned.sort(key=lambda tx: (tx.date, tx.created_at, tx.id_.value), reverse=True)
        if cursor is not None:
            cursor_date, cursor_created_at, cursor_id = cursor
            owned = [
                tx
                for tx in owned
                if (tx.date, tx.created_at, tx.id_.value)
                < (cursor_date, cursor_created_at, cursor_id)
            ]
        if type_filter is not None:
            owned = [tx for tx in owned if tx.type_.value == type_filter]
        if currency_filter is not None:
            owned = [tx for tx in owned if tx.amount.currency.code == currency_filter]
        if category_id_filter is not None:
            target = _UUID(category_id_filter)
            owned = [
                tx for tx in owned if tx.category_id is not None and tx.category_id.value == target
            ]
        return owned[:limit]

    async def get_by_ids(self, ids: list[TransactionId], user_id: UserId) -> list[Transaction]:
        result = []
        for tid in ids:
            tx = self._store.get(tid)
            if tx is not None and tx.user_id == user_id:
                result.append(tx)
        return result

    async def delete(self, transaction_id: TransactionId, user_id: UserId) -> bool:
        tx = self._store.get(transaction_id)
        if tx is None or tx.user_id != user_id:
            return False
        del self._store[transaction_id]
        return True

    async def count_created_in_month(self, user_id: UserId, year: int, month: int) -> int:
        return sum(
            1
            for tx in self._store.values()
            if tx.user_id == user_id and tx.created_at.year == year and tx.created_at.month == month
        )


class FakeCategoryRepository:
    def __init__(self) -> None:
        self._store: dict[CategoryId, Category] = {}

    async def save(self, category: Category) -> None:
        self._store[category.id_] = category

    async def get_by_id(self, id_: CategoryId) -> Category | None:
        return self._store.get(id_)

    async def get_user_category_by_name(self, user_id: UserId, name: str) -> Category | None:
        return next(
            (c for c in self._store.values() if c.user_id == user_id and c.name == name),
            None,
        )

    async def list_for_user(self, user_id: UserId) -> list[Category]:
        result = [c for c in self._store.values() if c.is_system or c.user_id == user_id]
        result.sort(key=lambda c: (not c.is_system, c.name))
        return result


class FakeCategoryListReader:
    def __init__(self) -> None:
        self._items: list[CategoryListItem] = []

    def seed(self, items: list[CategoryListItem]) -> None:
        self._items = items

    async def list_for_user(self, user_id: UserId) -> list[CategoryListItem]:
        return list(self._items)

    async def get_by_id_for_user(
        self, category_id: CategoryId, user_id: UserId
    ) -> CategoryListItem | None:
        return next((i for i in self._items if i.id_ == str(category_id)), None)


class FakeOutboxRepository:
    def __init__(self) -> None:
        self.events: list[OutboxEvent] = []

    async def append(self, event: OutboxEvent) -> None:
        self.events.append(event)


class FakeFlusher:
    async def flush(self) -> None:
        pass


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_password_reset(self, to: Email, token: str, expires_at: object) -> None:
        self.sent.append((str(to), token))
