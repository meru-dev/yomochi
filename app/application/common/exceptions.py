class StorageError(Exception):
    """Raised when a persistence operation fails unexpectedly.

    Wraps SQLAlchemy (and future adapter) exceptions so infrastructure
    details don't propagate beyond the outbound layer.
    """
