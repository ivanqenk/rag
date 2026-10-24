"""Validación común del ámbito de búsqueda (carpeta, documento, página) de /query y /search."""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.repositories.documents import DocumentRepository
from app.repositories.folders import FolderRepository
from app.schemas.query import SearchScope


def check_scope_exists(session: Session, scope: SearchScope) -> None:
    """404 si la carpeta o el documento no existen, en lugar de responder «sin evidencia»."""
    if scope.folder_id and FolderRepository(session).get(scope.folder_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Carpeta no encontrada.")
    if scope.document_id:
        document = DocumentRepository(session).get(scope.document_id)
        # Un documento en la papelera no se puede consultar.
        if document is None or document.deleted_at is not None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado.")
