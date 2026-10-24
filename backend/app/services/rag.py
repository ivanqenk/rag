"""Responder preguntas con RAG: recuperar fragmentos, construir contexto, generar y verificar.

Principio: las fuentes que se muestran al usuario salen de NUESTRA base de datos, no del
texto del LLM. El LLM solo indica qué ids usó; se descartan los que no le dimos (citas
inventadas) y, si no queda ninguna cita válida, la respuesta se trata como no respaldada.

Las preguntas de resumen ("¿de qué trata?") no usan la búsqueda: usan como contexto los
resúmenes generados al procesar cada documento (ver services/summaries.py).
"""

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.documents import DocumentRepository
from app.services import retrieval
from app.services.embeddings import EmbeddingProvider
from app.services.llm import LLMProvider, LLMResult
from app.services.prompts import PROMPT_VERSION, ContextChunk
from app.services.summaries import is_summary_question

logger = logging.getLogger(__name__)

NO_EVIDENCE_ANSWER = (
    "No encontré información en los documentos disponibles para responder a esta pregunta."
)
EXCERPT_CHARS = 300
# Cuántos resúmenes (documentos más recientes) se consideran como máximo por pregunta.
MAX_SUMMARY_DOCUMENTS = 20


@dataclass(frozen=True)
class Source:
    document_id: UUID
    filename: str
    page_number: int | None
    # Un fragmento concreto o el resumen del documento (que no tiene fragmento ni score).
    source_type: Literal["chunk", "summary"]
    chunk_id: UUID | None
    excerpt: str
    score: float | None


@dataclass(frozen=True)
class RagAnswer:
    answer: str
    sources: list[Source]
    insufficient_evidence: bool


def build_context(
    results: Sequence[retrieval.SearchResult], max_chars: int
) -> list[tuple[ContextChunk, retrieval.SearchResult]]:
    """Asigna ids cortos (S1, S2…) a los resultados, en orden, sin superar `max_chars`."""
    context: list[tuple[ContextChunk, retrieval.SearchResult]] = []
    used_chars = 0
    for result in results:
        if used_chars + len(result.text) > max_chars:
            continue  # uno más corto que venga después aún puede caber
        used_chars += len(result.text)
        chunk = ContextChunk(
            ref=f"S{len(context) + 1}",
            filename=result.filename,
            page_number=result.page_number,
            text=result.text,
        )
        context.append((chunk, result))
    return context


def build_summary_context(
    documents: Sequence[tuple[UUID, str, str]], max_chars: int
) -> list[tuple[ContextChunk, Source]]:
    """Como build_context, pero con resúmenes (document_id, filename, summary)."""
    context: list[tuple[ContextChunk, Source]] = []
    used_chars = 0
    for document_id, filename, summary in documents:
        if used_chars + len(summary) > max_chars:
            continue
        used_chars += len(summary)
        chunk = ContextChunk(
            ref=f"S{len(context) + 1}", filename=filename, page_number=None, text=summary
        )
        source = Source(
            document_id=document_id,
            filename=filename,
            page_number=None,
            source_type="summary",
            chunk_id=None,
            excerpt=make_excerpt(summary),
            score=None,
        )
        context.append((chunk, source))
    return context


def _source_from_result(result: retrieval.SearchResult) -> Source:
    return Source(
        document_id=result.document_id,
        filename=result.filename,
        page_number=result.page_number,
        source_type="chunk",
        chunk_id=result.chunk_id,
        excerpt=make_excerpt(result.text),
        score=result.score,
    )


def make_excerpt(text: str, max_chars: int = EXCERPT_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    cut = text.rfind(" ", 0, max_chars)
    return text[: cut if cut > 0 else max_chars] + "…"


def answer_question(
    session: Session,
    embedder: EmbeddingProvider,
    llm: LLMProvider,
    settings: Settings,
    question: str,
) -> RagAnswer:
    started = time.perf_counter()
    context: list[tuple[ContextChunk, Source]] = []
    retrieved = 0
    if is_summary_question(question):
        documents = DocumentRepository(session).list_summaries(MAX_SUMMARY_DOCUMENTS)
        summaries = [(d.id, d.original_filename, d.summary or "") for d in documents]
        context = build_summary_context(summaries, settings.rag_max_context_chars)
        retrieved = len(documents)
    if not context:
        # Pregunta normal, o de resumen sin resúmenes disponibles: búsqueda RAG habitual.
        results = retrieval.search(session, embedder, settings, question, settings.retrieval_top_k)
        retrieved = len(results)
        context = [
            (chunk, _source_from_result(result))
            for chunk, result in build_context(results, settings.rag_max_context_chars)
        ]
    retrieval_ms = (time.perf_counter() - started) * 1000

    if not context:
        # Sin evidencia no se llama al LLM: ahorra costo y evita respuestas inventadas.
        _log(settings, llm, question, retrieved, 0, 0, None, retrieval_ms, 0, True)
        return RagAnswer(answer=NO_EVIDENCE_ANSWER, sources=[], insufficient_evidence=True)

    llm_started = time.perf_counter()
    llm_result = llm.generate_answer(question, [chunk for chunk, _ in context])
    llm_ms = (time.perf_counter() - llm_started) * 1000

    by_ref = {chunk.ref: source for chunk, source in context}
    # Verificación de citas: solo ids que existen en el contexto enviado, sin duplicados.
    valid_refs = list(dict.fromkeys(r for r in llm_result.answer.cited_sources if r in by_ref))
    invented = len(set(llm_result.answer.cited_sources) - set(by_ref))
    if invented:
        logger.warning("El LLM citó %d fuentes inexistentes; se descartan", invented)

    insufficient = llm_result.answer.insufficient_evidence or not valid_refs
    if insufficient:
        answer = RagAnswer(answer=NO_EVIDENCE_ANSWER, sources=[], insufficient_evidence=True)
    else:
        answer = RagAnswer(
            answer=llm_result.answer.answer,
            sources=[by_ref[ref] for ref in valid_refs],
            insufficient_evidence=False,
        )

    _log(
        settings,
        llm,
        question,
        retrieved,
        len(context),
        len(valid_refs),
        llm_result,
        retrieval_ms,
        llm_ms,
        insufficient,
    )
    return answer


def _log(
    settings: Settings,
    llm: LLMProvider,
    question: str,
    retrieved: int,
    context_chunks: int,
    cited: int,
    llm_result: LLMResult | None,
    retrieval_ms: float,
    llm_ms: float,
    insufficient: bool,
) -> None:
    """Métricas por consulta. Nunca el texto de la pregunta, del contexto ni de la respuesta."""
    input_tokens = llm_result.input_tokens if llm_result else 0
    output_tokens = llm_result.output_tokens if llm_result else 0
    cost = (
        input_tokens * settings.llm_input_price_per_mtok
        + output_tokens * settings.llm_output_price_per_mtok
    ) / 1_000_000
    logger.info(
        "Consulta RAG: %d caracteres, %d recuperados, %d en contexto, %d citados, "
        "sin_evidencia=%s, modelo=%s, prompt=%s, tokens=%d/%d, costo~$%.6f, "
        "recuperación %.0f ms, LLM %.0f ms",
        len(question),
        retrieved,
        context_chunks,
        cited,
        insufficient,
        llm.model_name,
        PROMPT_VERSION,
        input_tokens,
        output_tokens,
        cost,
        retrieval_ms,
        llm_ms,
    )
