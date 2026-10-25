"""Responder preguntas con RAG: recuperar fragmentos, construir contexto, generar y verificar.

Principio: las fuentes que se muestran al usuario salen de NUESTRA base de datos, no del
texto del LLM. El LLM solo indica qué ids usó; se descartan los que no le dimos (citas
inventadas) y, si no queda ninguna cita válida, la respuesta se trata como no respaldada.

Las preguntas de resumen ("¿de qué trata?") no usan la búsqueda: usan como contexto los
resúmenes generados al procesar cada documento (ver services/summaries.py).

Qué fragmentos lee el LLM depende de RAG_STRATEGY (simple, rerank o progressive; ver
core/config.py). La pregunta puede limitarse a una carpeta, a un documento o a una página.

Formatos de respuesta: breve (una o dos frases) y detallada (resumen + puntos; numerados si
las fuentes describen un procedimiento).
Para que una respuesta larga no añada nada que no esté en los documentos:
1. El prompt lo prohíbe y pide que cada punto cite sus fuentes.
2. El servidor descarta los puntos sin ninguna cita válida.
3. En detallada, una segunda llamada (RAG_VERIFY_ANSWERS) comprueba cada afirmación
   contra el texto de SUS fuentes y descarta las que no estén respaldadas.
"""

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Literal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.documents import DocumentRepository
from app.services import retrieval
from app.services.embeddings import EmbeddingProvider
from app.services.llm import LLMError, LLMProvider
from app.services.prompts import (
    PROMPT_VERSION,
    RERANK_PROMPT_VERSION,
    REWRITE_PROMPT_VERSION,
    VERIFY_PROMPT_VERSION,
    ContextChunk,
)
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
class AnswerPoint:
    text: str
    # Posiciones (desde 0) en RagAnswer.sources de las fuentes que respaldan el punto.
    source_indexes: list[int]


@dataclass(frozen=True)
class RagAnswer:
    answer: str
    sources: list[Source]
    insufficient_evidence: bool
    points: list[AnswerPoint] = field(default_factory=list)
    # Los puntos son pasos de un procedimiento: se muestran numerados.
    points_ordered: bool = False
    # Costo estimado de la consulta (todas las llamadas al LLM y el embedding de la pregunta),
    # para el presupuesto diario.
    cost_usd: float = 0.0
    # La pregunta reescrita a partir de la conversación (None si no hubo historial o no cambió).
    standalone_question: str | None = None
    # Afirmaciones descartadas por no tener cita válida o no superar la verificación. Solo
    # para logs y evaluación (cuántas) y para revisar la verificación (cuáles); no sale por la API.
    removed_claims: list[str] = field(default_factory=list)
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
    style: str = "brief",
    history: Sequence[tuple[str, str]] = (),
) -> RagAnswer:
    """Responde con los documentos, o solo con los de `scope` (carpeta, documento o página),
    en el formato `style` (brief o detailed).

    `history`: (pregunta, respuesta) de los turnos anteriores de la conversación. Si hay, la
    pregunta se reescribe primero para que se entienda sola («¿y después?» → «¿qué pasó después
    de…?») y todo lo demás (búsqueda, respuesta, verificación) usa la versión reescrita.
    """
    started = time.perf_counter()
    usage = _Usage()
    original_question = question
    if history:
        question = _rewrite(llm, settings, question, history, usage)
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
    removed_claims: list[str] = []
    llm_started = time.perf_counter()
    # Sin evidencia no se llama al LLM: ahorra costo y evita respuestas inventadas. Con
    # "progressive" hay varios intentos; se para en el primero que tenga respuesta.
    for context in attempts:
        considered += [(source.document_id, source.page_number) for _, source in context]
        candidate = _generate(llm, settings, question, context, style, usage)
        removed_claims += candidate.removed_claims
        if not candidate.insufficient_evidence:
            answer = candidate
            break
    llm_ms = (time.perf_counter() - llm_started) * 1000

    _log(
        settings,
        llm,
        question,
        style,
        retrieved,
        len(considered),
        len(answer.sources),
        len(removed_claims),
        usage,
        retrieval_ms,
        llm_ms,
        answer.insufficient_evidence,
    )
    cost = _llm_cost(settings, usage) + (
        len(question) / 4 * settings.embedding_price_per_mtok / 1_000_000
    )
    return replace(
        answer,
        considered=considered,
        removed_claims=removed_claims,
        cost_usd=cost,
        standalone_question=question if question != original_question else None,
    )


