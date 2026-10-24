"""Papelera: eliminar es reversible durante TRASH_RETENTION_DAYS días.

Un documento en la papelera no aparece en la biblioteca, ni en las búsquedas, ni en las
respuestas, pero conserva su archivo, sus fragmentos y sus embeddings, así que restaurarlo
es instantáneo y no cuesta nada. Pasado el plazo se borra del todo (purge_expired).
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.models.document import Document
from app.repositories.documents import DocumentRepository
from app.services import ingestion
from app.services.storage import LocalFileStorage

logger = logging.getLogger(__name__)


def move_to_trash(session: Session, document: Document) -> Document:
    return DocumentRepository(session).set_deleted_at(document, datetime.now(UTC))


def restore(session: Session, document: Document) -> Document:
    return DocumentRepository(session).set_deleted_at(document, None)


def purge_expired(
    session: Session, storage: LocalFileStorage, settings: Settings, now: datetime | None = None
) -> int:
    """Borra del todo los documentos que llevan más del plazo en la papelera."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=settings.trash_retention_days)
    expired = DocumentRepository(session).list_trashed_before(cutoff)
    for document in expired:
        ingestion.delete_document(session, storage, document)
    if expired:
        logger.info("Papelera: %d documentos eliminados definitivamente", len(expired))
    return len(expired)


def empty_trash(session: Session, storage: LocalFileStorage) -> int:
    trashed = DocumentRepository(session).list_all_trashed()
    for document in trashed:
        ingestion.delete_document(session, storage, document)
    return len(trashed)


async def purge_periodically(session_factory: sessionmaker[Session], settings: Settings) -> None:
    """Tarea de fondo del servidor: purga al arrancar y luego cada intervalo.

    Un fallo (p. ej. la base de datos caída un momento) se registra y se reintenta en la
    siguiente vuelta, sin tumbar la aplicación. Con varias réplicas cada una purgaría por su
    cuenta, lo que es inofensivo (borrar lo ya borrado no hace nada); en la Fase 8 sería un
    trabajo programado único.
    """
    storage = LocalFileStorage(settings.storage_dir)

    def run_once() -> None:
        with session_factory() as session:
            purge_expired(session, storage, settings)

    while True:
        try:
            await run_in_threadpool(run_once)
        except Exception:
            logger.exception("Falló la purga de la papelera; se reintentará")
        await asyncio.sleep(settings.trash_purge_interval_seconds)
