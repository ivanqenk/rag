"""Configuración de la aplicación leída desde variables de entorno (y el archivo .env)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# El .env vive en la raíz del repositorio (un nivel por encima de backend/).
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    app_env: str = "development"
    # Valor por defecto solo para desarrollo local con docker-compose.yml.
    database_url: str = "postgresql+psycopg://docintel:docintel@localhost:5432/docintel"

    # Carpeta donde se guardan los PDF subidos. No la sirve ningún endpoint.
    storage_dir: Path = REPO_ROOT / "backend" / "storage"
    max_upload_size_mb: int = Field(default=20, ge=1, le=200)
    # Evita que un PDF enorme bloquee el servidor durante el procesamiento síncrono.
    max_pdf_pages: int = Field(default=500, ge=1)

    # Fragmentación (en caracteres). Ver docs en app/services/chunking.py.
    chunk_size: int = Field(default=1000, ge=100)
    chunk_overlap: int = Field(default=200, ge=0)

    @model_validator(mode="after")
    def _overlap_smaller_than_chunk(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP debe ser menor que CHUNK_SIZE")
        return self

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración. Se cachea para leer el entorno una sola vez."""
    return Settings()
