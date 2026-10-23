"""Endpoints HTTP de documentos. Solo traducen HTTP <-> repositorio; sin lógica de negocio."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.repositories.documents import DocumentRepository, get_document_repository
from app.schemas.document import DocumentPage, DocumentRead

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

Repository = Annotated[DocumentRepository, Depends(get_document_repository)]

MAX_PAGE_SIZE = 100


@router.get("", response_model=DocumentPage)
def list_documents(
    repository: Repository,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentPage:
    """Lista documentos ordenados por fecha de creación descendente."""
    documents, total = repository.list(limit=limit, offset=offset)
    items = [DocumentRead.model_validate(document) for document in documents]
    return DocumentPage(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/{document_id}",
    response_model=DocumentRead,
    responses={404: {"description": "Documento no encontrado"}},
)
def get_document(document_id: UUID, repository: Repository) -> DocumentRead:
    """Devuelve los metadatos y el estado de un documento."""
    document = repository.get(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return DocumentRead.model_validate(document)
