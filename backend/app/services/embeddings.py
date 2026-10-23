"""Proveedores de embeddings detrás de una interfaz pequeña.

Un embedding es una lista de números que representa el significado de un texto: textos con
significado parecido producen vectores cercanos. La interfaz permite cambiar de proveedor
sin tocar la ingestión ni la búsqueda (ver docs/decisions/0001-proveedor-embeddings.md).
"""

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Annotated, Protocol

import openai
from fastapi import Depends, HTTPException, status

from app.core.config import Settings, get_settings
from app.models.document_chunk import EMBEDDING_DIMENSIONS


class EmbeddingError(Exception):
    """Fallo del proveedor. `message` es apto para mostrarse al usuario."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class EmbeddingProvider(Protocol):
    # Se guarda junto a cada vector: vectores de modelos distintos no son comparables.
    model_name: str

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        batch_size: int,
        timeout_seconds: float,
        max_retries: int,
    ) -> None:
        self.model_name = model
        self._batch_size = batch_size
        self._client = openai.OpenAI(
            api_key=api_key, timeout=timeout_seconds, max_retries=max_retries
        )

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        # Por lotes: menos peticiones (y menos riesgo de rate limit) que una por fragmento.
        for start in range(0, len(texts), self._batch_size):
            vectors.extend(self._embed_batch(texts[start : start + self._batch_size]))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed_batch([text])[0]

    def _embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            response = self._client.embeddings.create(
                model=self.model_name, input=list(texts), dimensions=EMBEDDING_DIMENSIONS
            )
        except openai.AuthenticationError as exc:
            raise EmbeddingError(
                "La clave de API del proveedor de embeddings no es válida."
            ) from exc
        except openai.OpenAIError as exc:
            # Incluye timeouts, rate limits y errores 5xx (tras agotar los reintentos del SDK).
            raise EmbeddingError(
                "El proveedor de embeddings no está disponible. Inténtalo más tarde."
            ) from exc

        # La API devuelve un `index` por resultado; ordenamos por él en vez de asumir el orden.
        vectors = [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
        if len(vectors) != len(texts) or any(len(v) != EMBEDDING_DIMENSIONS for v in vectors):
            raise EmbeddingError("El proveedor de embeddings devolvió una respuesta inesperada.")
        return vectors


class FakeEmbeddingProvider:
    """Proveedor local y determinista para pruebas: no llama a ninguna API ni cuesta dinero.

    Usa el "hashing trick": cada palabra suma en una posición del vector elegida por su hash.
    No entiende sinónimos, pero textos que comparten palabras quedan cerca, lo suficiente
    para probar la búsqueda de punta a punta. Cada palabra cuenta una sola vez y se ignoran
    las de menos de 4 letras ("de", "con", "el"…): si no, dominarían la similitud y textos
    sin relación parecerían cercanos, algo que un modelo real no hace.
    """

    model_name = "fake-hashing-v2"

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIMENSIONS
        for word in set(re.findall(r"\w{4,}", text.lower())):
            digest = hashlib.sha256(word.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
            vector[index] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            # Un vector de ceros no tiene dirección y la similitud coseno sería indefinida.
            vector[0] = 1.0
            return vector
        return [value / norm for value in vector]


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embeddings_provider == "fake":
        return FakeEmbeddingProvider()
    # Una línea `OPENAI_API_KEY=` vacía en .env cuenta como no configurada.
    if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value():
        raise EmbeddingError(
            "El proveedor de embeddings no está configurado (falta OPENAI_API_KEY)."
        )
    return OpenAIEmbeddingProvider(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.embedding_model,
        batch_size=settings.embedding_batch_size,
        timeout_seconds=settings.embedding_timeout_seconds,
        max_retries=settings.embedding_max_retries,
    )


def get_embedding_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EmbeddingProvider:
    """Dependencia de FastAPI. Las pruebas la sustituyen por FakeEmbeddingProvider."""
    try:
        return build_embedding_provider(settings)
    except EmbeddingError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, exc.message) from None
