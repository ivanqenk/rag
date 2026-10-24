"""Endpoints de la papelera: listar, restaurar y eliminar definitivamente."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.document import Document
from app.repositories.documents import DocumentRepository, get_document_repository
from app.schemas.document import DocumentRead, TrashPage
from app.services import ingestion, trash
from app.services.storage import LocalFileStorage, get_storage

router = APIRouter(prefix="/api/v1/trash", tags=["trash"])

Repository = Annotated[DocumentRepository, Depends(get_document_repository)]
Storage = Annotated[LocalFileStorage, Depends(get_storage)]
DbSession = Annotated[Session, Depends(get_db)]

MAX_PAGE_SIZE = 100


@router.get("", response_model=TrashPage)
def list_trash(
    repository: Repository,
    settings: Annotated[Settings, Depends(get_settings)],
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TrashPage:
    """Documentos de la papelera, eliminados más recientemente primero."""
    documents, total = repository.list(limit=limit, offset=offset, trashed=True)
    return TrashPage(
        items=[DocumentRead.model_validate(document) for document in documents],
        total=total,
        limit=limit,
        offset=offset,
        retention_days=settings.trash_retention_days,
    )


@router.post(
    "/{document_id}/restore",
    response_model=DocumentRead,
    responses={404: {"description": "El documento no está en la papelera"}},
)
def restore_document(document_id: UUID, repository: Repository, session: DbSession) -> DocumentRead:
    """Saca el documento de la papelera; vuelve a aparecer en la biblioteca y en las respuestas
    sin reprocesarlo."""
    return DocumentRead.model_validate(
        trash.restore(session, _get_trashed(repository, document_id))
    )


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "El documento no está en la papelera"}},
)
def delete_permanently(
    document_id: UUID, repository: Repository, session: DbSession, storage: Storage
) -> None:
    """Borra del todo: registro, fragmentos, embeddings y archivo. No se puede deshacer.
    Solo para documentos que ya están en la papelera."""
    ingestion.delete_document(session, storage, _get_trashed(repository, document_id))


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def empty_trash(session: DbSession, storage: Storage) -> None:
    """Vacía la papelera: borra del todo todos sus documentos."""
    trash.empty_trash(session, storage)


def _get_trashed(repository: DocumentRepository, document_id: UUID) -> Document:
    document = repository.get(document_id)
    if document is None or document.deleted_at is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El documento no está en la papelera.")
    return document
