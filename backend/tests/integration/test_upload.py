"""Flujo completo de subida e ingestión contra PostgreSQL real."""

from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.documents import DocumentRepository
from app.services import ingestion
from app.services.embeddings import EmbeddingError, FakeEmbeddingProvider
from app.services.storage import LocalFileStorage
from tests.pdf_factory import make_encrypted_pdf, make_pdf

LONG_TEXT = " ".join(f"Oración número {i} del manual de pruebas." for i in range(120))


def upload(client: TestClient, data: bytes, filename: str = "manual.pdf") -> dict:
    response = client.post("/api/v1/documents", files={"file": (filename, data, "application/pdf")})
    return {"status_code": response.status_code, "body": response.json()}


def stored_files(storage_dir: Path) -> list[Path]:
    return list(storage_dir.iterdir()) if storage_dir.exists() else []


def test_valid_pdf_is_processed_into_traceable_chunks(
    client: TestClient, db_session: Session, storage_dir: Path
) -> None:
    result = upload(client, make_pdf([LONG_TEXT, "", "Conclusión final."]))

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


def test_pdf_without_text_is_registered_as_failed(client: TestClient, db_session: Session) -> None:
    result = upload(client, make_pdf(["", ""]))

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
    client: TestClient,
    db_session: Session,
    storage_dir: Path,
    data: bytes,
    filename: str,
    expected_status: int,
) -> None:
    result = upload(client, data, filename)

    assert result["status_code"] == expected_status
    assert isinstance(result["body"]["detail"], str)
    # Nada guardado: ni registro ni archivo.
    assert DocumentRepository(db_session).list(limit=10, offset=0)[1] == 0
    assert stored_files(storage_dir) == []


def test_upload_over_size_limit_is_rejected(
    client: TestClient, db_session: Session, storage_dir: Path
) -> None:
    too_big = b"%PDF-1.7\n" + b"0" * (1024 * 1024)  # límite de la prueba: 1 MB

    result = upload(client, too_big)

    assert result["status_code"] == 413
    assert DocumentRepository(db_session).list(limit=10, offset=0)[1] == 0
    assert stored_files(storage_dir) == []


def test_client_filename_cannot_choose_storage_path(client: TestClient, storage_dir: Path) -> None:
    result = upload(client, make_pdf(["hola"]), filename="../../../etc/evil.pdf")

    assert result["status_code"] == 201
    assert result["body"]["original_filename"] == "evil.pdf"
    files = stored_files(storage_dir)
    assert len(files) == 1
    assert files[0].parent == storage_dir
    assert files[0].name != "evil.pdf"


def test_failure_while_saving_chunks_leaves_no_partial_chunks(
    db_session: Session,
    settings: Settings,
    embedder: FakeEmbeddingProvider,
    monkeypatch: pytest.MonkeyPatch,
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

    result = ingestion.process_document(db_session, storage, embedder, settings, document.id)

    assert result.status == "failed"
    assert result.error_code == "processing_error"
    # El mensaje al usuario no filtra el detalle técnico de la excepción.
    assert "fallo simulado" not in (result.error_message or "")
    assert DocumentRepository(db_session).list_chunks(document.id) == []


def test_reprocessing_replaces_chunks_instead_of_duplicating(
    db_session: Session, settings: Settings, embedder: FakeEmbeddingProvider
) -> None:
    storage = LocalFileStorage(settings.storage_dir)
    document = ingestion.register_upload(
        db_session, storage, settings, "manual.pdf", make_pdf([LONG_TEXT])
    )

    ingestion.process_document(db_session, storage, embedder, settings, document.id)
    first_count = len(DocumentRepository(db_session).list_chunks(document.id))
    ingestion.process_document(db_session, storage, embedder, settings, document.id)

    assert len(DocumentRepository(db_session).list_chunks(document.id)) == first_count


class FailingEmbeddingProvider:
    model_name = "failing-v1"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingError("El proveedor de embeddings no está disponible. Inténtalo más tarde.")

    def embed_query(self, text: str) -> list[float]:
        raise EmbeddingError("El proveedor de embeddings no está disponible. Inténtalo más tarde.")


def test_chunks_are_stored_with_embedding_and_model(
    client: TestClient, db_session: Session, embedder: FakeEmbeddingProvider
) -> None:
    body = upload(client, make_pdf([LONG_TEXT]))["body"]

    chunks = DocumentRepository(db_session).list_chunks(UUID(body["id"]))
    assert chunks
    assert all(c.embedding_model == embedder.model_name for c in chunks)
    assert all(len(c.embedding) == 1536 for c in chunks)
    # Los vectores son datos sensibles: la API nunca los devuelve.
    assert "embedding" not in body


def test_embedding_failure_marks_failed_and_keeps_previous_chunks(
    db_session: Session, settings: Settings, embedder: FakeEmbeddingProvider
) -> None:
    storage = LocalFileStorage(settings.storage_dir)
    document = ingestion.register_upload(
        db_session, storage, settings, "manual.pdf", make_pdf([LONG_TEXT])
    )
    ingestion.process_document(db_session, storage, embedder, settings, document.id)
    previous = [c.id for c in DocumentRepository(db_session).list_chunks(document.id)]

    result = ingestion.process_document(
        db_session, storage, FailingEmbeddingProvider(), settings, document.id
    )

    assert result.status == "failed"
    assert result.error_code == "embedding_error"
    assert "no está disponible" in (result.error_message or "")
    # Los fragmentos válidos anteriores no se perdieron por el fallo.
    assert [c.id for c in DocumentRepository(db_session).list_chunks(document.id)] == previous


def test_reprocess_endpoint_recovers_a_failed_document(
    client: TestClient, db_session: Session, settings: Settings
) -> None:
    storage = LocalFileStorage(settings.storage_dir)
    document = ingestion.register_upload(
        db_session, storage, settings, "manual.pdf", make_pdf([LONG_TEXT])
    )
    ingestion.process_document(
        db_session, storage, FailingEmbeddingProvider(), settings, document.id
    )

    response = client.post(f"/api/v1/documents/{document.id}/reprocess")

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert DocumentRepository(db_session).list_chunks(document.id)


def test_delete_removes_document_chunks_and_file(
    client: TestClient, db_session: Session, storage_dir: Path
) -> None:
    body = upload(client, make_pdf([LONG_TEXT]))["body"]
    document_id = UUID(body["id"])
    assert stored_files(storage_dir)

    response = client.delete(f"/api/v1/documents/{document_id}")

    assert response.status_code == 204
    assert client.get(f"/api/v1/documents/{document_id}").status_code == 404
    assert DocumentRepository(db_session).list_chunks(document_id) == []
    assert stored_files(storage_dir) == []


def test_delete_unknown_document_returns_404(client: TestClient) -> None:
    assert client.delete(f"/api/v1/documents/{UUID(int=0)}").status_code == 404
