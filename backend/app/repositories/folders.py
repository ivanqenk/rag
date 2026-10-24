"""Acceso a datos de carpetas."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.document import Document
from app.models.folder import Folder


class DuplicateFolderNameError(Exception):
    """Ya existe una carpeta con ese nombre (sin distinguir mayúsculas)."""


class FolderRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_with_counts(self) -> list[tuple[Folder, int]]:
        """Carpetas por nombre, con cuántos documentos tiene cada una."""
        statement = (
            select(Folder, func.count(Document.id))
            # Los documentos de la papelera no cuentan.
            .outerjoin(Document, (Document.folder_id == Folder.id) & Document.deleted_at.is_(None))
            .group_by(Folder.id)
            .order_by(func.lower(Folder.name))
        )
        return [(folder, count) for folder, count in self._session.execute(statement)]

    def get(self, folder_id: UUID) -> Folder | None:
        return self._session.get(Folder, folder_id)

    def count_documents(self, folder_id: UUID) -> int:
        statement = select(func.count()).where(
            Document.folder_id == folder_id, Document.deleted_at.is_(None)
        )
        return self._session.scalar(statement) or 0

    def create(self, name: str) -> Folder:
        folder = Folder(name=name)
        self._session.add(folder)
        self._commit()
        self._session.refresh(folder)
        return folder

    def rename(self, folder: Folder, name: str) -> Folder:
        folder.name = name
        self._commit()
        return folder

    def delete(self, folder: Folder) -> None:
        """Borra la carpeta; sus documentos quedan sin carpeta (ON DELETE SET NULL)."""
        self._session.delete(folder)
        self._session.commit()

    def _commit(self) -> None:
        # El índice único de la base de datos es la fuente de verdad: comprobar antes con
        # una consulta dejaría una carrera entre dos peticiones simultáneas.
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise DuplicateFolderNameError from exc


def get_folder_repository(session: Annotated[Session, Depends(get_db)]) -> FolderRepository:
    return FolderRepository(session)
