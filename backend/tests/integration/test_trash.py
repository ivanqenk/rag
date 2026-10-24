"""Papelera: eliminar es reversible durante TRASH_RETENTION_DAYS días."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.documents import DocumentRepository
from app.services import trash
from app.services.llm import FakeLLMProvider
from app.services.storage import LocalFileStorage
from tests.integration.test_search import VACATIONS
from tests.pdf_factory import make_pdf


def upload(client: TestClient, filename: str = "manual.pdf", data: dict | None = None) -> str:
    response = client.post(
        "/api/v1/documents",
        files={"file": (filename, make_pdf([VACATIONS]), "application/pdf")},
        data=data or {},
    )
    assert response.status_code == 201
    return response.json()["id"]


def stored_files(storage_dir: Path) -> list[Path]:
    return list(storage_dir.iterdir()) if storage_dir.exists() else []


def test_deleted_document_goes_to_trash_and_disappears_everywhere(
    client: TestClient, llm: FakeLLMProvider, storage_dir: Path
) -> None:
    document_id = upload(client)

    assert client.delete(f"/api/v1/documents/{document_id}").status_code == 204

    assert client.get("/api/v1/documents").json()["total"] == 0
    search = client.post("/api/v1/search", json={"query": "días de vacaciones"}).json()
    assert search["results"] == []
    answer = client.post("/api/v1/query", json={"question": "¿días de vacaciones?"}).json()
    assert answer["insufficient_evidence"] is True
    assert llm.calls == []
    # Sigue existiendo: se puede ver (marcado como eliminado) y su archivo se conserva.
    detail = client.get(f"/api/v1/documents/{document_id}").json()
    assert detail["deleted_at"] is not None
    assert stored_files(storage_dir)

    trash_page = client.get("/api/v1/trash").json()
    assert [d["id"] for d in trash_page["items"]] == [document_id]
    assert trash_page["retention_days"] == 30


def test_restore_brings_it_back_without_reprocessing(
    client: TestClient, llm: FakeLLMProvider
) -> None:
    document_id = upload(client)
    client.delete(f"/api/v1/documents/{document_id}")
    summaries_before = len(llm.summary_calls)

    response = client.post(f"/api/v1/trash/{document_id}/restore")

    assert response.status_code == 200
    assert response.json()["deleted_at"] is None
    assert client.get("/api/v1/trash").json()["total"] == 0
    assert client.get("/api/v1/documents").json()["total"] == 1
    search = client.post("/api/v1/search", json={"query": "días de vacaciones"}).json()
    assert search["results"]
    assert len(llm.summary_calls) == summaries_before  # sin volver a procesar


def test_trashed_documents_cannot_be_modified_or_queried(client: TestClient) -> None:
    document_id = upload(client)
    client.delete(f"/api/v1/documents/{document_id}")

    reprocess = client.post(f"/api/v1/documents/{document_id}/reprocess")
    move = client.patch(f"/api/v1/documents/{document_id}", json={"folder_id": None})
    scoped = client.post("/api/v1/query", json={"question": "x", "document_id": document_id})

    assert reprocess.status_code == 409
    assert "papelera" in reprocess.json()["detail"]
    assert move.status_code == 409
    assert scoped.status_code == 404


def test_only_trashed_documents_can_be_restored_or_purged(client: TestClient) -> None:
    document_id = upload(client)

    assert client.post(f"/api/v1/trash/{document_id}/restore").status_code == 404
    assert client.delete(f"/api/v1/trash/{document_id}").status_code == 404
    assert client.get(f"/api/v1/documents/{document_id}").status_code == 200


def test_trashed_documents_do_not_count_in_folders(client: TestClient) -> None:
    folder = client.post("/api/v1/folders", json={"name": "Contratos"}).json()
    document_id = upload(client, data={"folder_id": folder["id"]})

    client.delete(f"/api/v1/documents/{document_id}")

    assert client.get("/api/v1/folders").json()[0]["document_count"] == 0
    listed = client.get("/api/v1/documents", params={"folder_id": folder["id"]}).json()
    assert listed["total"] == 0


def test_empty_trash_deletes_everything_in_it(client: TestClient, storage_dir: Path) -> None:
    trashed = [upload(client, "a.pdf"), upload(client, "b.pdf")]
    kept = upload(client, "c.pdf")
    for document_id in trashed:
        client.delete(f"/api/v1/documents/{document_id}")

    assert client.delete("/api/v1/trash").status_code == 204

    assert client.get("/api/v1/trash").json()["total"] == 0
    assert [d["id"] for d in client.get("/api/v1/documents").json()["items"]] == [kept]
    assert len(stored_files(storage_dir)) == 1


def test_purge_deletes_only_documents_older_than_retention(
    client: TestClient, db_session: Session, settings: Settings, storage_dir: Path
) -> None:
    old_id, recent_id = upload(client, "viejo.pdf"), upload(client, "reciente.pdf")
    repository = DocumentRepository(db_session)
    now = datetime.now(UTC)
    for document_id, age in ((old_id, 31), (recent_id, 29)):
        document = repository.get(UUID(document_id))
        assert document is not None
        repository.set_deleted_at(document, now - timedelta(days=age))

    purged = trash.purge_expired(db_session, LocalFileStorage(storage_dir), settings, now=now)

    assert purged == 1
    assert client.get(f"/api/v1/documents/{old_id}").status_code == 404
    assert [d["id"] for d in client.get("/api/v1/trash").json()["items"]] == [recent_id]
    assert len(stored_files(storage_dir)) == 1
