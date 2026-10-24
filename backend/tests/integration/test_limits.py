"""Límites de frecuencia, presupuesto diario y cuotas de almacenamiento."""

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.main import app
from app.repositories.usage import UsageRepository
from tests.integration.test_search import VACATIONS
from tests.pdf_factory import make_pdf


def use_settings(settings: Settings, **changes: object) -> Settings:
    changed = settings.model_copy(update=changes)
    app.dependency_overrides[get_settings] = lambda: changed
    return changed


def upload(client: TestClient, name: str = "manual.pdf") -> int:
    response = client.post(
        "/api/v1/documents", files={"file": (name, make_pdf([VACATIONS]), "application/pdf")}
    )
    return response.status_code


def ask(client: TestClient) -> object:
    return client.post("/api/v1/query", json={"question": "¿días de vacaciones?"})


def test_too_many_questions_get_429_with_retry_after(
    client: TestClient, settings: Settings
) -> None:
    use_settings(settings, rate_limit_queries_per_minute=3)

    statuses = [ask(client).status_code for _ in range(3)]
    blocked = ask(client)
    search = client.post("/api/v1/search", json={"query": "vacaciones"})

    assert statuses == [200, 200, 200]
    assert blocked.status_code == 429
    assert 1 <= int(blocked.headers["Retry-After"]) <= 60
    assert "Demasiadas preguntas" in blocked.json()["detail"]
    assert search.status_code == 429  # /search comparte el límite


def test_too_many_uploads_get_429(client: TestClient, settings: Settings) -> None:
    use_settings(settings, rate_limit_uploads_per_hour=2)

    assert [upload(client, f"{i}.pdf") for i in range(3)] == [201, 201, 429]


def test_zero_disables_rate_limits(client: TestClient, settings: Settings) -> None:
    use_settings(settings, rate_limit_queries_per_minute=0)

    assert all(ask(client).status_code == 200 for _ in range(30))


def test_spending_is_recorded(client: TestClient, db_session: Session) -> None:
    upload(client)
    ask(client)
    ask(client)

    usage = client.get("/api/v1/usage").json()

    assert usage["queries_today"] == 2
    assert usage["documents_processed_today"] == 1
    # Los proveedores falsos no gastan tokens del LLM; queda el embedding estimado (> 0).
    assert 0 < usage["cost_usd"] < 0.001
    assert usage["documents"] == 1
    assert usage["storage_bytes"] > 0


def test_daily_budget_blocks_questions_and_uploads(
    client: TestClient, settings: Settings, db_session: Session
) -> None:
    use_settings(settings, daily_budget_usd=0.5)
    UsageRepository(db_session).add(0.5)
    db_session.commit()

    blocked = ask(client)

    assert blocked.status_code == 429
    assert "límite de gasto diario" in blocked.json()["detail"]
    assert int(blocked.headers["Retry-After"]) <= 24 * 3600
    assert upload(client) == 429
    usage = client.get("/api/v1/usage").json()
    assert usage["cost_usd"] == 0.5
    assert usage["daily_budget_usd"] == 0.5


def test_document_quota_counts_the_trash(client: TestClient, settings: Settings) -> None:
    use_settings(settings, max_documents=1)
    assert upload(client) == 201
    document_id = client.get("/api/v1/documents").json()["items"][0]["id"]
    client.delete(f"/api/v1/documents/{document_id}")  # a la papelera: sigue ocupando

    response = client.post(
        "/api/v1/documents", files={"file": ("b.pdf", make_pdf([VACATIONS]), "application/pdf")}
    )

    assert response.status_code == 403
    assert "vacía la papelera" in response.json()["detail"]
    client.delete("/api/v1/trash")
    assert upload(client, "c.pdf") == 201


def test_storage_quota(client: TestClient, settings: Settings, db_session: Session) -> None:
    use_settings(settings, max_storage_mb=1)
    # Simula 1 MB ya ocupado subiendo y luego inflando el tamaño registrado.
    upload(client)
    db_session.execute(text("UPDATE documents SET size_bytes = 1048576"))
    db_session.commit()

    assert upload(client, "otro.pdf") == 403


def test_usage_cost_uses_decimal_precision(db_session: Session) -> None:
    repository = UsageRepository(db_session)
    for _ in range(1000):
        repository.add(0.000001)
    db_session.commit()

    assert repository.today().cost_usd == Decimal("0.001000")
