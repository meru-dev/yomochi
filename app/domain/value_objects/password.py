from dataclasses import dataclass

from app.domain.exceptions.domain_errors import WeakPasswordError

_MIN_LENGTH = 8
# bcrypt silently truncates input beyond 72 bytes; reject early to avoid silent data loss
_MAX_LENGTH = 72


@dataclass(frozen=True, slots=True, repr=False)
class RawPassword:
    value: str

    def __post_init__(self) -> None:
        if len(self.value) < _MIN_LENGTH:
            raise WeakPasswordError(f"Password must be at least {_MIN_LENGTH} characters")
        if len(self.value) > _MAX_LENGTH:
            raise WeakPasswordError(f"Password must be at most {_MAX_LENGTH} characters")

    def __repr__(self) -> str:
        return "RawPassword(***)"

    def __str__(self) -> str:
        return "***"


@dataclass(frozen=True, slots=True)
class UserPasswordHash:
    value: str

    def __str__(self) -> str:
        return self.value
