from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.document import Document
from app.repositories.documents import DocumentRepository


def create_document(repository: DocumentRepository, name: str = "manual.pdf") -> Document:
    return repository.create(
        original_filename=name,
        storage_key=f"{uuid4()}.pdf",
        content_type="application/pdf",
        size_bytes=1234,
        checksum_sha256="a" * 64,
    )


def test_create_sets_defaults(db_session: Session) -> None:
    document = create_document(DocumentRepository(db_session))

    assert document.id is not None
    assert document.status == "pending"
    assert document.created_at is not None
    assert document.processed_at is None


def test_created_document_is_visible_from_a_new_session(
    engine: Engine, db_session: Session
) -> None:
    created = create_document(DocumentRepository(db_session))

    # Una sesión nueva equivale a otra petición (o a un backend reiniciado):
    # solo ve lo que realmente se confirmó en PostgreSQL.
    with Session(engine) as other_session:
        found = DocumentRepository(other_session).get(created.id)

    assert found is not None
    assert found.original_filename == "manual.pdf"


def test_list_orders_newest_first_and_counts_total(db_session: Session) -> None:
    repository = DocumentRepository(db_session)
    for name in ["a.pdf", "b.pdf", "c.pdf"]:
        create_document(repository, name)

    documents, total = repository.list(limit=2, offset=0)

    assert total == 3
    assert [d.original_filename for d in documents] == ["c.pdf", "b.pdf"]


def test_get_unknown_id_returns_none(db_session: Session) -> None:
    assert DocumentRepository(db_session).get(uuid4()) is None


def test_database_rejects_invalid_status(db_session: Session) -> None:
    document = create_document(DocumentRepository(db_session))
    document.status = "banana"

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_api_reads_documents_from_database(client: TestClient, db_session: Session) -> None:
    created = create_document(DocumentRepository(db_session))

    list_response = client.get("/api/v1/documents")
    detail_response = client.get(f"/api/v1/documents/{created.id}")

    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == str(created.id)
    assert "storage_key" not in detail_response.json()
