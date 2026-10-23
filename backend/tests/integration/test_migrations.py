from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect

import app.models  # noqa: F401  (registra las tablas en Base.metadata)
from app.db.base import Base
from tests.integration.conftest import make_alembic_config


def test_migrations_can_be_reapplied_from_scratch(engine: Engine) -> None:
    config = make_alembic_config()

    command.downgrade(config, "base")
    assert "documents" not in inspect(engine).get_table_names()

    command.upgrade(config, "head")
    assert "documents" in inspect(engine).get_table_names()


def test_models_match_migrations(engine: Engine) -> None:
    """Si alguien cambia un modelo y olvida crear la migración, esta prueba falla."""
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)

    assert diff == []
