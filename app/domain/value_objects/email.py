import re
from dataclasses import dataclass

from app.domain.exceptions.domain_errors import InvalidEmailError

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True, slots=True, repr=False)
class Email:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        object.__setattr__(self, "value", normalized)
        if not _EMAIL_RE.match(normalized):
            raise InvalidEmailError(normalized)

    def __repr__(self) -> str:
        return "Email(***)"

    def __str__(self) -> str:
        return self.value
