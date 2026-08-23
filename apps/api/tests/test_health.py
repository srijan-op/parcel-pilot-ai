"""Smoke tests for API scaffold."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["llm_provider"] == "groq"
    assert body["embedding_provider"] == "gemini"
    assert "snapshot_at" in body
    assert "2026-08-16" in body["snapshot_at"]


def test_root() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["message"] == "ParcelPilot Assist API"
