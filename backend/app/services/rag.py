"""Responder preguntas con RAG: recuperar fragmentos, construir contexto, generar y verificar.

Principio: las fuentes que se muestran al usuario salen de NUESTRA base de datos, no del
texto del LLM. El LLM solo indica qué ids usó; se descartan los que no le dimos (citas
inventadas) y, si no queda ninguna cita válida, la respuesta se trata como no respaldada.

Las preguntas de resumen ("¿de qué trata?") no usan la búsqueda: usan como contexto los
resúmenes generados al procesar cada documento (ver services/summaries.py).

Qué fragmentos lee el LLM depende de RAG_STRATEGY (simple, rerank o progressive; ver
core/config.py). La pregunta puede limitarse a una carpeta, a un documento o a una página.
"""

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.documents import DocumentRepository
from app.services import retrieval
from app.services.embeddings import EmbeddingProvider
from app.services.llm import LLMError, LLMProvider
from app.services.prompts import PROMPT_VERSION, RERANK_PROMPT_VERSION, ContextChunk
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
    # (documento, página) de todo lo que leyó el LLM. Solo para la evaluación; no sale por
    # la API.
    considered: list[tuple[UUID, int | None]] = field(default_factory=list)


@dataclass
class _Usage:
    """Llamadas y tokens del LLM en una consulta (puede haber varias: rerank, progressive)."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens


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
    scope: retrieval.Scope = retrieval.EVERYWHERE,
) -> RagAnswer:
    """Responde con los documentos, o solo con los de `scope` (carpeta, documento o página)."""
    started = time.perf_counter()
    usage = _Usage()
    attempts: list[list[tuple[ContextChunk, Source]]] = []
    retrieved = 0
    # Con una página concreta la pregunta es sobre esa página, no sobre todo el documento.
    if scope.page_number is None and is_summary_question(question):
        documents = DocumentRepository(session).list_summaries(
            MAX_SUMMARY_DOCUMENTS, folder_id=scope.folder_id, document_id=scope.document_id
        )
        summaries = [(d.id, d.original_filename, d.summary or "") for d in documents]
        summary_context = build_summary_context(summaries, settings.rag_max_context_chars)
        if summary_context:
            attempts = [summary_context]
            retrieved = len(summaries)
    if not attempts:
        # Pregunta normal, o de resumen sin resúmenes disponibles: búsqueda RAG habitual.
        results, groups = _select_chunks(session, embedder, llm, settings, question, scope, usage)
        retrieved = len(results)
        for group in groups:
            context = build_context(group, settings.rag_max_context_chars)
            if context:
                attempts.append([(chunk, _source_from_result(r)) for chunk, r in context])
    retrieval_ms = (time.perf_counter() - started) * 1000

    answer = RagAnswer(answer=NO_EVIDENCE_ANSWER, sources=[], insufficient_evidence=True)
    considered: list[tuple[UUID, int | None]] = []
    llm_started = time.perf_counter()
    # Sin evidencia no se llama al LLM: ahorra costo y evita respuestas inventadas. Con
    # "progressive" hay varios intentos; se para en el primero que tenga respuesta.
    for context in attempts:
        considered += [(source.document_id, source.page_number) for _, source in context]
        candidate = _generate(llm, question, context, usage)
        if not candidate.insufficient_evidence:
            answer = candidate
            break
    llm_ms = (time.perf_counter() - llm_started) * 1000

    _log(
        settings,
        llm,
        question,
        retrieved,
        len(considered),
        len(answer.sources),
        usage,
        retrieval_ms,
        llm_ms,
        answer.insufficient_evidence,
    )
    return RagAnswer(
        answer=answer.answer,
        sources=answer.sources,
        insufficient_evidence=answer.insufficient_evidence,
        considered=considered,
    )


def _select_chunks(
    session: Session,
    embedder: EmbeddingProvider,
    llm: LLMProvider,
    settings: Settings,
    question: str,
    scope: retrieval.Scope,
    usage: _Usage,
) -> tuple[list[retrieval.SearchResult], list[list[retrieval.SearchResult]]]:
    """Busca y decide qué grupos de fragmentos lee el LLM, en orden, según RAG_STRATEGY."""
    top_k = settings.retrieval_top_k
    strategy = settings.rag_strategy
    if strategy == "rerank":
        wanted = max(settings.rag_rerank_candidates, top_k)
    elif strategy == "progressive":
        wanted = top_k * 4  # 5 + 5 + 10 con el valor por defecto
    else:
        wanted = top_k
    results = retrieval.search(session, embedder, settings, question, wanted, scope)

    if strategy == "progressive":
        windows = [(0, top_k), (top_k, top_k * 2), (top_k * 2, top_k * 4)]
        return results, [results[a:b] for a, b in windows if results[a:b]]
    if strategy == "rerank" and len(results) > top_k:
        return results, [_rerank(llm, question, results, top_k, usage)]
    return results, [results[:top_k]]


def _rerank(
    llm: LLMProvider,
    question: str,
    results: list[retrieval.SearchResult],
    top_k: int,
    usage: _Usage,
) -> list[retrieval.SearchResult]:
    """El LLM elige los `top_k` candidatos más útiles. Si falla o no elige ninguno, se usa el
    orden de la búsqueda: el reordenamiento mejora la precisión, pero no es imprescindible."""
    candidates = [
        ContextChunk(ref=f"C{i}", filename=r.filename, page_number=r.page_number, text=r.text)
        for i, r in enumerate(results, start=1)
    ]
    by_ref = {chunk.ref: result for chunk, result in zip(candidates, results, strict=True)}
    try:
        reranked = llm.rerank(question, candidates, top_k)
    except LLMError:
        logger.warning("Falló el reordenamiento; se usa el orden de la búsqueda")
        return results[:top_k]
    usage.add(reranked.input_tokens, reranked.output_tokens)
    # Igual que con las citas: solo ids que existen, sin duplicados.
    chosen = [by_ref[ref] for ref in dict.fromkeys(reranked.refs) if ref in by_ref][:top_k]
    return chosen or results[:top_k]


def _generate(
    llm: LLMProvider, question: str, context: list[tuple[ContextChunk, Source]], usage: _Usage
) -> RagAnswer:
    """Una llamada al LLM con su verificación de citas."""
    llm_result = llm.generate_answer(question, [chunk for chunk, _ in context])
    usage.add(llm_result.input_tokens, llm_result.output_tokens)

    by_ref = {chunk.ref: source for chunk, source in context}
    # Verificación de citas: solo ids que existen en el contexto enviado, sin duplicados.
    valid_refs = list(dict.fromkeys(r for r in llm_result.answer.cited_sources if r in by_ref))
    invented = len(set(llm_result.answer.cited_sources) - set(by_ref))
    if invented:
        logger.warning("El LLM citó %d fuentes inexistentes; se descartan", invented)

    if llm_result.answer.insufficient_evidence or not valid_refs:
        return RagAnswer(answer=NO_EVIDENCE_ANSWER, sources=[], insufficient_evidence=True)
    return RagAnswer(
        answer=llm_result.answer.answer,
        sources=[by_ref[ref] for ref in valid_refs],
        insufficient_evidence=False,
    )


def _log(
    settings: Settings,
    llm: LLMProvider,
    question: str,
    retrieved: int,
    context_chunks: int,
    cited: int,
    usage: _Usage,
    retrieval_ms: float,
    llm_ms: float,
    insufficient: bool,
) -> None:
    """Métricas por consulta. Nunca el texto de la pregunta, del contexto ni de la respuesta."""
    cost = (
        usage.input_tokens * settings.llm_input_price_per_mtok
        + usage.output_tokens * settings.llm_output_price_per_mtok
    ) / 1_000_000
    logger.info(
        "Consulta RAG: %d caracteres, %d recuperados, %d leídos por el LLM, %d citados, "
        "sin_evidencia=%s, estrategia=%s, modelo=%s, prompts=%s/%s, llamadas=%d, "
        "tokens=%d/%d, costo~$%.6f, recuperación %.0f ms, LLM %.0f ms",
        len(question),
        retrieved,
        context_chunks,
        cited,
        insufficient,
        settings.rag_strategy,
        llm.model_name,
        PROMPT_VERSION,
        RERANK_PROMPT_VERSION,
        usage.calls,
        usage.input_tokens,
        usage.output_tokens,
        cost,
        retrieval_ms,
        llm_ms,
    )
