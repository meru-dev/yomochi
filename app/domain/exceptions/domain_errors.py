class DomainError(Exception):
    pass


class InvalidEmailError(DomainError):
    def __init__(self, value: str) -> None:
        super().__init__(f"Invalid email address: {value!r}")


class InvalidCurrencyError(DomainError):
    def __init__(self, code: str) -> None:
        super().__init__(f"Unknown ISO 4217 currency code: {code!r}")


class InvalidMoneyError(DomainError):
    pass


class WeakPasswordError(DomainError):
    pass


class InvalidTransactionTextError(DomainError):
    pass


class CategoryNameAlreadyExistsError(DomainError):
    def __init__(self, name: str = "") -> None:
        msg = f"Category name already exists: {name!r}" if name else "Category name already exists"
        super().__init__(msg)


class InvalidCursorError(DomainError):
    pass


class InvalidRecurrenceScheduleError(DomainError):
    pass


class CategoryParentNotFoundError(DomainError):
    def __init__(self, parent_id: str = "") -> None:
        msg = (
            f"Parent category not found: {parent_id!r}"
            if parent_id
            else "Parent category not found"
        )
        super().__init__(msg)


class CategoryParentIsLeafError(DomainError):
    def __init__(self, parent_id: str = "") -> None:
        msg = (
            f"Parent category is a leaf, not a group: {parent_id!r}"
            if parent_id
            else "Parent category is a leaf"
        )
        super().__init__(msg)


class CategoryTypeMismatchError(DomainError):
    def __init__(self) -> None:
        super().__init__("Leaf category type must match parent category type")


class CategoryIsGroupError(DomainError):
    def __init__(self, category_id: str = "") -> None:
        msg = (
            f"Cannot assign a group category to a transaction: {category_id!r}"
            if category_id
            else "Cannot assign a group category to a transaction"
        )
        super().__init__(msg)


class FileTooLargeError(DomainError):
    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes
        super().__init__(f"Upload of {size_bytes} bytes exceeds limit of {max_bytes} bytes")
