import os

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from alembic.script import ScriptDirectory
from testcontainers.postgres import PostgresContainer

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="module")
def pg():
    with PostgresContainer("pgvector/pgvector:pg16") as container:
        yield container


def _make_alembic_cfg(db_url: str) -> Config:
    cfg = Config(os.path.join(_ROOT, "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _get_revisions(cfg: Config) -> list[str]:
    script = ScriptDirectory.from_config(cfg)
    revisions = [rev.revision for rev in script.walk_revisions()]
    revisions.reverse()  # oldest first → newest last
    return revisions


def test_stairway(pg: PostgresContainer) -> None:
    """For each revision: upgrade to it, downgrade one step, upgrade again."""
    sync_url = pg.get_connection_url()
    # Convert psycopg2 URL to asyncpg URL for use with env.py's async migrations
    async_url = sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    cfg = _make_alembic_cfg(async_url)
    revisions = _get_revisions(cfg)

    assert revisions, "No migrations found"

    for revision in revisions:
        alembic_command.upgrade(cfg, revision)
        alembic_command.downgrade(cfg, "-1")
        alembic_command.upgrade(cfg, revision)
