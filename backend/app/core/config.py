"""Configuración de la aplicación leída desde variables de entorno (y el archivo .env)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# El .env vive en la raíz del repositorio (un nivel por encima de backend/).
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    app_env: str = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
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

    # Embeddings. "fake" es un proveedor local determinista para pruebas y desarrollo sin clave.
    embeddings_provider: Literal["openai", "fake"] = "openai"
    # SecretStr evita que la clave aparezca si se imprime o se registra la configuración.
    openai_api_key: SecretStr | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_batch_size: int = Field(default=100, ge=1, le=2048)
    embedding_timeout_seconds: float = Field(default=30, gt=0)
    # El SDK de OpenAI reintenta con backoff exponencial ante 429, 5xx y timeouts.
    embedding_max_retries: int = Field(default=3, ge=0, le=10)

    # Búsqueda.
    max_query_chars: int = Field(default=1000, ge=10)
    retrieval_top_k: int = Field(default=5, ge=1)
    retrieval_max_top_k: int = Field(default=20, ge=1)
    # Similitud coseno mínima para aceptar un resultado vectorial (0-1). Valor inicial a
    # calibrar con el conjunto de evaluación (Fase 7).
    retrieval_min_score: float = Field(default=0.25, ge=0, le=1)

    # LLM que redacta las respuestas. "fake" = local y determinista, para pruebas.
    llm_provider: Literal["openai", "fake"] = "openai"
    llm_model: str = "gpt-6-luna"
    # gpt-6-luna es un modelo de razonamiento: más esfuerzo = más tokens (costo) y latencia.
    llm_reasoning_effort: Literal["none", "low", "medium", "high"] = "low"
    # Incluye los tokens de razonamiento; si se agota, la respuesta queda incompleta.
    llm_max_output_tokens: int = Field(default=2000, ge=100)
    llm_timeout_seconds: float = Field(default=60, gt=0)
    llm_max_retries: int = Field(default=2, ge=0, le=10)
    # Precios (USD por millón de tokens) solo para estimar el costo en los logs.
    llm_input_price_per_mtok: float = Field(default=0.10, ge=0)
    llm_output_price_per_mtok: float = Field(default=0.50, ge=0)

    # Contexto enviado al LLM: limita costo y evita diluir la respuesta con texto irrelevante.
    rag_max_context_chars: int = Field(default=8000, ge=500)
    # Cómo se eligen los fragmentos que lee el LLM (comparativa en docs/rag-evaluation.md):
    # - "simple": los RETRIEVAL_TOP_K primeros de la búsqueda.
    # - "rerank": la búsqueda trae RAG_RERANK_CANDIDATES y el LLM elige los RETRIEVAL_TOP_K
    #   más útiles (una llamada extra por pregunta).
    # - "progressive": prueba con los primeros RETRIEVAL_TOP_K; si no hay evidencia, con los
    #   siguientes, y después con el doble (hasta 3 llamadas al LLM).
    rag_strategy: Literal["simple", "rerank", "progressive"] = "rerank"
    rag_rerank_candidates: int = Field(default=20, ge=1, le=50)
    # Elegir fragmentos es más sencillo que redactar la respuesta: menos razonamiento = menos
    # latencia (ver la comparativa en docs/rag-evaluation.md).
    rag_rerank_reasoning_effort: Literal["none", "low", "medium", "high"] = "none"
    # Respuestas detalladas y por pasos: una segunda llamada comprueba cada afirmación contra
    # el texto de sus fuentes y elimina las que no estén respaldadas (ver services/rag.py).
    rag_verify_answers: bool = True

    # Resumen automático de cada documento al procesarlo (para preguntas tipo "¿de qué
    # trata?"). Si el documento es más largo, se envían fragmentos repartidos por todo él.
    summary_max_input_chars: int = Field(default=12000, ge=1000)
    summary_max_chars: int = Field(default=1500, ge=200)

    # Papelera: los documentos eliminados se pueden restaurar durante este tiempo; después se
    # borran del todo (registro, fragmentos y archivo). La comprobación se repite cada hora.
    trash_retention_days: int = Field(default=30, ge=1)
    trash_purge_interval_seconds: float = Field(default=3600, gt=0)

    @model_validator(mode="after")
    def _overlap_smaller_than_chunk(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP debe ser menor que CHUNK_SIZE")
        if self.retrieval_top_k > self.retrieval_max_top_k:
            raise ValueError("RETRIEVAL_TOP_K no puede superar RETRIEVAL_MAX_TOP_K")
        return self

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración. Se cachea para leer el entorno una sola vez."""
    return Settings()
