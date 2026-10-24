"""Procesamiento de documentos fuera de la petición HTTP (PROCESSING_MODE=background).

La subida guarda el archivo, registra el documento como `pending` y responde enseguida; el
procesamiento (extracción, embeddings, resumen) sigue en un hilo del servidor. Un semáforo
limita cuántos documentos se procesan a la vez. Si el servidor se reinicia a mitad, los
documentos que quedaron `pending` o `processing` se retoman al arrancar.

Es la versión de un solo proceso de lo previsto para la Fase 8 (una cola SQS y un worker):
`process_document` solo necesita el id del documento, así que el cambio no lo afecta.
"""

import logging
import threading
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.repositories.documents import DocumentRepository
from app.services import ingestion
from app.services.embeddings import EmbeddingError, EmbeddingProvider, build_embedding_provider
from app.services.llm import LLMError, LLMProvider, build_llm_provider
from app.services.storage import LocalFileStorage

logger = logging.getLogger(__name__)

_slots: threading.BoundedSemaphore | None = None
_slots_lock = threading.Lock()


def _processing_slots(settings: Settings) -> threading.BoundedSemaphore:
    """Semáforo compartido por todo el proceso (se crea con el primer documento)."""
    global _slots
    with _slots_lock:
        if _slots is None:
            _slots = threading.BoundedSemaphore(settings.processing_concurrency)
        return _slots


def process_in_background(
    session_factory: sessionmaker[Session],
    storage: LocalFileStorage,
    embedder: EmbeddingProvider,
    llm: LLMProvider | None,
    settings: Settings,
    document_id: UUID,
) -> None:
    """Procesa un documento con su propia sesión (la de la petición ya se cerró).

    process_document ya deja el documento `failed` con un mensaje si algo sale mal; aquí solo
    se registra un fallo inesperado (p. ej. la base de datos caída) para no perderlo en silencio.
    """
    with _processing_slots(settings):
        try:
            with session_factory() as session:
                ingestion.process_document(session, storage, embedder, llm, settings, document_id)
        except Exception:
            logger.exception("Falló el procesamiento en segundo plano de %s", document_id)


def resume_unfinished(session_factory: sessionmaker[Session], settings: Settings) -> int:
    """Retoma los documentos que quedaron a medias. Se llama al arrancar el servidor."""
    with session_factory() as session:
        unfinished = [d.id for d in DocumentRepository(session).list_unfinished()]
    if not unfinished:
        return 0
    try:
        embedder = build_embedding_provider(settings)
    except EmbeddingError:
        logger.warning(
            "Hay %d documentos sin procesar, pero no hay proveedor de embeddings: se quedan "
            "pendientes (se pueden reprocesar)",
            len(unfinished),
        )
        return 0
    try:
        llm: LLMProvider | None = build_llm_provider(settings)
    except LLMError:
        llm = None
    storage = LocalFileStorage(settings.storage_dir)
    logger.info("Retomando %d documentos que quedaron a medias", len(unfinished))
    for document_id in unfinished:
        process_in_background(session_factory, storage, embedder, llm, settings, document_id)
    return len(unfinished)
