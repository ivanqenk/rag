from types import SimpleNamespace
from typing import Any

import httpx2
import openai
import pytest

from app.core.config import Settings
from app.services.llm import (
    FakeLLMProvider,
    LLMAnswer,
    LLMError,
    LLMRerank,
    LLMSummary,
    OpenAILLMProvider,
    build_llm_provider,
)
from app.services.prompts import (
    RERANK_SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    ContextChunk,
)

CONTEXT = [ContextChunk("S1", "manual.pdf", 1, "Hay 22 días de vacaciones.")]
ANSWER = LLMAnswer(answer="22 días.", cited_sources=["S1"], insufficient_evidence=False)


class FakeResponsesAPI:
    """Imita client.responses.parse y guarda los argumentos recibidos."""

    def __init__(
        self,
        parsed: LLMAnswer | LLMSummary | LLMRerank | None = ANSWER,
        error: Exception | None = None,
    ) -> None:
        self.kwargs: dict[str, Any] = {}
        self._parsed = parsed
        self._error = error

    def parse(self, **kwargs: Any) -> SimpleNamespace:
        self.kwargs = kwargs
        if self._error is not None:
            raise self._error
        return SimpleNamespace(
            output_parsed=self._parsed,
            usage=SimpleNamespace(input_tokens=1200, output_tokens=150),
        )


def make_provider(api: FakeResponsesAPI) -> OpenAILLMProvider:
    provider = OpenAILLMProvider(
        api_key="sk-test",
        model="gpt-6-luna",
        reasoning_effort="low",
        rerank_reasoning_effort="none",
        max_output_tokens=2000,
        timeout_seconds=5,
        max_retries=0,
    )
    provider._client = SimpleNamespace(responses=api)  # type: ignore[assignment]
    return provider


def test_openai_provider_sends_safe_structured_request() -> None:
    api = FakeResponsesAPI()

    result = make_provider(api).generate_answer("¿Cuántos días?", CONTEXT)

    assert result.answer == ANSWER
    assert (result.input_tokens, result.output_tokens) == (1200, 150)
    kwargs = api.kwargs
    assert kwargs["model"] == "gpt-6-luna"
    assert kwargs["instructions"] == SYSTEM_PROMPT
    assert kwargs["text_format"] is LLMAnswer  # salida estructurada con esquema
    assert kwargs["store"] is False  # privacidad: OpenAI no guarda la conversación
    assert kwargs["reasoning"] == {"effort": "low"}
    assert "tools" not in kwargs  # el LLM no puede ejecutar acciones
    assert '<fuente id="S1"' in kwargs["input"]


def test_openai_summary_uses_its_own_prompt_and_schema() -> None:
    api = FakeResponsesAPI(parsed=LLMSummary(summary="Manual de RR. HH."))

    result = make_provider(api).generate_summary("manual.pdf", CONTEXT)

    assert result.summary == "Manual de RR. HH."
    assert api.kwargs["instructions"] == SUMMARY_SYSTEM_PROMPT
    assert api.kwargs["text_format"] is LLMSummary
    assert api.kwargs["store"] is False
    assert "tools" not in api.kwargs
    assert "<fragmento" in api.kwargs["input"]


def test_openai_rerank_uses_its_own_prompt_schema_and_effort() -> None:
    api = FakeResponsesAPI(parsed=LLMRerank(relevant=["S1"]))

    result = make_provider(api).rerank("¿Cuántos días?", CONTEXT, top_n=5)

    assert result.refs == ["S1"]
    assert api.kwargs["instructions"] == RERANK_SYSTEM_PROMPT
    assert api.kwargs["text_format"] is LLMRerank
    assert api.kwargs["reasoning"] == {"effort": "none"}  # tarea sencilla: menos latencia
    assert api.kwargs["store"] is False
    assert "tools" not in api.kwargs
    assert api.kwargs["input"].startswith("<maximo>5</maximo>")


def test_missing_parsed_output_is_an_error() -> None:
    with pytest.raises(LLMError):
        make_provider(FakeResponsesAPI(parsed=None)).generate_answer("pregunta", CONTEXT)


def _request() -> httpx2.Request:
    return httpx2.Request("POST", "https://api.openai.com/v1/responses")


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            openai.AuthenticationError(
                "bad key", response=httpx2.Response(401, request=_request()), body=None
            ),
            "clave de API",
        ),
        (openai.APITimeoutError(request=_request()), "no está disponible"),
        (
            openai.RateLimitError(
                "no credits",
                response=httpx2.Response(429, request=_request()),
                body={"type": "insufficient_quota", "code": "credit_balance_exhausted"},
            ),
            "no tiene saldo",
        ),
    ],
)
def test_openai_errors_become_safe_messages(error: Exception, expected: str) -> None:
    with pytest.raises(LLMError) as exc_info:
        make_provider(FakeResponsesAPI(error=error)).generate_answer("pregunta", CONTEXT)

    assert expected in exc_info.value.message
    assert "bad key" not in exc_info.value.message


@pytest.mark.parametrize("api_key", [None, ""])
def test_build_provider_requires_api_key(api_key: str | None) -> None:
    with pytest.raises(LLMError) as exc_info:
        build_llm_provider(Settings(llm_provider="openai", openai_api_key=api_key))

    assert "OPENAI_API_KEY" in exc_info.value.message


def test_fake_provider_cites_first_source_and_records_calls() -> None:
    llm = FakeLLMProvider()

    result = llm.generate_answer("¿Cuántos días?", CONTEXT)

    assert result.answer.cited_sources == ["S1"]
    assert result.answer.insufficient_evidence is False
    assert llm.calls == [("¿Cuántos días?", CONTEXT)]
