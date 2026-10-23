"""Fixtures de integración: usan un PostgreSQL real (base `docintel_test`).

Requieren `docker compose up -d db`. Si PostgreSQL no responde, las pruebas se marcan
como SKIPPED con el motivo, en lugar de fallar con un error de conexión confuso.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://docintel:docintel@localhost:5432/docintel_test",
)
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def make_alembic_config() -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return config


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    engine = create_engine(TEST_DATABASE_URL)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip(f"PostgreSQL no disponible en {engine.url.render_as_string()}")

    # Esquema desde cero con las migraciones reales (no con create_all), para probarlas.
    config = make_alembic_config()
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    with Session(engine, expire_on_commit=False) as session:
        yield session
    # Cada prueba empieza con tablas vacías.
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE documents"))


@pytest.fixture
def client(engine: Engine, db_session: Session) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
