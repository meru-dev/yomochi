from dataclasses import dataclass, field
from datetime import datetime

from app.domain.entities.base import EntityMixin
from app.domain.value_objects.email import Email
from app.domain.value_objects.enums import Plan
from app.domain.value_objects.ids import UserId
from app.domain.value_objects.password import UserPasswordHash


@dataclass(eq=False)
class User(EntityMixin):
    id_: UserId
    email: Email
    password_hash: UserPasswordHash
    created_at: datetime
    plan: Plan = field(default=Plan.FREE)

    def change_password(self, new_hash: UserPasswordHash) -> None:
        self.password_hash = new_hash
