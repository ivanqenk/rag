"""Búsqueda híbrida de fragmentos: vectorial (significado) + texto completo (palabras exactas).

Por qué híbrida: los embeddings encuentran textos con el mismo significado aunque usen otras
palabras, pero fallan con nombres propios, códigos y números exactos ("artículo 47.3"). La
búsqueda por palabras de PostgreSQL cubre justo ese caso. Las dos listas se combinan con
Reciprocal Rank Fusion (RRF), que solo usa la posición en cada lista, así no hay que
comparar puntuaciones de escalas distintas.
"""

import logging
import time
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
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


def search(
    session: Session,
    embedder: EmbeddingProvider,
    settings: Settings,
    query: str,
    top_k: int,
) -> list[SearchResult]:
    """Devuelve hasta `top_k` fragmentos relevantes. Lista vacía = no hay evidencia suficiente."""
    started = time.perf_counter()
    candidates = top_k * CANDIDATES_PER_RESULT
    query_embedding = embedder.embed_query(query)

    # Solo documentos completados: nunca devolver fragmentos de un procesamiento a medias.
    base = (
        select(DocumentChunk, Document.original_filename)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.status == DocumentStatus.COMPLETED)
    )

    # 1) Vectorial. Búsqueda exacta (sin índice). Solo vectores del modelo activo: los de
    #    otro modelo viven en otro "espacio" y compararlos daría resultados sin sentido.
    distance = DocumentChunk.embedding.cosine_distance(query_embedding)
    vector_rows = session.execute(
        base.add_columns((1 - distance).label("similarity"))
        .where(DocumentChunk.embedding_model == embedder.model_name)
        .where(distance <= 1 - settings.retrieval_min_score)
        .order_by(distance)
        .limit(candidates)
    ).all()

    # 2) Texto completo. websearch_to_tsquery acepta texto libre de forma segura (no falla
    #    con comillas o símbolos) y exige que aparezcan todas las palabras.
    ts_query = func.websearch_to_tsquery("simple", query)
    keyword_rows = session.execute(
        base.where(DocumentChunk.search_vector.op("@@")(ts_query))
        .order_by(func.ts_rank_cd(DocumentChunk.search_vector, ts_query).desc())
        .limit(candidates)
    ).all()

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
