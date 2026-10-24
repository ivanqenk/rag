"""Endpoints HTTP de documentos. Solo traducen HTTP <-> servicios; sin lógica de negocio."""

from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.session import get_db, get_session_factory
from app.models.document import Document
from app.repositories.documents import DocumentRepository, get_document_repository
from app.repositories.folders import FolderRepository
from app.schemas.document import DocumentPage, DocumentRead, DocumentUpdate
from app.services import ingestion, processing, trash
from app.services.embeddings import EmbeddingProvider, get_embedding_provider
from app.services.llm import LLMProvider, get_optional_llm_provider
from app.services.pdf_extraction import InvalidPdfError
from app.services.storage import LocalFileStorage, get_storage

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

Repository = Annotated[DocumentRepository, Depends(get_document_repository)]
Embedder = Annotated[EmbeddingProvider, Depends(get_embedding_provider)]
# Opcional: sin LLM configurado el documento se procesa igual, solo que sin resumen.
OptionalLLM = Annotated[LLMProvider | None, Depends(get_optional_llm_provider)]
SessionFactory = Annotated[sessionmaker[Session], Depends(get_session_factory)]

MAX_PAGE_SIZE = 100


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentRead,
    responses={
        202: {"description": "Recibido; se procesa en segundo plano (PROCESSING_MODE=background)"},
        400: {"description": "Archivo vacío"},
        404: {"description": "La carpeta indicada no existe"},
        413: {"description": "El archivo supera el tamaño máximo"},
        415: {"description": "El archivo no es un PDF"},
        422: {"description": "PDF dañado, cifrado, sin páginas o con demasiadas páginas"},
        503: {"description": "Proveedor de embeddings no configurado"},
    },
)
def upload_document(
    file: UploadFile,
    response: Response,
    background_tasks: BackgroundTasks,
    session_factory: SessionFactory,
    session: Annotated[Session, Depends(get_db)],
    storage: Annotated[LocalFileStorage, Depends(get_storage)],
    embedder: Embedder,
    llm: OptionalLLM,
    settings: Annotated[Settings, Depends(get_settings)],
    folder_id: Annotated[UUID | None, Form(description="Carpeta donde guardarlo")] = None,
) -> DocumentRead:
    """Sube un PDF y lo procesa (extracción, fragmentación, embeddings y resumen).

    Con PROCESSING_MODE=background (por defecto) responde 202 en cuanto el archivo está guardado
    y validado, con `status = "pending"`; el cliente consulta `GET /documents/{id}` hasta que
    sea `completed` o `failed`. Con `sync` espera y responde 201 con el estado final. Un fallo
    de procesamiento (p. ej. PDF sin texto) no es un error HTTP: el documento queda `failed`
    con un `error_message` explicativo.
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

    if folder_id is not None:
        _check_folder_exists(session, folder_id)

    try:
        document = ingestion.register_upload(
            session, storage, settings, file.filename, data, folder_id
        )
    except ingestion.EmptyFileError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El archivo está vacío.") from None
    except ingestion.UnsupportedFileTypeError:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Solo se admiten archivos PDF."
        ) from None
    except InvalidPdfError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.message) from None

    return _process(
        document,
        response,
        background_tasks,
        session,
        session_factory,
        storage,
        embedder,
        llm,
        settings,
    )


@router.get("", response_model=DocumentPage)
def list_documents(
    repository: Repository,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    folder_id: Annotated[UUID | None, Query(description="Solo los de esta carpeta")] = None,
) -> DocumentPage:
    """Lista documentos ordenados por fecha de creación descendente."""
    documents, total = repository.list(limit=limit, offset=offset, folder_id=folder_id)
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


@router.patch(
    "/{document_id}",
    response_model=DocumentRead,
    responses={
        404: {"description": "Documento o carpeta no encontrados"},
        409: {"description": "El documento está en la papelera"},
    },
)
def update_document(
    document_id: UUID,
    body: DocumentUpdate,
    repository: Repository,
    session: Annotated[Session, Depends(get_db)],
) -> DocumentRead:
    """Mueve el documento a una carpeta (`folder_id`) o lo saca de ella (`null`)."""
    document = _get_active_or_409(repository, document_id)
    if body.folder_id is not None:
        _check_folder_exists(session, body.folder_id)
    return DocumentRead.model_validate(repository.move(document, body.folder_id))


@router.get(
    "/{document_id}/file",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "El PDF original"},
        404: {"description": "Documento o archivo no encontrado"},
    },
)
def get_document_file(
    document_id: UUID,
    repository: Repository,
    storage: Annotated[LocalFileStorage, Depends(get_storage)],
) -> Response:
    """Devuelve el PDF original para verlo en el navegador (admite `#page=N` en la URL)."""
    document = _get_or_404(repository, document_id)
    try:
        data = storage.read(document.storage_key)
    except FileNotFoundError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "El archivo original no está disponible."
        ) from None
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": _inline_disposition(document.original_filename),
            # El tipo es fijo y la firma %PDF- se validó al subirlo: que el navegador no
            # intente adivinar otro (p. ej. HTML).
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-cache",
        },
    )


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "Documento no encontrado"}},
)
def delete_document(
    document_id: UUID,
    repository: Repository,
    session: Annotated[Session, Depends(get_db)],
) -> None:
    """Mueve el documento a la papelera: deja de aparecer en la biblioteca y en las
    respuestas, y se puede restaurar durante TRASH_RETENTION_DAYS días (ver /api/v1/trash)."""
    document = _get_or_404(repository, document_id)
    if document.deleted_at is None:
        trash.move_to_trash(session, document)


@router.post(
    "/{document_id}/reprocess",
    response_model=DocumentRead,
    responses={
        202: {"description": "En cola; se procesa en segundo plano (PROCESSING_MODE=background)"},
        404: {"description": "Documento no encontrado"},
        409: {"description": "El documento está en la papelera"},
        503: {"description": "Proveedor de embeddings no configurado"},
    },
)
def reprocess_document(
    document_id: UUID,
    response: Response,
    background_tasks: BackgroundTasks,
    session_factory: SessionFactory,
    repository: Repository,
    session: Annotated[Session, Depends(get_db)],
    storage: Annotated[LocalFileStorage, Depends(get_storage)],
    embedder: Embedder,
    llm: OptionalLLM,
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentRead:
    """Vuelve a procesar un documento: tras un fallo, o tras cambiar de modelo de embeddings.
    Mismo comportamiento que la subida según PROCESSING_MODE (202 + `pending`, o 201)."""
    document = _get_active_or_409(repository, document_id)
    if settings.processing_mode == "background":
        document = repository.mark_pending(document)
    return _process(
        document,
        response,
        background_tasks,
        session,
        session_factory,
        storage,
        embedder,
        llm,
        settings,
    )


def _inline_disposition(filename: str) -> str:
    """`inline` para que se abra en el navegador. `filename*` lleva el nombre en UTF-8
    (RFC 6266); `filename` es la alternativa ASCII sin comillas ni barras invertidas."""
    ascii_name = filename.encode("ascii", "ignore").decode().replace('"', "").replace("\\", "")
    return (
        f"inline; filename=\"{ascii_name or 'documento.pdf'}\"; filename*=UTF-8''{quote(filename)}"
    )


def _process(
    document: Document,
    response: Response,
    background_tasks: BackgroundTasks,
    session: Session,
    session_factory: sessionmaker[Session],
    storage: LocalFileStorage,
    embedder: EmbeddingProvider,
    llm: LLMProvider | None,
    settings: Settings,
) -> DocumentRead:
    """Procesa ya (sync, 201) o después de responder (background, 202)."""
    if settings.processing_mode == "sync":
        document = ingestion.process_document(
            session, storage, embedder, llm, settings, document.id
        )
        return DocumentRead.model_validate(document)
    background_tasks.add_task(
        processing.process_in_background,
        session_factory,
        storage,
        embedder,
        llm,
        settings,
        document.id,
    )
    response.status_code = status.HTTP_202_ACCEPTED
    return DocumentRead.model_validate(document)


def _check_folder_exists(session: Session, folder_id: UUID) -> None:
    if FolderRepository(session).get(folder_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Carpeta no encontrada.")


def _get_active_or_409(repository: DocumentRepository, document_id: UUID) -> Document:
    document = _get_or_404(repository, document_id)
    if document.deleted_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "El documento está en la papelera. Restáuralo primero."
        )
    return document


def _get_or_404(repository: DocumentRepository, document_id: UUID) -> Document:
    document = repository.get(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document
