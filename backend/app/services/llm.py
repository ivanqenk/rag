"""Proveedores de LLM (el modelo que redacta la respuesta) detrás de una interfaz pequeña.

El LLM no tiene herramientas ni puede ejecutar acciones: recibe texto y devuelve una
respuesta estructurada. Así, aunque un documento intente manipularlo, lo peor que puede
pasar es una respuesta incorrecta, nunca una acción no autorizada.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Protocol, TypeVar

import openai
from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.services.openai_errors import is_quota_exhausted
from app.services.prompts import (
    RERANK_SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    VERIFY_SYSTEM_PROMPT,
    ContextChunk,
    build_rerank_message,
    build_summary_message,
    build_user_message,
    build_verify_message,
)


class LLMPoint(BaseModel):
    """Una afirmación de una respuesta detallada o por pasos, con sus propias fuentes."""

    text: str = Field(description="Una sola afirmación concreta, sacada de las fuentes")
    cited_sources: list[str] = Field(description="Ids de las fuentes que la respaldan")


class LLMAnswer(BaseModel):
    """Esquema que el LLM está obligado a rellenar (Structured Outputs).

    Datos estructurados en lugar de Markdown: el frontend los dibuja como texto (sin riesgo de
    HTML o enlaces inyectados) y cada punto se puede verificar por separado.
    """

    answer: str = Field(description="Respuesta a la pregunta basada solo en las fuentes")
    cited_sources: list[str] = Field(description="Ids de las fuentes que respaldan la respuesta")
    # default_factory no aparece en el esquema: para OpenAI el campo sigue siendo obligatorio.
    points: list[LLMPoint] = Field(
        default_factory=list, description="Puntos o pasos (vacío en respuestas breves)"
    )
    insufficient_evidence: bool = Field(
        description="true si las fuentes no permiten responder la pregunta"
    )


class LLMVerdict(BaseModel):
    id: str
    supported: bool = Field(description="true solo si sus fragmentos respaldan toda la afirmación")


class LLMVerification(BaseModel):
    verdicts: list[LLMVerdict]


@dataclass(frozen=True)
class VerificationResult:
    # id de la afirmación -> respaldada. Las que falten se tratan como no respaldadas.
    supported: dict[str, bool]
    input_tokens: int
    output_tokens: int


class LLMSummary(BaseModel):
    summary: str = Field(description="Resumen del documento en texto plano")


class LLMRerank(BaseModel):
    relevant: list[str] = Field(
        description="Ids de los fragmentos útiles para responder, del más al menos útil"
    )


@dataclass(frozen=True)
class RerankResult:
    refs: list[str]
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class LLMResult:
    answer: LLMAnswer
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class SummaryResult:
    summary: str
    input_tokens: int
    output_tokens: int


_Parsed = TypeVar("_Parsed", bound=BaseModel)


class LLMError(Exception):
    """Fallo del proveedor. `message` es apto para mostrarse al usuario."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class LLMProvider(Protocol):
    model_name: str

    def generate_answer(
        self, question: str, context: Sequence[ContextChunk], style: str = "brief"
    ) -> LLMResult: ...

    def verify(
        self, question: str, claims: Sequence[tuple[str, str, Sequence[ContextChunk]]]
    ) -> VerificationResult: ...

    def generate_summary(self, filename: str, chunks: Sequence[ContextChunk]) -> SummaryResult: ...

    def rerank(
        self, question: str, candidates: Sequence[ContextChunk], top_n: int
    ) -> RerankResult: ...


class OpenAILLMProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        reasoning_effort: str,
        rerank_reasoning_effort: str,
        max_output_tokens: int,
        timeout_seconds: float,
        max_retries: int,
    ) -> None:
        self.model_name = model
        self._reasoning_effort = reasoning_effort
        self._rerank_reasoning_effort = rerank_reasoning_effort
        self._max_output_tokens = max_output_tokens
        self._client = openai.OpenAI(
            api_key=api_key, timeout=timeout_seconds, max_retries=max_retries
        )

    def generate_answer(
        self, question: str, context: Sequence[ContextChunk], style: str = "brief"
    ) -> LLMResult:
        parsed, input_tokens, output_tokens = self._parse(
            SYSTEM_PROMPT, build_user_message(question, context, style), LLMAnswer
        )
        return LLMResult(answer=parsed, input_tokens=input_tokens, output_tokens=output_tokens)

    def verify(
        self, question: str, claims: Sequence[tuple[str, str, Sequence[ContextChunk]]]
    ) -> VerificationResult:
        # Comparar una afirmación con su texto no necesita razonamiento largo: mismo esfuerzo
        # que el reordenamiento (rápido).
        parsed, input_tokens, output_tokens = self._parse(
            VERIFY_SYSTEM_PROMPT,
            build_verify_message(question, claims),
            LLMVerification,
            reasoning_effort=self._rerank_reasoning_effort,
        )
        return VerificationResult(
            supported={verdict.id: verdict.supported for verdict in parsed.verdicts},
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def generate_summary(self, filename: str, chunks: Sequence[ContextChunk]) -> SummaryResult:
        parsed, input_tokens, output_tokens = self._parse(
            SUMMARY_SYSTEM_PROMPT, build_summary_message(filename, chunks), LLMSummary
        )
        return SummaryResult(
            summary=parsed.summary, input_tokens=input_tokens, output_tokens=output_tokens
        )

    def rerank(self, question: str, candidates: Sequence[ContextChunk], top_n: int) -> RerankResult:
        parsed, input_tokens, output_tokens = self._parse(
            RERANK_SYSTEM_PROMPT,
            build_rerank_message(question, candidates, top_n),
            LLMRerank,
            reasoning_effort=self._rerank_reasoning_effort,
        )
        return RerankResult(
            refs=parsed.relevant, input_tokens=input_tokens, output_tokens=output_tokens
        )

    def _parse(
        self,
        instructions: str,
        user_input: str,
        schema: type[_Parsed],
        reasoning_effort: str | None = None,
    ) -> tuple[_Parsed, int, int]:
        """Llama al modelo con salida estructurada y traduce los errores a LLMError."""
        try:
            response = self._client.responses.parse(
                model=self.model_name,
                instructions=instructions,
                input=user_input,
                text_format=schema,
                reasoning={"effort": reasoning_effort or self._reasoning_effort},
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
        return (
            response.output_parsed,
            usage.input_tokens if usage else 0,
            usage.output_tokens if usage else 0,
        )


class FakeLLMProvider:
    """LLM local y determinista para pruebas: no llama a ninguna API ni cuesta dinero.

    Por defecto "responde" con el inicio de la primera fuente y la cita. Con `scripted`
    devuelve siempre esa respuesta, para simular comportamientos concretos del modelo
    (citas inventadas, abstención…). El "resumen" es el nombre del archivo y el inicio
    del primer fragmento; el "reordenamiento" conserva el orden del buscador. Guarda las
    llamadas para poder inspeccionarlas.
    """

    model_name = "fake-llm-v1"

    def __init__(self, scripted: LLMAnswer | None = None) -> None:
        self._scripted = scripted
        self.calls: list[tuple[str, list[ContextChunk]]] = []
        self.summary_calls: list[tuple[str, list[ContextChunk]]] = []
        self.rerank_calls: list[tuple[str, list[ContextChunk], int]] = []
        self.styles: list[str] = []
        self.verify_calls: list[list[tuple[str, str, Sequence[ContextChunk]]]] = []
        self.unsupported: set[str] = set()

    def generate_answer(
        self, question: str, context: Sequence[ContextChunk], style: str = "brief"
    ) -> LLMResult:
        self.calls.append((question, list(context)))
        self.styles.append(style)
        if self._scripted is not None:
            answer = self._scripted
        elif not context:
            answer = LLMAnswer(
                answer="No encontré la respuesta.", cited_sources=[], insufficient_evidence=True
            )
        else:
            first = context[0]
            # Detallada / pasos: un punto por fuente (como mucho tres), citándola.
            points = (
                []
                if style == "brief"
                else [LLMPoint(text=c.text[:120], cited_sources=[c.ref]) for c in context[:3]]
            )
            answer = LLMAnswer(
                answer=f"Según las fuentes: {first.text[:200]}",
                cited_sources=[first.ref],
                points=points,
                insufficient_evidence=False,
            )
        return LLMResult(answer=answer, input_tokens=0, output_tokens=0)

    def verify(
        self, question: str, claims: Sequence[tuple[str, str, Sequence[ContextChunk]]]
    ) -> VerificationResult:
        """Por defecto lo da todo por respaldado; `unsupported` marca ids como no respaldados."""
        self.verify_calls.append(list(claims))
        return VerificationResult(
            supported={claim_id: claim_id not in self.unsupported for claim_id, _, _ in claims},
            input_tokens=0,
            output_tokens=0,
        )

    def generate_summary(self, filename: str, chunks: Sequence[ContextChunk]) -> SummaryResult:
        self.summary_calls.append((filename, list(chunks)))
        first_text = chunks[0].text[:300] if chunks else ""
        return SummaryResult(
            summary=f"Resumen simulado de {filename}: {first_text}",
            input_tokens=0,
            output_tokens=0,
        )

    def rerank(self, question: str, candidates: Sequence[ContextChunk], top_n: int) -> RerankResult:
        self.rerank_calls.append((question, list(candidates), top_n))
        refs = [chunk.ref for chunk in candidates[:top_n]]
        return RerankResult(refs=refs, input_tokens=0, output_tokens=0)


def build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "fake":
        return FakeLLMProvider()
    if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value():
        raise LLMError("El proveedor de LLM no está configurado (falta OPENAI_API_KEY).")
    return OpenAILLMProvider(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.llm_model,
        reasoning_effort=settings.llm_reasoning_effort,
        rerank_reasoning_effort=settings.rag_rerank_reasoning_effort,
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


def get_optional_llm_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LLMProvider | None:
    """Como get_llm_provider, pero sin LLM configurado devuelve None en vez de un 503.

    Se usa al subir documentos: el resumen es opcional y no debe impedir la subida.
    """
    try:
        return build_llm_provider(settings)
    except LLMError:
        return None
