"""Conexión a la base de datos y sesiones por petición."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

# El engine mantiene un pool de conexiones; se crea una sola vez por proceso.
# pool_pre_ping descarta conexiones caídas (p. ej. si PostgreSQL se reinició).
engine = create_engine(get_settings().database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: abre una sesión por petición y la cierra al terminar."""
    with SessionLocal() as session:
        yield session
