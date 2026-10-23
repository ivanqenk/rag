"""Endpoint de consulta RAG: responde una pregunta citando los documentos."""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.query import QueryRequest, QueryResponse, SourceItem
from app.services import rag
from app.services.embeddings import EmbeddingError, EmbeddingProvider, get_embedding_provider
from app.services.llm import LLMError, LLMProvider, get_llm_provider

router = APIRouter(prefix="/api/v1", tags=["query"])


@router.post(
    "/query",
    response_model=QueryResponse,
    responses={
        422: {"description": "Pregunta vacía o demasiado larga"},
        503: {"description": "Proveedor de embeddings o de LLM no configurado o no disponible"},
    },
)
def query_documents(
    request: QueryRequest,
    session: Annotated[Session, Depends(get_db)],
    embedder: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> QueryResponse:
    """Responde usando solo los documentos cargados. Si no hay evidencia suficiente, lo dice
    explícitamente (`insufficient_evidence: true`) en lugar de inventar una respuesta."""
    question = request.question.strip()
    if not question:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "La pregunta está vacía.")
    if len(question) > settings.max_query_chars:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"La pregunta supera el máximo de {settings.max_query_chars} caracteres.",
        )

    try:
        result = rag.answer_question(session, embedder, llm, settings, question)
    except (EmbeddingError, LLMError) as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, exc.message) from None

    return QueryResponse(
        answer=result.answer,
        sources=[SourceItem(**asdict(source)) for source in result.sources],
        insufficient_evidence=result.insufficient_evidence,
    )
