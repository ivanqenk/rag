"""Búsqueda híbrida de fragmentos: vectorial (significado) + texto completo (palabras exactas).

Por qué híbrida: los embeddings encuentran textos con el mismo significado aunque usen otras
palabras, pero fallan con nombres propios, códigos y números exactos ("artículo 47.3"). La
búsqueda por palabras de PostgreSQL cubre justo ese caso. Las dos listas se combinan con
Reciprocal Rank Fusion (RRF), que solo usa la posición en cada lista, así no hay que
comparar puntuaciones de escalas distintas.

Búsqueda por palabras: basta con que el fragmento contenga ALGUNA palabra importante de la
pregunta (OR), y se ordena con una puntuación tipo BM25: cuenta más una palabra rara en la
colección ("Tezcuco") que una que aparece en todas partes ("Cortés"). Exigir todas las
palabras (AND) casi nunca encontraba nada con preguntas naturales (ver la evaluación).
"""

import logging
import math
import re
import time
from collections import Counter
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.schemas.document import DocumentStatus
from app.services.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)

# Constante estándar de RRF: amortigua la diferencia entre las primeras posiciones.
RRF_K = 60
# Cuántos candidatos trae cada búsqueda antes de fusionar, respecto al top_k pedido.
CANDIDATES_PER_RESULT = 4
# Fragmentos que PostgreSQL preselecciona (ts_rank_cd) antes de puntuarlos con BM25.
KEYWORD_POOL = 200
MAX_KEYWORD_TERMS = 12
BM25_K1 = 1.2
# Fracción mínima de las palabras de la pregunta que debe contener un fragmento. Evita que
# una sola palabra suelta ("conductor") convierta en evidencia un fragmento sin relación,
# saltándose el umbral de similitud.
MIN_TERM_COVERAGE = 0.5
# Letras y dígitos (sin "_", que el analizador de PostgreSQL trata como separador).
_WORD_RE = re.compile(r"[^\W_]+")
# Palabras vacías frecuentes en español e inglés: no ayudan a distinguir fragmentos.
STOPWORDS = frozenset(
    """
    al ante con contra del desde donde durante entre hacia hasta las los mas para pero por
    que qué quien quién quienes cual cuál cuales cuáles cuando cuándo como cómo cuanto cuánto
    cuanta cuánta cuantos cuántos cuantas cuántas sin sobre tras una uno unos unas este esta
    esto estos estas ese esa eso esos esas aquel aquella fue fueron era eran ser son está
    están hay había han has hace hizo muy sus nos les lo la le se su mis tus tengo tiene
    the and for are was were what which who whom when where why how does did with from this
    that these those have has had about into your you our their there its can could
    """.split()
)


@dataclass(frozen=True)
class SearchResult:
    chunk_id: UUID
    document_id: UUID
    filename: str
    page_number: int | None
    chunk_index: int
    text: str
    score: float  # puntuación RRF combinada (solo sirve para ordenar)
    vector_similarity: float | None  # similitud coseno 0-1; None si solo coincidió por palabras
    keyword_match: bool


def keyword_terms(query: str) -> list[str]:
    """Palabras de la pregunta útiles para buscar: sin palabras vacías ni repetidas."""
    terms: list[str] = []
    for word in _WORD_RE.findall(query.lower()):
        if len(word) >= 3 and word not in STOPWORDS and word not in terms:
            terms.append(word)
    return terms[:MAX_KEYWORD_TERMS]


