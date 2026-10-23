import math
from types import SimpleNamespace

import httpx2
import openai
import pytest

from app.core.config import Settings
from app.models.document_chunk import EMBEDDING_DIMENSIONS
from app.services.embeddings import (
    EmbeddingError,
    FakeEmbeddingProvider,
    OpenAIEmbeddingProvider,
    build_embedding_provider,
)


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


# --- Proveedor falso ---------------------------------------------------------------


def test_fake_provider_is_deterministic_and_normalized() -> None:
    provider = FakeEmbeddingProvider()

    first = provider.embed_query("Política de vacaciones")
    second = provider.embed_documents(["Política de vacaciones"])[0]

    assert first == second
    assert len(first) == EMBEDDING_DIMENSIONS
    assert math.isclose(math.sqrt(sum(v * v for v in first)), 1.0)


def test_fake_provider_puts_texts_with_shared_words_closer() -> None:
    provider = FakeEmbeddingProvider()
    query = provider.embed_query("días de vacaciones")

    related = provider.embed_query("Tienes veintidós días de vacaciones al año")
    unrelated = provider.embed_query("Receta de paella valenciana")

    assert cosine(query, related) > cosine(query, unrelated)


def test_fake_provider_handles_text_without_words() -> None:
    vector = FakeEmbeddingProvider().embed_query("¿?")

    assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0)


# --- Proveedor de OpenAI (con el cliente HTTP sustituido) ---------------------------


class FakeEmbeddingsAPI:
    """Imita client.embeddings: registra las llamadas y devuelve vectores en orden inverso
    (la API no garantiza el orden; el proveedor debe ordenar por `index`)."""

    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[list[str]] = []
        self._error = error

    def create(self, *, model: str, input: list[str], dimensions: int) -> SimpleNamespace:
        if self._error is not None:
            raise self._error
        self.calls.append(input)
        data = [
            SimpleNamespace(index=i, embedding=[float(len(text))] * dimensions)
            for i, text in enumerate(input)
        ]
        return SimpleNamespace(data=list(reversed(data)))


def make_openai_provider(api: FakeEmbeddingsAPI, batch_size: int = 2) -> OpenAIEmbeddingProvider:
    provider = OpenAIEmbeddingProvider(
        api_key="sk-test",
        model="text-embedding-3-small",
        batch_size=batch_size,
        timeout_seconds=5,
        max_retries=0,
    )
    provider._client = SimpleNamespace(embeddings=api)  # type: ignore[assignment]
    return provider


def test_openai_provider_batches_requests_and_keeps_order() -> None:
    api = FakeEmbeddingsAPI()
    provider = make_openai_provider(api, batch_size=2)

    vectors = provider.embed_documents(["a", "bb", "ccc", "dddd", "eeeee"])

    assert api.calls == [["a", "bb"], ["ccc", "dddd"], ["eeeee"]]
    assert [v[0] for v in vectors] == [1.0, 2.0, 3.0, 4.0, 5.0]


def _request() -> httpx2.Request:
    return httpx2.Request("POST", "https://api.openai.com/v1/embeddings")


@pytest.mark.parametrize(
    ("error", "expected_message"),
    [
        (
            openai.AuthenticationError(
                "bad key", response=httpx2.Response(401, request=_request()), body=None
            ),
            "clave de API",
        ),
        (
            openai.RateLimitError(
                "slow down", response=httpx2.Response(429, request=_request()), body=None
            ),
            "no está disponible",
        ),
        (openai.APITimeoutError(request=_request()), "no está disponible"),
    ],
)
def test_openai_errors_become_safe_messages(error: Exception, expected_message: str) -> None:
    provider = make_openai_provider(FakeEmbeddingsAPI(error=error))

    with pytest.raises(EmbeddingError) as exc_info:
        provider.embed_query("hola")

    assert expected_message in exc_info.value.message
    # El mensaje al usuario no incluye el detalle técnico del proveedor.
    assert "slow down" not in exc_info.value.message
    assert "bad key" not in exc_info.value.message


def test_openai_unexpected_dimensions_are_rejected() -> None:
    class WrongDimensionsAPI(FakeEmbeddingsAPI):
        def create(self, *, model: str, input: list[str], dimensions: int) -> SimpleNamespace:
            return SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[0.1, 0.2])])

    provider = make_openai_provider(WrongDimensionsAPI())

    with pytest.raises(EmbeddingError):
        provider.embed_query("hola")


# --- Selección de proveedor ---------------------------------------------------------


@pytest.mark.parametrize("api_key", [None, ""])
def test_build_provider_requires_api_key_for_openai(api_key: str | None) -> None:
    settings = Settings(embeddings_provider="openai", openai_api_key=api_key)

    with pytest.raises(EmbeddingError) as exc_info:
        build_embedding_provider(settings)

    assert "OPENAI_API_KEY" in exc_info.value.message


def test_build_provider_returns_fake_when_configured() -> None:
    settings = Settings(embeddings_provider="fake")

    assert isinstance(build_embedding_provider(settings), FakeEmbeddingProvider)


def test_api_key_is_not_exposed_when_settings_are_printed() -> None:
    settings = Settings(openai_api_key="sk-super-secreta")

    assert "sk-super-secreta" not in repr(settings)
    assert "sk-super-secreta" not in str(settings.model_dump())
