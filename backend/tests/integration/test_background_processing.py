"""PROCESSING_MODE=background: la subida responde enseguida y el documento se procesa después."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.main import app
from app.repositories.documents import DocumentRepository
from app.services import ingestion, processing
from app.services.storage import LocalFileStorage
from tests.integration.test_search import VACATIONS
from tests.pdf_factory import make_pdf


@pytest.fixture
def background(settings: Settings) -> Settings:
    background = settings.model_copy(update={"processing_mode": "background"})
    app.dependency_overrides[get_settings] = lambda: background
    return background


def upload(client: TestClient) -> tuple[int, dict]:
    response = client.post(
        "/api/v1/documents",
        files={"file": ("manual.pdf", make_pdf([VACATIONS]), "application/pdf")},
    )
    return response.status_code, response.json()


def test_upload_responds_202_and_processes_afterwards(
    client: TestClient, background: Settings
) -> None:
    status_code, body = upload(client)

    assert status_code == 202
    assert body["status"] == "pending"
    # TestClient ejecuta las tareas en segundo plano antes de devolver la respuesta, así que
    # el documento ya está procesado al consultarlo.
    document = client.get(f"/api/v1/documents/{body['id']}").json()
    assert document["status"] == "completed"
    assert document["summary"]


def test_invalid_files_are_still_rejected_immediately(
    client: TestClient, background: Settings
) -> None:
    response = client.post(
        "/api/v1/documents", files={"file": ("a.pdf", b"no soy un pdf", "application/pdf")}
    )

    assert response.status_code == 415


def test_reprocess_responds_202_and_marks_pending(client: TestClient, background: Settings) -> None:
    _, body = upload(client)

    response = client.post(f"/api/v1/documents/{body['id']}/reprocess")

    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    assert client.get(f"/api/v1/documents/{body['id']}").json()["status"] == "completed"


def test_unfinished_documents_are_resumed_at_startup(
    engine: Engine, db_session: Session, settings: Settings, storage_dir: Path
) -> None:
    # Registrado pero sin procesar, como si el servidor se hubiera reiniciado a mitad.
    storage = LocalFileStorage(storage_dir)
    document = ingestion.register_upload(
        db_session, storage, settings, "manual.pdf", make_pdf([VACATIONS])
    )
    trashed = ingestion.register_upload(
        db_session, storage, settings, "papelera.pdf", make_pdf([VACATIONS])
    )
    DocumentRepository(db_session).set_deleted_at(trashed, trashed.created_at)

    resumed = processing.resume_unfinished(
        sessionmaker(bind=engine, expire_on_commit=False), settings
    )

    assert resumed == 1  # el de la papelera no se retoma
    db_session.expire_all()
    assert DocumentRepository(db_session).get(document.id).status == "completed"
