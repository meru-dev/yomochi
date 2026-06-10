class EntityMixin:
    # Subclasses must define `id_`. Equality and hashing are identity-based.
    def __eq__(self, other: object) -> bool:
        if type(self) is not type(other):
            return NotImplemented
        return bool(self.id_ == other.id_)  # type: ignore[attr-defined]

    def __hash__(self) -> int:
        return hash((type(self), self.id_))  # type: ignore[attr-defined]

    def __setattr__(self, name: str, value: object) -> None:
        if name == "id_" and "id_" in self.__dict__:
            msg = "id_ is immutable after construction"
            raise AttributeError(msg)
        object.__setattr__(self, name, value)
