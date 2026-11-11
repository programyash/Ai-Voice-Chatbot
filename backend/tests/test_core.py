from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.db import connection, init_db
from backend.app.knowledge import ingest, retrieve, seed
from backend.app import tools
from backend.app.main import app
from backend.app.agent import service


@pytest.fixture(autouse=True)
def isolated_database(tmp_path: Path):
    previous_path = settings.database_path
    previous_export = settings.allow_knowledge_export
    previous_admin = settings.admin_token
    object.__setattr__(settings, "database_path", tmp_path / "test.db")
    object.__setattr__(settings, "allow_knowledge_export", False)
    object.__setattr__(settings, "admin_token", "test-admin-token")
    init_db()
    seed()
    yield
    object.__setattr__(settings, "database_path", previous_path)
    object.__setattr__(settings, "allow_knowledge_export", previous_export)
    object.__setattr__(settings, "admin_token", previous_admin)


def test_seeded_facts_and_retrieval():
    with connection() as db:
        rows = db.execute("SELECT body, page FROM chunks").fetchall()
    assert len(rows) == 7
    assert not any("raw leave and attendance" in row["body"] for row in rows)
    assert retrieve("minimum villa plot size")[0]["section"] == "Project A overview"
    assert any("proposed Haryana" in x["text"] for x in retrieve("Haryana Orbital Rail Corridor"))


def test_additional_markdown_ingestion(tmp_path: Path):
    source = tmp_path / "update.md"
    source.write_text("# New facilities\nA new documented facility can be added without code changes.", encoding="utf-8")
    result = ingest(source)
    assert result["chunks"] == 1
    assert any(x["source"] == "update.md" for x in retrieve("documented facility"))


def test_structured_tools():
    assert tools.get_project_details("a")["plot_size_sq_yd"] == [267, 597]
    assert tools.get_project_details("B")["business_plots_approx"] == 85
    assert tools.get_connectivity_information("IGI")["distances_km_approx"]["IGI Airport"] == 45
    assert tools.get_connectivity_information("Mars")["error"]
    assert tools.convert_plot_area(1, "sq yd", "sq ft")["result"] == 9
    assert tools.convert_plot_area(1, "sq yd", "sq m")["result"] == 0.8361
    assert tools.calculate_property_values(267, 25000)["illustrative_total_inr"] == 6675000
    assert "not specified" in tools.compare_projects()["note"]


def test_consent_and_request_status():
    with pytest.raises(ValueError):
        tools.Lead(name="Ada", mobile="9876543210", consent=False)
    lead = tools.capture_customer_lead(tools.Lead(name="Ada Lovelace", mobile="9876543210", consent=True))
    assert lead["status"] == "inquiry received"
    duplicate = tools.capture_customer_lead(tools.Lead(name="Ada Lovelace", mobile="9876543210", consent=True))
    assert duplicate["status"] == "already received"
    visit = tools.create_site_visit_request(tools.Visit(name="Ada Lovelace", mobile="9876543210", preferred_date=date.today() + timedelta(days=2), consent=True))
    assert visit["status"] == "pending confirmation"
    callback = tools.request_human_callback(tools.Callback(name="Ada Lovelace", email="ada@example.com", consent=True))
    assert callback["status"] == "pending"


def test_api_health_and_safe_cloud_gate():
    with TestClient(app) as client:
        health = client.get("/api/health").json()
        assert health["knowledge_chunks"] == 7
        assert health["knowledge_export_enabled"] is False
        assert client.get("/api/projects").status_code == 200
        local_chat = client.post("/api/chat", json={"message": "Tell me about Project A"})
        assert local_chat.status_code == 200 and local_chat.json()["mode"] == "local_reference"
        assert "villa plots" in local_chat.json()["answer"].lower()
        assert "assignment" not in local_chat.json()["answer"].lower()
        unknown = client.post("/api/chat", json={"message": "What is the current availability of 300 sq yd plots?"})
        assert "current availability" in unknown.json()["answer"].lower()
        assert client.post("/api/chat", json={"message": "   "}).status_code == 422
        assert client.get("/api/admin/leads").status_code == 403
        assert client.post("/api/leads", json={"name": "Ada", "mobile": "9876543210", "consent": False}).status_code == 422
        lead = client.post("/api/leads", json={"name": "Test Customer", "mobile": "9876543210", "consent": True})
        assert lead.status_code == 200 and lead.json()["status"] == "inquiry received"
        admin = client.get("/api/admin/leads", headers={"X-Admin-Token": "test-admin-token"})
        assert admin.status_code == 200 and len(admin.json()["leads"]) == 1
        visit = client.post("/api/visits", json={"name": "Test Customer", "mobile": "9876543210", "preferred_date": (date.today() + timedelta(days=2)).isoformat(), "consent": True})
        assert visit.status_code == 200 and visit.json()["status"] == "pending confirmation"
        callback = client.post("/api/callbacks", json={"name": "Test Customer", "email": "test@example.com", "consent": True})
        assert callback.status_code == 200 and callback.json()["status"] == "pending"
        with client.websocket_connect("/ws/live") as ws:
            assert ws.receive_json()["type"] == "error"


def test_agent_reuses_conversation_history_without_network(monkeypatch):
    calls = []

    class FakeChats:
        def create(self, model, history, config):
            calls.append(history)
            return SimpleNamespace(send_message=lambda message: SimpleNamespace(text="Documented answer"))

    monkeypatch.setattr(service.genai, "Client", lambda **kwargs: SimpleNamespace(chats=FakeChats()))
    monkeypatch.setattr(service, "retrieve", lambda *args, **kwargs: [{"source": "assignment", "page": 1, "section": "Project A", "text": "Villa plots are 267 to 597 sq yd."}])
    object.__setattr__(settings, "allow_knowledge_export", True)
    conversation_id = service.create_conversation()
    service.chat(conversation_id, "Tell me about villa plots")
    service.chat(conversation_id, "What is its minimum size?")
    assert len(calls) == 2
    assert [item.role for item in calls[1]] == ["user", "model"]
    assert service.history(conversation_id)[-1]["body"] == "Documented answer"


def test_customer_answer_removes_internal_references():
    raw = "INR 80,000 [Assignment - AI Voice Bot Development.pdf, page 2]. These are assignment-provided indications rather than verified live quotations."
    answer = service.customer_answer(raw)
    assert "pdf" not in answer.lower() and "assignment" not in answer.lower()
    assert "INR 80,000" in answer and "verified live quotations" in answer

