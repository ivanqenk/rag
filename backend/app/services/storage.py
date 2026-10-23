"""Almacenamiento de archivos subidos en disco local (desarrollo). S3 llegará en la Fase 8."""

import re
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import Depends

from app.core.config import Settings, get_settings

# Solo aceptamos claves generadas por nosotros: 32 hex + ".pdf". Así una clave nunca
# puede contener "../" ni rutas absolutas (path traversal).
_STORAGE_KEY_PATTERN = re.compile(r"^[0-9a-f]{32}\.pdf$")


class LocalFileStorage:
    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    def save(self, data: bytes) -> str:
        """Guarda el contenido con un nombre aleatorio y devuelve su clave interna."""
        self._base_dir.mkdir(parents=True, exist_ok=True)
        storage_key = f"{uuid4().hex}.pdf"
        # "xb": falla si el archivo ya existiera en lugar de sobrescribirlo.
        with open(self._path(storage_key), "xb") as file:
            file.write(data)
        return storage_key

    def read(self, storage_key: str) -> bytes:
        return self._path(storage_key).read_bytes()

    def delete(self, storage_key: str) -> None:
        self._path(storage_key).unlink(missing_ok=True)

    def _path(self, storage_key: str) -> Path:
        if not _STORAGE_KEY_PATTERN.fullmatch(storage_key):
            raise ValueError("Clave de almacenamiento inválida")
        return self._base_dir / storage_key


def get_storage(settings: Annotated[Settings, Depends(get_settings)]) -> LocalFileStorage:
    """Dependencia de FastAPI. Las pruebas la sustituyen por una carpeta temporal."""
    return LocalFileStorage(settings.storage_dir)
