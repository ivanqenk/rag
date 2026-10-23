"""Ingestión de documentos: registrar una subida y procesarla.

Está separada en dos pasos para que, en la Fase 8, `process_document` pueda ejecutarse en
un worker (SQS) sin cambiar nada: solo necesita el id del documento.
"""

import hashlib
import logging
from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.document import Document
from app.repositories.documents import DocumentRepository
from app.schemas.document import DocumentStatus
from app.services.chunking import chunk_pages
from app.services.pdf_extraction import (
    InvalidPdfError,
    extract_pages,
    has_pdf_signature,
    validate_pdf,
)
from app.services.storage import LocalFileStorage

logger = logging.getLogger(__name__)

# Coincide con el tamaño de la columna documents.original_filename.
_MAX_FILENAME_LENGTH = 255


class EmptyFileError(Exception):
    pass


class UnsupportedFileTypeError(Exception):
    pass


def sanitize_filename(filename: str | None) -> str:
    """Conserva solo el nombre (sin carpetas) y quita caracteres no imprimibles.

    El nombre solo se muestra al usuario; nunca se usa para construir rutas en disco.
    """
    name = PurePosixPath((filename or "").replace("\\", "/")).name
    name = "".join(char for char in name if char.isprintable()).strip()
    if len(name) > _MAX_FILENAME_LENGTH:
        # Recorta el nombre pero conserva la extensión, que se valida después.
        suffix = PurePosixPath(name).suffix[:10]
        name = name[: _MAX_FILENAME_LENGTH - len(suffix)] + suffix
    return name or "documento.pdf"


def register_upload(
    session: Session,
    storage: LocalFileStorage,
    settings: Settings,
    filename: str | None,
    data: bytes,
) -> Document:
    """Valida el archivo, lo guarda y crea el registro con estado `pending`.

    Si la validación falla no se guarda nada (ni archivo ni registro).
    """
    if not data:
        raise EmptyFileError
    # Dos señales independientes: la extensión que manda el cliente y el contenido real.
    # El Content-Type del cliente se ignora: lo controla el cliente y no aporta garantías.
    safe_name = sanitize_filename(filename)
    if not safe_name.lower().endswith(".pdf") or not has_pdf_signature(data):
        raise UnsupportedFileTypeError
    validate_pdf(data, max_pages=settings.max_pdf_pages)

    storage_key = storage.save(data)
    try:
        return DocumentRepository(session).create(
            original_filename=safe_name,
            storage_key=storage_key,
            content_type="application/pdf",
            size_bytes=len(data),
            checksum_sha256=hashlib.sha256(data).hexdigest(),
        )
    except Exception:
        # Sin registro en la base, el archivo quedaría huérfano.
        storage.delete(storage_key)
        raise


def process_document(
    session: Session, storage: LocalFileStorage, settings: Settings, document_id: UUID
) -> Document:
    """Extrae, fragmenta y guarda el texto. Deja el documento en `completed` o `failed`.

    Los fragmentos y el estado `completed` se confirman en una sola transacción: si algo
    falla, no quedan fragmentos parciales de un documento que no está completo.
    """
    repository = DocumentRepository(session)
    document = repository.get(document_id)
    if document is None:
        raise ValueError(f"Documento {document_id} no existe")

    document.status = DocumentStatus.PROCESSING
    session.commit()

    try:
        pages = extract_pages(storage.read(document.storage_key))
        chunks = chunk_pages(pages, settings.chunk_size, settings.chunk_overlap)
        if not chunks:
            raise InvalidPdfError(
                "no_extractable_text",
                "El PDF no contiene texto extraíble. Los PDF escaneados (imágenes) "
                "no están soportados todavía.",
            )
        repository.replace_chunks(document.id, chunks)
        document.status = DocumentStatus.COMPLETED
        document.error_code = None
        document.error_message = None
        document.processed_at = datetime.now(UTC)
        session.commit()
        logger.info("Documento %s procesado: %d fragmentos", document.id, len(chunks))
    except Exception as exc:
        session.rollback()
        if isinstance(exc, InvalidPdfError):
            code, message = exc.code, exc.message
            logger.warning("Documento %s no procesable: %s", document_id, code)
        else:
            # El detalle técnico va al log; al usuario solo un mensaje genérico y seguro.
            code, message = "processing_error", "Error inesperado al procesar el documento."
            logger.exception("Error procesando el documento %s", document_id)
        document.status = DocumentStatus.FAILED
        document.error_code = code
        document.error_message = message
        session.commit()

    return document
