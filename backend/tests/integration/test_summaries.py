"""Resúmenes de documentos: generación al subir y uso en preguntas de resumen."""

from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.main import app
from app.repositories.documents import DocumentRepository
from app.services import ingestion
from app.services.embeddings import FakeEmbeddingProvider
from app.services.llm import FakeLLMProvider, LLMError, get_optional_llm_provider
from app.services.storage import LocalFileStorage
from tests.integration.test_search import EXPENSES, SECURITY, VACATIONS
from tests.pdf_factory import make_pdf

HANDBOOK = make_pdf([VACATIONS, EXPENSES, SECURITY])


class DownSummaryLLM(FakeLLMProvider):
    def generate_summary(self, filename: str, chunks: list) -> None:  # type: ignore[override]
        raise LLMError("El proveedor de LLM no tiene saldo.")


def upload(client: TestClient, data: bytes = HANDBOOK, filename: str = "manual.pdf") -> dict:
    response = client.post("/api/v1/documents", files={"file": (filename, data, "application/pdf")})
    assert response.status_code == 201, response.text
    return response.json()


def ask(client: TestClient, question: str) -> dict:
    response = client.post("/api/v1/query", json={"question": question})
    assert response.status_code == 200, response.text
    return response.json()


def test_upload_generates_and_returns_a_summary(client: TestClient, llm: FakeLLMProvider) -> None:
    body = upload(client)

    assert body["status"] == "completed"
    assert body["summary"].startswith("Resumen simulado de manual.pdf")
    [(filename, context)] = llm.summary_calls
    assert filename == "manual.pdf"
    assert {c.page_number for c in context} == {1, 2, 3}  # el documento corto va entero


def test_summary_failure_does_not_fail_the_document(client: TestClient) -> None:
    app.dependency_overrides[get_optional_llm_provider] = lambda: DownSummaryLLM()

    body = upload(client)

    assert body["status"] == "completed"
    assert body["summary"] is None


def test_without_llm_configured_documents_are_processed_without_summary(
    client: TestClient,
) -> None:
    app.dependency_overrides[get_optional_llm_provider] = lambda: None

    body = upload(client)

    assert body["status"] == "completed"
    assert body["summary"] is None


def test_reprocess_keeps_previous_summary_if_the_new_one_fails(
    db_session: Session, settings: Settings, embedder: FakeEmbeddingProvider
) -> None:
    storage = LocalFileStorage(settings.storage_dir)
    document = ingestion.register_upload(db_session, storage, settings, "manual.pdf", HANDBOOK)
    ingestion.process_document(
        db_session, storage, embedder, FakeLLMProvider(), settings, document.id
    )
    previous = document.summary

    result = ingestion.process_document(
        db_session, storage, embedder, DownSummaryLLM(), settings, document.id
    )

    assert result.status == "completed"
    assert previous is not None
    assert result.summary == previous


def test_summary_question_answers_from_summaries(client: TestClient, llm: FakeLLMProvider) -> None:
    document_id = upload(client)["id"]

    body = ask(client, "¿De qué trata?")

    assert body["insufficient_evidence"] is False
    [source] = body["sources"]
    assert source["source_type"] == "summary"
    assert source["document_id"] == document_id
    assert source["chunk_id"] is None
    assert source["page_number"] is None
    assert source["score"] is None
    [(_, context)] = llm.calls
    assert context[0].text.startswith("Resumen simulado de manual.pdf")


def test_summary_question_without_summaries_falls_back_to_search(client: TestClient) -> None:
    app.dependency_overrides[get_optional_llm_provider] = lambda: None
    upload(client)

    body = ask(client, "resumen de la política de vacaciones")

    assert body["insufficient_evidence"] is False
    assert body["sources"][0]["source_type"] == "chunk"


def test_summaries_of_failed_documents_are_not_used(
    client: TestClient, db_session: Session
) -> None:
    document_id = UUID(upload(client)["id"])
    document = DocumentRepository(db_session).get(document_id)
    assert document is not None
    document.status = "failed"
    db_session.commit()

    assert DocumentRepository(db_session).list_summaries(limit=10) == []


def test_regular_questions_still_use_chunks(client: TestClient) -> None:
    upload(client)

    body = ask(client, "¿cuántos días de vacaciones tengo?")

    assert body["sources"][0]["source_type"] == "chunk"
    assert body["sources"][0]["chunk_id"]