def search(
    session: Session,
    embedder: EmbeddingProvider,
    settings: Settings,
    query: str,
    top_k: int,
    document_id: UUID | None = None,
    page_number: int | None = None,
) -> list[SearchResult]:
    """Devuelve hasta `top_k` fragmentos relevantes. Lista vacía = no hay evidencia suficiente.

    `document_id` y `page_number` limitan la búsqueda a un documento o a una de sus páginas.
    """
    started = time.perf_counter()
    candidates = top_k * CANDIDATES_PER_RESULT
    query_embedding = embedder.embed_query(query)

    # Solo documentos completados: nunca devolver fragmentos de un procesamiento a medias.
    base = (
        select(DocumentChunk, Document.original_filename)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.status == DocumentStatus.COMPLETED)
    )
    if document_id is not None:
        base = base.where(DocumentChunk.document_id == document_id)
    if page_number is not None:
        base = base.where(DocumentChunk.page_number == page_number)
    # Con una página elegida, el usuario ya dijo dónde buscar ("¿en qué año fue esto?" puede
    # parecerse poco a la página): se ordena por similitud, pero sin descartar por umbral.
    min_score = 0.0 if page_number is not None else settings.retrieval_min_score

    # 1) Vectorial. Búsqueda exacta (sin índice). Solo vectores del modelo activo: los de
    #    otro modelo viven en otro "espacio" y compararlos daría resultados sin sentido.
    distance = DocumentChunk.embedding.cosine_distance(query_embedding)
    vector_rows = session.execute(
        base.add_columns((1 - distance).label("similarity"))
        .where(DocumentChunk.embedding_model == embedder.model_name)
        .where(distance <= 1 - min_score)
        .order_by(distance)
        .limit(candidates)
    ).all()

    # 2) Palabras clave (OR + BM25).
    keyword_rows = _keyword_search(session, base, keyword_terms(query), candidates)

    # 3) Fusión RRF: cada lista aporta 1 / (RRF_K + posición).
    scores: dict[UUID, float] = {}
    chunks: dict[UUID, tuple[DocumentChunk, str]] = {}
    similarities: dict[UUID, float] = {}
    keyword_ids: set[UUID] = set()
    for rank, (chunk, filename, similarity) in enumerate(vector_rows, start=1):
        scores[chunk.id] = scores.get(chunk.id, 0) + 1 / (RRF_K + rank)
        chunks[chunk.id] = (chunk, filename)
        similarities[chunk.id] = float(similarity)
    for rank, (chunk, filename) in enumerate(keyword_rows, start=1):
        scores[chunk.id] = scores.get(chunk.id, 0) + 1 / (RRF_K + rank)
        chunks[chunk.id] = (chunk, filename)
        keyword_ids.add(chunk.id)

    ranked_ids = sorted(scores, key=lambda chunk_id: scores[chunk_id], reverse=True)[:top_k]
    results = [
        SearchResult(
            chunk_id=chunk_id,
            document_id=chunks[chunk_id][0].document_id,
            filename=chunks[chunk_id][1],
            page_number=chunks[chunk_id][0].page_number,
            chunk_index=chunks[chunk_id][0].chunk_index,
            text=chunks[chunk_id][0].text,
            score=scores[chunk_id],
            vector_similarity=similarities.get(chunk_id),
            keyword_match=chunk_id in keyword_ids,
        )
        for chunk_id in ranked_ids
    ]

    # Solo métricas, nunca el texto de la pregunta ni de los fragmentos.
    logger.info(
        "Búsqueda: %d caracteres, %d vectoriales, %d por palabras, %d resultados, "
        "mejor similitud %s, %.0f ms",
        len(query),
        len(vector_rows),
        len(keyword_rows),
        len(results),
        f"{max(similarities.values()):.3f}" if similarities else "-",
        (time.perf_counter() - started) * 1000,
    )
    return results


def _keyword_search(
    session: Session, base: Select[tuple[DocumentChunk, str]], terms: list[str], limit: int
) -> list[tuple[DocumentChunk, str]]:
    """Fragmentos que contienen alguna de las palabras, ordenados por BM25."""
    if not terms:
        return []
    # Los términos solo tienen letras y dígitos, así que no pueden romper la sintaxis de
    # to_tsquery. Se combinan con OR ("|").
    ts_query = func.to_tsquery("simple", " | ".join(terms))
    rows = session.execute(
        base.where(DocumentChunk.search_vector.op("@@")(ts_query))
        .order_by(func.ts_rank_cd(DocumentChunk.search_vector, ts_query).desc())
        .limit(KEYWORD_POOL)
    ).all()
    if not rows:
        return []

    # Rareza de cada palabra (IDF) dentro del mismo ámbito de búsqueda: cuántos fragmentos
    # la contienen. Una consulta con un conteo filtrado por término (usa el índice GIN).
    scope = base.with_only_columns(DocumentChunk.search_vector).subquery()
    counts = session.execute(
        select(
            func.count(),
            *(
                func.count().filter(scope.c.search_vector.op("@@")(func.to_tsquery("simple", t)))
                for t in terms
            ),
        ).select_from(scope)
    ).one()
    total, document_frequencies = counts[0], counts[1:]
    idf = {
        term: math.log(1 + (total - df + 0.5) / (df + 0.5))
        for term, df in zip(terms, document_frequencies, strict=True)
    }

    min_matches = math.ceil(len(terms) * MIN_TERM_COVERAGE)

    def bm25(chunk: DocumentChunk) -> float:
        frequencies = Counter(_WORD_RE.findall(chunk.text.lower()))
        matched = [term for term in terms if frequencies[term]]
        if len(matched) < min_matches:
            return 0.0
        return sum(
            idf[term] * frequencies[term] * (BM25_K1 + 1) / (frequencies[term] + BM25_K1)
            for term in matched
        )

    scored = sorted(
        ((bm25(chunk), chunk, filename) for chunk, filename in rows),
        key=lambda row: row[0],
        reverse=True,
    )
    return [(chunk, filename) for score, chunk, filename in scored[:limit] if score > 0]
