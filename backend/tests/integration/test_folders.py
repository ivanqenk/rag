"""Carpetas: CRUD, documentos dentro de carpetas y preguntas limitadas a una carpeta."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.llm import FakeLLMProvider
from tests.integration.test_search import EXPENSES, VACATIONS
from tests.pdf_factory import make_pdf

UNKNOWN = "00000000-0000-0000-0000-000000000000"


def create_folder(client: TestClient, name: str) -> dict:
    response = client.post("/api/v1/folders", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def upload(client: TestClient, text: str, filename: str, folder_id: str | None = None) -> dict:
    data = {"folder_id": folder_id} if folder_id else {}
    response = client.post(
        "/api/v1/documents",
        files={"file": (filename, make_pdf([text]), "application/pdf")},
        data=data,
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- CRUD de carpetas --------------------------------------------------------------------


def test_create_list_and_count_documents(client: TestClient) -> None:
    contracts = create_folder(client, "  Contratos  ")
    create_folder(client, "anexos")
    upload(client, VACATIONS, "a.pdf", contracts["id"])

    folders = client.get("/api/v1/folders").json()

    assert contracts["name"] == "Contratos"  # sin espacios sobrantes
    assert [(f["name"], f["document_count"]) for f in folders] == [
        ("anexos", 0),
        ("Contratos", 1),
    ]


def test_folder_names_are_unique_ignoring_case(client: TestClient) -> None:
    create_folder(client, "Contratos")
    other = create_folder(client, "Facturas")

    duplicate = client.post("/api/v1/folders", json={"name": "CONTRATOS"})
    rename_to_duplicate = client.patch(f"/api/v1/folders/{other['id']}", json={"name": "contratos"})

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Ya existe una carpeta con ese nombre."
    assert rename_to_duplicate.status_code == 409


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
def test_invalid_names_are_rejected(client: TestClient, name: str) -> None:
    assert client.post("/api/v1/folders", json={"name": name}).status_code == 422


def test_rename_folder(client: TestClient) -> None:
    folder = create_folder(client, "Contratos")
    upload(client, VACATIONS, "a.pdf", folder["id"])

    response = client.patch(f"/api/v1/folders/{folder['id']}", json={"name": "Contratos 2026"})

    assert response.status_code == 200
    assert response.json()["name"] == "Contratos 2026"
    assert response.json()["document_count"] == 1


def test_deleting_a_folder_keeps_its_documents(client: TestClient) -> None:
    folder = create_folder(client, "Contratos")
    document = upload(client, VACATIONS, "a.pdf", folder["id"])

    assert client.delete(f"/api/v1/folders/{folder['id']}").status_code == 204

    assert client.get("/api/v1/folders").json() == []
    kept = client.get(f"/api/v1/documents/{document['id']}").json()
    assert kept["folder_id"] is None


def test_unknown_folder_returns_404(client: TestClient) -> None:
    assert client.patch(f"/api/v1/folders/{UNKNOWN}", json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/v1/folders/{UNKNOWN}").status_code == 404


# --- Documentos en carpetas --------------------------------------------------------------


def test_upload_into_folder_and_filter_list(client: TestClient) -> None:
    folder = create_folder(client, "Contratos")
    inside = upload(client, VACATIONS, "dentro.pdf", folder["id"])
    upload(client, EXPENSES, "fuera.pdf")

    body = client.get("/api/v1/documents", params={"folder_id": folder["id"]}).json()

    assert inside["folder_id"] == folder["id"]
    assert body["total"] == 1
    assert [d["original_filename"] for d in body["items"]] == ["dentro.pdf"]


def test_upload_into_unknown_folder_stores_nothing(client: TestClient, storage_dir: Path) -> None:
    response = client.post(
        "/api/v1/documents",
        files={"file": ("a.pdf", make_pdf([VACATIONS]), "application/pdf")},
        data={"folder_id": UNKNOWN},
    )

    assert response.status_code == 404
    assert client.get("/api/v1/documents").json()["total"] == 0
    assert not storage_dir.exists() or list(storage_dir.iterdir()) == []


def test_move_document_between_folders(client: TestClient) -> None:
    folder = create_folder(client, "Contratos")
    document = upload(client, VACATIONS, "a.pdf")
    url = f"/api/v1/documents/{document['id']}"

    moved = client.patch(url, json={"folder_id": folder["id"]})
    taken_out = client.patch(url, json={"folder_id": None})
    to_unknown = client.patch(url, json={"folder_id": UNKNOWN})

    assert moved.json()["folder_id"] == folder["id"]
    assert taken_out.json()["folder_id"] is None
    assert to_unknown.status_code == 404


# --- Preguntas por carpeta ---------------------------------------------------------------


def test_question_limited_to_a_folder(client: TestClient, llm: FakeLLMProvider) -> None:
    hr = create_folder(client, "RR. HH.")
    finance = create_folder(client, "Finanzas")
    upload(client, VACATIONS, "vacaciones.pdf", hr["id"])
    upload(client, VACATIONS + " Copia de finanzas.", "copia.pdf", finance["id"])

    response = client.post(
        "/api/v1/query",
        json={"question": "¿cuántos días de vacaciones tengo?", "folder_id": hr["id"]},
    )

    assert response.status_code == 200
    assert {s["filename"] for s in response.json()["sources"]} == {"vacaciones.pdf"}
    [(_, context)] = llm.calls
    assert {chunk.filename for chunk in context} == {"vacaciones.pdf"}


def test_summary_question_limited_to_a_folder(client: TestClient, llm: FakeLLMProvider) -> None:
    folder = create_folder(client, "RR. HH.")
    upload(client, VACATIONS, "vacaciones.pdf", folder["id"])
    upload(client, EXPENSES, "gastos.pdf")

    client.post("/api/v1/query", json={"question": "¿De qué trata?", "folder_id": folder["id"]})

    [(_, context)] = llm.calls
    assert [chunk.filename for chunk in context] == ["vacaciones.pdf"]


@pytest.mark.parametrize("path", ["/api/v1/query", "/api/v1/search"])
def test_folder_scope_is_validated(client: TestClient, path: str) -> None:
    key = "question" if path.endswith("query") else "query"
    document = upload(client, VACATIONS, "a.pdf")
    folder = create_folder(client, "Contratos")

    both = client.post(
        path, json={key: "vacaciones", "folder_id": folder["id"], "document_id": document["id"]}
    )
    unknown = client.post(path, json={key: "vacaciones", "folder_id": UNKNOWN})

    assert both.status_code == 422
    assert unknown.status_code == 404
