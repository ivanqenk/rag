"""Pruebas de la capa HTTP de documentos, sin base de datos (repositorio falso en memoria)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.documents import get_document_repository
from app.schemas.document import DocumentRead, DocumentStatus

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


class FakeDocumentRepository:
    """Imita los métodos de lectura de DocumentRepository usando una lista."""

    def __init__(self, documents: list[DocumentRead]) -> None:
        self._documents = {doc.id: doc for doc in documents}

    def list(self, limit: int, offset: int) -> tuple[list[DocumentRead], int]:
        ordered = sorted(self._documents.values(), key=lambda d: d.created_at, reverse=True)
        return ordered[offset : offset + limit], len(ordered)

    def get(self, document_id: UUID) -> DocumentRead | None:
        return self._documents.get(document_id)


def make_document(minutes: int, status: DocumentStatus = DocumentStatus.COMPLETED) -> DocumentRead:
    created = BASE_TIME + timedelta(minutes=minutes)
    return DocumentRead(
        id=uuid4(),
        original_filename=f"doc-{minutes}.pdf",
        content_type="application/pdf",
        size_bytes=1_000,
        status=status,
        created_at=created,
        updated_at=created,
    )


@pytest.fixture
def documents() -> list[DocumentRead]:
    # Se crean desordenados a propósito para comprobar el orden de la respuesta.
    return [make_document(10), make_document(30), make_document(20)]


@pytest.fixture
def client(documents: list[DocumentRead]) -> Iterator[TestClient]:
    repository = FakeDocumentRepository(documents)
    app.dependency_overrides[get_document_repository] = lambda: repository
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_documents_newest_first(client: TestClient) -> None:
    response = client.get("/api/v1/documents")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert [d["original_filename"] for d in body["items"]] == [
        "doc-30.pdf",
        "doc-20.pdf",
        "doc-10.pdf",
    ]


def test_list_documents_paginates(client: TestClient) -> None:
    response = client.get("/api/v1/documents", params={"limit": 1, "offset": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["limit"] == 1
    assert body["offset"] == 1
    assert [d["original_filename"] for d in body["items"]] == ["doc-20.pdf"]


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"limit": "abc"}],
)
def test_list_documents_rejects_invalid_pagination(
    client: TestClient, params: dict[str, object]
) -> None:
    response = client.get("/api/v1/documents", params=params)

    assert response.status_code == 422


def test_get_document_returns_metadata(client: TestClient, documents: list[DocumentRead]) -> None:
    target = documents[0]

    response = client.get(f"/api/v1/documents/{target.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(target.id)
    assert body["status"] == "completed"
    # La API no debe exponer ubicaciones internas de almacenamiento.
    assert "storage_key" not in body


def test_get_document_not_found(client: TestClient) -> None:
    response = client.get(f"/api/v1/documents/{UUID(int=0)}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found"}


def test_get_document_rejects_invalid_id(client: TestClient) -> None:
    response = client.get("/api/v1/documents/not-a-uuid")

    assert response.status_code == 422
