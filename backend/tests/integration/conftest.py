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
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.session import get_db, get_session_factory
from app.main import app
from app.services.embeddings import FakeEmbeddingProvider, get_embedding_provider
from app.services.limits import SlidingWindowLimiter, get_rate_limiter
from app.services.llm import FakeLLMProvider, get_llm_provider, get_optional_llm_provider

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
        connection.execute(text("TRUNCATE documents, document_chunks, folders, usage_daily"))


@pytest.fixture
def storage_dir(tmp_path: Path) -> Path:
    return tmp_path / "storage"


@pytest.fixture
def settings(storage_dir: Path) -> Settings:
    return Settings(
        storage_dir=storage_dir,
        max_upload_size_mb=1,
        chunk_size=500,
        chunk_overlap=100,
        embeddings_provider="fake",
        llm_provider="fake",
        # Calibrado para el proveedor falso con los textos de test_search.py: las consultas
        # relevantes dan >= 0.27 y las colisiones de hash entre palabras distintas <= 0.15.
        retrieval_min_score=0.2,
        # La mayoría de las pruebas comprueban el resultado del procesamiento en la propia
        # respuesta; el modo en segundo plano tiene sus pruebas (test_background_processing.py).
        processing_mode="sync",
    )


@pytest.fixture
def embedder() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider()


@pytest.fixture
def llm() -> FakeLLMProvider:
    return FakeLLMProvider()


@pytest.fixture
def client(
    engine: Engine,
    db_session: Session,
    settings: Settings,
    embedder: FakeEmbeddingProvider,
    llm: FakeLLMProvider,
) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: sessionmaker(
        bind=engine, expire_on_commit=False
    )
    app.dependency_overrides[get_settings] = lambda: settings
    # Un limitador nuevo por prueba: los contadores no se arrastran de una a otra.
    limiter = SlidingWindowLimiter()
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    # Nunca llamar a un proveedor real (de pago) desde la suite, aunque .env tenga una clave.
    app.dependency_overrides[get_embedding_provider] = lambda: embedder
    app.dependency_overrides[get_llm_provider] = lambda: llm
    app.dependency_overrides[get_optional_llm_provider] = lambda: llm
    yield TestClient(app)
    app.dependency_overrides.clear()