def _rewrite(
    llm: LLMProvider,
    settings: Settings,
    question: str,
    history: Sequence[tuple[str, str]],
    usage: _Usage,
) -> str:
    """La pregunta reescrita, o la original si la reescritura falla o no es válida: sin
    reescritura la respuesta puede ser peor, pero nunca inventada."""
    try:
        rewritten = llm.rewrite_question(question, history)
    except LLMError:
        logger.warning("Falló la reescritura de la pregunta de seguimiento; se usa la original")
        return question
    usage.add(rewritten.input_tokens, rewritten.output_tokens)
    candidate = rewritten.question.strip()
    if not candidate or len(candidate) > settings.max_query_chars:
        return question
    return candidate


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
    llm: LLMProvider,
    settings: Settings,
    question: str,
    context: list[tuple[ContextChunk, Source]],
    style: str,
    usage: _Usage,
) -> RagAnswer:
    """Una llamada al LLM, la verificación de citas y, si aplica, la de las afirmaciones."""
    chunks = [chunk for chunk, _ in context]
    llm_result = llm.generate_answer(question, chunks, style)
    usage.add(llm_result.input_tokens, llm_result.output_tokens)
    no_evidence = RagAnswer(answer=NO_EVIDENCE_ANSWER, sources=[], insufficient_evidence=True)
    if llm_result.answer.insufficient_evidence:
        return no_evidence

    by_ref = {chunk.ref: (chunk, source) for chunk, source in context}
    invented = 0

    def valid(refs: list[str]) -> list[str]:
        # Verificación de citas: solo ids que existen en el contexto enviado, sin duplicados.
        nonlocal invented
        invented += len(set(refs) - set(by_ref))
        return [ref for ref in dict.fromkeys(refs) if ref in by_ref]

    summary = llm_result.answer.answer.strip()
    summary_refs = valid(llm_result.answer.cited_sources)
    candidates = [] if style == "brief" else llm_result.answer.points
    points = [(p.text.strip(), valid(p.cited_sources)) for p in candidates if p.text.strip()]
    if invented:
        logger.warning("El LLM citó %d fuentes inexistentes; se descartan", invented)
    # Un punto sin ninguna cita válida no está respaldado: se descarta.
    removed = [text for text, refs in points if not refs]
    points = [(text, refs) for text, refs in points if refs]
    if not summary_refs:
        summary = ""

    if style != "brief" and settings.rag_verify_answers:
        summary, points, dropped = _verify(
            llm, question, summary, summary_refs, points, by_ref, usage
        )
        removed += dropped

    if not summary and not points:
        return replace(no_evidence, removed_claims=removed)

    # Fuentes devueltas: las del resumen y las de los puntos, sin repetir, en orden de aparición.
    ordered = list(
        dict.fromkeys([*(summary_refs if summary else []), *(r for _, rs in points for r in rs)])
    )
    position = {ref: i for i, ref in enumerate(ordered)}
    return RagAnswer(
        answer=summary,
        sources=[by_ref[ref][1] for ref in ordered],
        insufficient_evidence=False,
        points=[AnswerPoint(text, [position[r] for r in refs]) for text, refs in points],
        points_ordered=llm_result.answer.ordered and bool(points),
        removed_claims=removed,
    )


def _verify(
    llm: LLMProvider,
    question: str,
    summary: str,
    summary_refs: list[str],
    points: list[tuple[str, list[str]]],
    by_ref: dict[str, tuple[ContextChunk, Source]],
    usage: _Usage,
) -> tuple[str, list[tuple[str, list[str]]], list[str]]:
    """Comprueba cada afirmación contra el texto de las fuentes que cita (no contra todo el
    contexto: si una cifra sale de otra fuente, la cita es incorrecta). Lo no respaldado, o
    sin veredicto, se descarta."""
    claims: list[tuple[str, str, list[ContextChunk]]] = []
    if summary:
        claims.append(("A0", summary, [by_ref[r][0] for r in summary_refs]))
    for i, (text, refs) in enumerate(points, start=1):
        claims.append((f"A{i}", text, [by_ref[r][0] for r in refs]))
    if not claims:
        return summary, points, []

    verification = llm.verify(question, claims)
    usage.add(verification.input_tokens, verification.output_tokens)
    supported = verification.supported
    kept_points = [p for i, p in enumerate(points, start=1) if supported.get(f"A{i}", False)]
    kept_summary = summary if summary and supported.get("A0", False) else ""
    dropped = [text for text, refs in points if (text, refs) not in kept_points]
    if summary and not kept_summary:
        dropped.insert(0, summary)
    if dropped:
        logger.info("Verificación: %d afirmaciones sin respaldo descartadas", len(dropped))
    return kept_summary, kept_points, dropped


def _llm_cost(settings: Settings, usage: _Usage) -> float:
    return (
        usage.input_tokens * settings.llm_input_price_per_mtok
        + usage.output_tokens * settings.llm_output_price_per_mtok
    ) / 1_000_000


def _log(
    settings: Settings,
    llm: LLMProvider,
    question: str,
    style: str,
    retrieved: int,
    context_chunks: int,
    cited: int,
    removed_claims: int,
    usage: _Usage,
    retrieval_ms: float,
    llm_ms: float,
    insufficient: bool,
) -> None:
    """Métricas por consulta. Nunca el texto de la pregunta, del contexto ni de la respuesta."""
    cost = _llm_cost(settings, usage)
    logger.info(
        "Consulta RAG: %d caracteres, formato=%s, %d recuperados, %d leídos por el LLM, "
        "%d citados, %d afirmaciones descartadas, sin_evidencia=%s, estrategia=%s, modelo=%s, "
        "prompts=%s/%s/%s/%s, llamadas=%d, tokens=%d/%d, costo~$%.6f, recuperación %.0f ms, "
        "LLM %.0f ms",
        len(question),
        style,
        retrieved,
        context_chunks,
        cited,
        removed_claims,
        insufficient,
        settings.rag_strategy,
        llm.model_name,
        PROMPT_VERSION,
        RERANK_PROMPT_VERSION,
        VERIFY_PROMPT_VERSION,
        REWRITE_PROMPT_VERSION,
        usage.calls,
        usage.input_tokens,
        usage.output_tokens,
        cost,
        retrieval_ms,
        llm_ms,
    )
