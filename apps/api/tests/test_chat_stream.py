"""C5 — SSE streaming of tool events."""

from __future__ import annotations

import json
import os

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv()

from app.main import app

client = TestClient(app)

_has_groq = bool(os.getenv("GROQ_API_KEY"))
needs_groq = pytest.mark.skipif(not _has_groq, reason="Requires GROQ_API_KEY")


def _parse_sse(raw: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name = "message"
    data_lines: list[str] = []
    for line in raw.splitlines():
        if line.startswith("event:"):
            event_name = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].strip())
        elif line.strip() == "":
            if data_lines:
                payload = json.loads("\n".join(data_lines))
                events.append((event_name, payload))
            event_name = "message"
            data_lines = []
    if data_lines:
        events.append((event_name, json.loads("\n".join(data_lines))))
    return events


def test_chat_stream_requires_auth() -> None:
    response = client.post("/chat/stream", json={"message": "hello"})
    assert response.status_code == 401


@needs_groq
def test_chat_stream_emits_tool_events() -> None:
    login = client.post("/auth/login", json={"persona_id": "northstar"})
    token = login.json()["access_token"]
    with client.stream(
        "POST",
        "/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "Can I cancel ORD-1001 without a fee?"},
    ) as response:
        assert response.status_code == 200, response.text
        body = "".join(response.iter_text())

    events = _parse_sse(body)
    names = [name for name, _ in events]
    assert "start" in names
    assert "tool_start" in names
    assert "tool_end" in names
    assert "final" in names or "awaiting_confirmation" in names

    tools = [
        payload["tool"]
        for name, payload in events
        if name == "tool_start" and payload.get("tool")
    ]
    assert tools, events
    assert any(
        t in {"structured_data_query", "document_search", "list_documents"} for t in tools
    ), tools

    finals = [p for n, p in events if n == "final"]
    if finals:
        assert finals[0]["answer"]
        assert finals[0]["thread_id"]
