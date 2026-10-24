"""Endpoint de búsqueda semántica (solo recuperación; la respuesta con LLM llega en la Fase 5)."""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.scope import check_scope_exists
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.search import SearchRequest, SearchResponse, SearchResultItem
from app.services import retrieval
from app.services.embeddings import EmbeddingError, EmbeddingProvider, get_embedding_provider

router = APIRouter(prefix="/api/v1", tags=["search"])


@router.post(
    "/search",
    response_model=SearchResponse,
    responses={
        404: {"description": "La carpeta o el documento indicados no existen"},
        422: {"description": "Consulta vacía, demasiado larga o top_k fuera de rango"},
        503: {"description": "Proveedor de embeddings no configurado o no disponible"},
    },
)
def search_chunks(
    request: SearchRequest,
    session: Annotated[Session, Depends(get_db)],
    embedder: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SearchResponse:
    """Busca los fragmentos más relevantes combinando significado y palabras exactas."""
    query = request.query.strip()
    if not query:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "La consulta está vacía.")
    if len(query) > settings.max_query_chars:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"La consulta supera el máximo de {settings.max_query_chars} caracteres.",
        )
    top_k = request.top_k or settings.retrieval_top_k
    if top_k > settings.retrieval_max_top_k:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"top_k no puede superar {settings.retrieval_max_top_k}.",
        )

    check_scope_exists(session, request)

    try:
        results = retrieval.search(session, embedder, settings, query, top_k, request.to_scope())
    except EmbeddingError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, exc.message) from None

    return SearchResponse(
        results=[SearchResultItem(**asdict(result)) for result in results],
        insufficient_evidence=not results,
    )
