"""Prueba contra la API real de OpenAI. Cuesta dinero (fracciones de centavo).

No se ejecuta con `pytest`; solo con `uv run pytest -m openai` y OPENAI_API_KEY en .env.
"""

import pytest

from app.core.config import get_settings
from app.models.document_chunk import EMBEDDING_DIMENSIONS
from app.services.embeddings import OpenAIEmbeddingProvider, build_embedding_provider

pytestmark = pytest.mark.openai


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_real_openai_embeddings_capture_meaning() -> None:
    settings = get_settings().model_copy(update={"embeddings_provider": "openai"})
    if settings.openai_api_key is None:
        pytest.skip("OPENAI_API_KEY no está configurada en .env")
    provider = build_embedding_provider(settings)
    assert isinstance(provider, OpenAIEmbeddingProvider)

    query = provider.embed_query("¿Cuántos días de vacaciones tengo al año?")
    related, unrelated = provider.embed_documents(
        [
            "El empleado dispone de veintidós días hábiles de descanso anual.",
            "La impresora del tercer piso está averiada.",
        ]
    )

    assert len(query) == EMBEDDING_DIMENSIONS
    # Sin palabras en común con la pregunta, el texto relacionado debe quedar más cerca.
    assert cosine(query, related) > cosine(query, unrelated)
    print(  # visible con -s; ayuda a calibrar RETRIEVAL_MIN_SCORE
        f"\nsimilitud relacionada={cosine(query, related):.3f} "
        f"no relacionada={cosine(query, unrelated):.3f}"
    )
