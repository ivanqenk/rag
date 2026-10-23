"""Flujo completo de subida e ingestión contra PostgreSQL real."""

from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.main import app
from app.repositories.documents import DocumentRepository
from app.services import ingestion
from app.services.storage import LocalFileStorage
from tests.pdf_factory import make_encrypted_pdf, make_pdf

LONG_TEXT = " ".join(f"Oración número {i} del manual de pruebas." for i in range(120))


@pytest.fixture
def storage_dir(tmp_path: Path) -> Path:
    return tmp_path / "storage"


@pytest.fixture
def settings(storage_dir: Path) -> Settings:
    return Settings(
        storage_dir=storage_dir, max_upload_size_mb=1, chunk_size=500, chunk_overlap=100
    )


@pytest.fixture
def upload_client(client: TestClient, settings: Settings) -> Iterator[TestClient]:
    # get_storage depende de get_settings, así que basta con sustituir la configuración.
    app.dependency_overrides[get_settings] = lambda: settings
    yield client


def upload(client: TestClient, data: bytes, filename: str = "manual.pdf") -> dict:
    response = client.post("/api/v1/documents", files={"file": (filename, data, "application/pdf")})
    return {"status_code": response.status_code, "body": response.json()}


def stored_files(storage_dir: Path) -> list[Path]:
    return list(storage_dir.iterdir()) if storage_dir.exists() else []


def test_valid_pdf_is_processed_into_traceable_chunks(
    upload_client: TestClient, db_session: Session, storage_dir: Path
) -> None:
    result = upload(upload_client, make_pdf([LONG_TEXT, "", "Conclusión final."]))

    assert result["status_code"] == 201
    body = result["body"]
    assert body["status"] == "completed"
    assert body["processed_at"] is not None
    assert body["original_filename"] == "manual.pdf"
    assert "storage_key" not in body

    chunks = DocumentRepository(db_session).list_chunks(UUID(body["id"]))
    assert len(chunks) > 1
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert {c.page_number for c in chunks} == {1, 3}  # la página 2 no tiene texto
    assert "Conclusión final." in chunks[-1].text
    assert len(stored_files(storage_dir)) == 1


def test_pdf_without_text_is_registered_as_failed(
    upload_client: TestClient, db_session: Session
) -> None:
    result = upload(upload_client, make_pdf(["", ""]))

    assert result["status_code"] == 201
    body = result["body"]
    assert body["status"] == "failed"
    assert "no contiene texto" in body["error_message"]
    assert DocumentRepository(db_session).list_chunks(UUID(body["id"])) == []


@pytest.mark.parametrize(
    ("data", "filename", "expected_status"),
    [
        (b"", "vacio.pdf", 400),
        (b"Hola, soy un archivo de texto", "notas.pdf", 415),
        (make_pdf(["hola"]), "falso.txt", 415),
        (b"%PDF-1.7\nesto no es un PDF de verdad", "roto.pdf", 422),
        (make_encrypted_pdf(), "cifrado.pdf", 422),
    ],
)
def test_invalid_uploads_are_rejected_without_side_effects(
    upload_client: TestClient,
    db_session: Session,
    storage_dir: Path,
    data: bytes,
    filename: str,
    expected_status: int,
) -> None:
    result = upload(upload_client, data, filename)

    assert result["status_code"] == expected_status
    assert isinstance(result["body"]["detail"], str)
    # Nada guardado: ni registro ni archivo.
    assert DocumentRepository(db_session).list(limit=10, offset=0)[1] == 0
    assert stored_files(storage_dir) == []


def test_upload_over_size_limit_is_rejected(
    upload_client: TestClient, db_session: Session, storage_dir: Path
) -> None:
    too_big = b"%PDF-1.7\n" + b"0" * (1024 * 1024)  # límite de la prueba: 1 MB

    result = upload(upload_client, too_big)

    assert result["status_code"] == 413
    assert DocumentRepository(db_session).list(limit=10, offset=0)[1] == 0
    assert stored_files(storage_dir) == []


def test_client_filename_cannot_choose_storage_path(
    upload_client: TestClient, storage_dir: Path
) -> None:
    result = upload(upload_client, make_pdf(["hola"]), filename="../../../etc/evil.pdf")

    assert result["status_code"] == 201
    assert result["body"]["original_filename"] == "evil.pdf"
    files = stored_files(storage_dir)
    assert len(files) == 1
    assert files[0].parent == storage_dir
    assert files[0].name != "evil.pdf"


def test_failure_while_saving_chunks_leaves_no_partial_chunks(
    db_session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = LocalFileStorage(settings.storage_dir)
    document = ingestion.register_upload(
        db_session, storage, settings, "manual.pdf", make_pdf([LONG_TEXT])
    )
    original_replace = DocumentRepository.replace_chunks

    def replace_then_crash(self: DocumentRepository, *args: object, **kwargs: object) -> None:
        original_replace(self, *args, **kwargs)  # type: ignore[arg-type]
        raise RuntimeError("fallo simulado de la base de datos")

    monkeypatch.setattr(DocumentRepository, "replace_chunks", replace_then_crash)

    result = ingestion.process_document(db_session, storage, settings, document.id)

    assert result.status == "failed"
    assert result.error_code == "processing_error"
    # El mensaje al usuario no filtra el detalle técnico de la excepción.
    assert "fallo simulado" not in (result.error_message or "")
    assert DocumentRepository(db_session).list_chunks(document.id) == []


def test_reprocessing_replaces_chunks_instead_of_duplicating(
    db_session: Session, settings: Settings
) -> None:
    storage = LocalFileStorage(settings.storage_dir)
    document = ingestion.register_upload(
        db_session, storage, settings, "manual.pdf", make_pdf([LONG_TEXT])
    )

    ingestion.process_document(db_session, storage, settings, document.id)
    first_count = len(DocumentRepository(db_session).list_chunks(document.id))
    ingestion.process_document(db_session, storage, settings, document.id)

    assert len(DocumentRepository(db_session).list_chunks(document.id)) == first_count
