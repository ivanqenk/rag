"""Endpoints HTTP de documentos. Solo traducen HTTP <-> servicios; sin lógica de negocio."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.document import Document
from app.repositories.documents import DocumentRepository, get_document_repository
from app.schemas.document import DocumentPage, DocumentRead
from app.services import ingestion
from app.services.embeddings import EmbeddingProvider, get_embedding_provider
from app.services.pdf_extraction import InvalidPdfError
from app.services.storage import LocalFileStorage, get_storage

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

Repository = Annotated[DocumentRepository, Depends(get_document_repository)]
Embedder = Annotated[EmbeddingProvider, Depends(get_embedding_provider)]

MAX_PAGE_SIZE = 100


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentRead,
    responses={
        400: {"description": "Archivo vacío"},
        413: {"description": "El archivo supera el tamaño máximo"},
        415: {"description": "El archivo no es un PDF"},
        422: {"description": "PDF dañado, cifrado, sin páginas o con demasiadas páginas"},
        503: {"description": "Proveedor de embeddings no configurado"},
    },
)
def upload_document(
    file: UploadFile,
    session: Annotated[Session, Depends(get_db)],
    storage: Annotated[LocalFileStorage, Depends(get_storage)],
    embedder: Embedder,
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentRead:
    """Sube un PDF y lo procesa (extracción, fragmentación y embeddings).

    Devuelve 201 aunque el procesamiento falle (p. ej. PDF sin texto): el documento queda
    registrado con `status = "failed"` y un `error_message` explicativo.
    """
    max_bytes = settings.max_upload_size_bytes
    # Leemos como máximo un byte más del límite: suficiente para saber si lo supera
    # sin cargar en memoria un archivo arbitrariamente grande.
    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"El archivo supera el máximo de {settings.max_upload_size_mb} MB.",
        )

    try:
        document = ingestion.register_upload(session, storage, settings, file.filename, data)
    except ingestion.EmptyFileError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El archivo está vacío.") from None
    except ingestion.UnsupportedFileTypeError:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Solo se admiten archivos PDF."
        ) from None
    except InvalidPdfError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.message) from None

    # Procesamiento síncrono en el MVP; en la Fase 8 esto será un mensaje a una cola.
    document = ingestion.process_document(session, storage, embedder, settings, document.id)
    return DocumentRead.model_validate(document)


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
    return DocumentRead.model_validate(_get_or_404(repository, document_id))


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "Documento no encontrado"}},
)
def delete_document(
    document_id: UUID,
    repository: Repository,
    session: Annotated[Session, Depends(get_db)],
    storage: Annotated[LocalFileStorage, Depends(get_storage)],
) -> None:
    """Elimina el documento, sus fragmentos y embeddings, y el archivo almacenado."""
    ingestion.delete_document(session, storage, _get_or_404(repository, document_id))


@router.post(
    "/{document_id}/reprocess",
    response_model=DocumentRead,
    responses={
        404: {"description": "Documento no encontrado"},
        503: {"description": "Proveedor de embeddings no configurado"},
    },
)
def reprocess_document(
    document_id: UUID,
    repository: Repository,
    session: Annotated[Session, Depends(get_db)],
    storage: Annotated[LocalFileStorage, Depends(get_storage)],
    embedder: Embedder,
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentRead:
    """Vuelve a procesar un documento: tras un fallo, o tras cambiar de modelo de embeddings."""
    document = _get_or_404(repository, document_id)
    document = ingestion.process_document(session, storage, embedder, settings, document.id)
    return DocumentRead.model_validate(document)


def _get_or_404(repository: DocumentRepository, document_id: UUID) -> Document:
    document = repository.get(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document
