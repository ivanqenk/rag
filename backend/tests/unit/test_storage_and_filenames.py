from pathlib import Path

import pytest

from app.services.ingestion import sanitize_filename
from app.services.storage import LocalFileStorage


def test_save_read_delete_roundtrip(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path)

    key = storage.save(b"%PDF-contenido")

    assert storage.read(key) == b"%PDF-contenido"
    # El nombre en disco es aleatorio, no el que envió el cliente.
    assert [p.name for p in tmp_path.iterdir()] == [key]
    storage.delete(key)
    assert list(tmp_path.iterdir()) == []


def test_each_save_uses_a_new_key(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path)

    assert storage.save(b"a") != storage.save(b"a")


@pytest.mark.parametrize(
    "key",
    ["../../etc/passwd", "/etc/passwd", "a.pdf", "../" + "0" * 32 + ".pdf", "0" * 32 + ".exe"],
)
def test_rejects_keys_that_could_escape_the_storage_dir(tmp_path: Path, key: str) -> None:
    with pytest.raises(ValueError):
        LocalFileStorage(tmp_path).read(key)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("informe.pdf", "informe.pdf"),
        ("../../etc/informe.pdf", "informe.pdf"),
        ("C:\\Users\\ana\\informe.pdf", "informe.pdf"),
        ("in\x00for\nme.pdf", "informe.pdf"),
        ("", "documento.pdf"),
        (None, "documento.pdf"),
    ],
)
def test_sanitize_filename(raw: str | None, expected: str) -> None:
    assert sanitize_filename(raw) == expected


def test_sanitize_filename_limits_length_but_keeps_extension() -> None:
    name = sanitize_filename("a" * 400 + ".pdf")

    assert len(name) == 255
    assert name.endswith(".pdf")
