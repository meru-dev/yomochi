import pytest
from pydantic import ValidationError

from app.main.config.settings import AuthSettings, DatabaseSettings


def test_jwt_secret_required_when_empty():
    """AuthSettings must raise if jwt_secret is empty string."""
    with pytest.raises((ValidationError, ValueError)):
        AuthSettings(jwt_secret="", _env_file=None)


def test_auth_settings_valid_with_secret():
    """AuthSettings works when jwt_secret is provided."""
    s = AuthSettings(jwt_secret="a-real-secret-that-is-long-enough", _env_file=None)
    assert s.cookie_name == "auth"
    assert s.session_expire_minutes == 60 * 24 * 30


def test_auth_settings_defaults():
    """AuthSettings can be created with only jwt_secret override.

    The secret must be ≥ 32 bytes per RFC 7518 §3.2 for HS256, so the override
    has to satisfy the validator in addition to being non-empty.
    """
    s = AuthSettings(jwt_secret="a" * 32, _env_file=None)
    assert s.cookie_name == "auth"
    assert s.session_expire_minutes == 60 * 24 * 30


def test_database_pool_defaults_are_explicit() -> None:
    """Pool settings must have production-safe defaults, not SQLAlchemy's hidden 5."""
    cfg = DatabaseSettings(database_url="postgresql+asyncpg://u:p@localhost/db")
    assert cfg.db_pool_size == 10
    assert cfg.db_max_overflow == 5
    assert cfg.db_pool_recycle_seconds == 1800
