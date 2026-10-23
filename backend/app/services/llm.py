"""Proveedores de LLM (el modelo que redacta la respuesta) detrás de una interfaz pequeña.

El LLM no tiene herramientas ni puede ejecutar acciones: recibe texto y devuelve una
respuesta estructurada. Así, aunque un documento intente manipularlo, lo peor que puede
pasar es una respuesta incorrecta, nunca una acción no autorizada.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Protocol

import openai
from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.services.openai_errors import is_quota_exhausted
from app.services.prompts import SYSTEM_PROMPT, ContextChunk, build_user_message


class LLMAnswer(BaseModel):
    """Esquema que el LLM está obligado a rellenar (Structured Outputs)."""

    answer: str = Field(description="Respuesta a la pregunta basada solo en las fuentes")
    cited_sources: list[str] = Field(description="Ids de las fuentes que respaldan la respuesta")
    insufficient_evidence: bool = Field(
        description="true si las fuentes no permiten responder la pregunta"
    )


@dataclass(frozen=True)
class LLMResult:
    answer: LLMAnswer
    input_tokens: int
    output_tokens: int


class LLMError(Exception):
    """Fallo del proveedor. `message` es apto para mostrarse al usuario."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class LLMProvider(Protocol):
    model_name: str

    def generate_answer(self, question: str, context: Sequence[ContextChunk]) -> LLMResult: ...


class OpenAILLMProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        reasoning_effort: str,
        max_output_tokens: int,
        timeout_seconds: float,
        max_retries: int,
    ) -> None:
        self.model_name = model
        self._reasoning_effort = reasoning_effort
        self._max_output_tokens = max_output_tokens
        self._client = openai.OpenAI(
            api_key=api_key, timeout=timeout_seconds, max_retries=max_retries
        )

    def generate_answer(self, question: str, context: Sequence[ContextChunk]) -> LLMResult:
        try:
            response = self._client.responses.parse(
                model=self.model_name,
                instructions=SYSTEM_PROMPT,
                input=build_user_message(question, context),
                text_format=LLMAnswer,
                reasoning={"effort": self._reasoning_effort},
                max_output_tokens=self._max_output_tokens,
                # Privacidad: no guardar la conversación en OpenAI (no la necesitamos después).
                store=False,
            )
        except openai.AuthenticationError as exc:
            raise LLMError("La clave de API del proveedor de LLM no es válida.") from exc
        except openai.OpenAIError as exc:
            if is_quota_exhausted(exc):
                raise LLMError(
                    "El proveedor de LLM no tiene saldo. Añade crédito en la cuenta del proveedor."
                ) from exc
            raise LLMError("El proveedor de LLM no está disponible. Inténtalo más tarde.") from exc

        # None si el modelo se negó a responder o se quedó sin tokens (respuesta incompleta).
        if response.output_parsed is None:
            raise LLMError("No se pudo generar una respuesta. Inténtalo de nuevo.")
        usage = response.usage
        return LLMResult(
            answer=response.output_parsed,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
        )


class FakeLLMProvider:
    """LLM local y determinista para pruebas: no llama a ninguna API ni cuesta dinero.

    Por defecto "responde" con el inicio de la primera fuente y la cita. Con `scripted`
    devuelve siempre esa respuesta, para simular comportamientos concretos del modelo
    (citas inventadas, abstención…). Guarda las llamadas para poder inspeccionarlas.
    """

    model_name = "fake-llm-v1"

    def __init__(self, scripted: LLMAnswer | None = None) -> None:
        self._scripted = scripted
        self.calls: list[tuple[str, list[ContextChunk]]] = []

    def generate_answer(self, question: str, context: Sequence[ContextChunk]) -> LLMResult:
        self.calls.append((question, list(context)))
        if self._scripted is not None:
            answer = self._scripted
        elif not context:
            answer = LLMAnswer(
                answer="No encontré la respuesta.", cited_sources=[], insufficient_evidence=True
            )
        else:
            first = context[0]
            answer = LLMAnswer(
                answer=f"Según las fuentes: {first.text[:200]}",
                cited_sources=[first.ref],
                insufficient_evidence=False,
            )
        return LLMResult(answer=answer, input_tokens=0, output_tokens=0)


def build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "fake":
        return FakeLLMProvider()
    if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value():
        raise LLMError("El proveedor de LLM no está configurado (falta OPENAI_API_KEY).")
    return OpenAILLMProvider(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.llm_model,
        reasoning_effort=settings.llm_reasoning_effort,
        max_output_tokens=settings.llm_max_output_tokens,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )


def get_llm_provider(settings: Annotated[Settings, Depends(get_settings)]) -> LLMProvider:
    """Dependencia de FastAPI. Las pruebas la sustituyen por FakeLLMProvider."""
    try:
        return build_llm_provider(settings)
    except LLMError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, exc.message) from None
