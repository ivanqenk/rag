"""Configuración de la aplicación leída desde variables de entorno (y el archivo .env)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# El .env vive en la raíz del repositorio (un nivel por encima de backend/).
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    app_env: str = "development"
    # Valor por defecto solo para desarrollo local con docker-compose.yml.
    database_url: str = "postgresql+psycopg://docintel:docintel@localhost:5432/docintel"


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración. Se cachea para leer el entorno una sola vez."""
    return Settings()
