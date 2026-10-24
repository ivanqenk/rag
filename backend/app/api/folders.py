"""Endpoints HTTP de carpetas."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.folder import Folder
from app.repositories.folders import (
    DuplicateFolderNameError,
    FolderRepository,
    get_folder_repository,
)
from app.schemas.folder import FolderRead, FolderWrite

router = APIRouter(prefix="/api/v1/folders", tags=["folders"])

Repository = Annotated[FolderRepository, Depends(get_folder_repository)]

DUPLICATE_NAME = "Ya existe una carpeta con ese nombre."


@router.get("", response_model=list[FolderRead])
def list_folders(repository: Repository) -> list[FolderRead]:
    """Todas las carpetas, por nombre, con su número de documentos."""
    return [_read(folder, count) for folder, count in repository.list_with_counts()]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=FolderRead,
    responses={409: {"description": "Ya existe una carpeta con ese nombre"}},
)
def create_folder(body: FolderWrite, repository: Repository) -> FolderRead:
    try:
        folder = repository.create(body.name)
    except DuplicateFolderNameError:
        raise HTTPException(status.HTTP_409_CONFLICT, DUPLICATE_NAME) from None
    return _read(folder, 0)


@router.patch(
    "/{folder_id}",
    response_model=FolderRead,
    responses={
        404: {"description": "Carpeta no encontrada"},
        409: {"description": "Ya existe una carpeta con ese nombre"},
    },
)
def rename_folder(folder_id: UUID, body: FolderWrite, repository: Repository) -> FolderRead:
    folder = _get_or_404(repository, folder_id)
    try:
        folder = repository.rename(folder, body.name)
    except DuplicateFolderNameError:
        raise HTTPException(status.HTTP_409_CONFLICT, DUPLICATE_NAME) from None
    return _read(folder, repository.count_documents(folder.id))


@router.delete(
    "/{folder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "Carpeta no encontrada"}},
)
def delete_folder(folder_id: UUID, repository: Repository) -> None:
    """Borra la carpeta. Sus documentos NO se borran: quedan sin carpeta."""
    repository.delete(_get_or_404(repository, folder_id))


def _read(folder: Folder, document_count: int) -> FolderRead:
    return FolderRead(
        id=folder.id, name=folder.name, created_at=folder.created_at, document_count=document_count
    )


def _get_or_404(repository: FolderRepository, folder_id: UUID) -> Folder:
    folder = repository.get(folder_id)
    if folder is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Carpeta no encontrada.")
    return folder
