"""C3 — chat HITL interrupt / resume."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv()

from app.agent.graph import _pack_response, _serialize_interrupt, resume_agent_turn
from app.auth.models import AuthUser
from app.main import app

client = TestClient(app)

_has_groq = bool(os.getenv("GROQ_API_KEY"))
_db_url = os.getenv("DATABASE_URL", "")
needs_groq = pytest.mark.skipif(not _has_groq, reason="Requires GROQ_API_KEY")
needs_db = pytest.mark.skipif(
    not _db_url or "localhost" in _db_url or "user:password" in _db_url,
    reason="Requires configured DATABASE_URL",
)


def test_serialize_interrupt_tuple() -> None:
    raw = (SimpleNamespace(value={"type": "confirm_action", "pending_id": "p-1"}),)
    assert _serialize_interrupt(raw) == {"type": "confirm_action", "pending_id": "p-1"}


def test_pack_awaiting_confirmation() -> None:
    user = AuthUser(
        user_id="maya",
        name="Maya",
        role="support_agent",
        account_id=None,
        persona_id="maya",
    )
    packed = _pack_response(
        thread_id="t-1",
        user=user,
        messages=[],
        interrupt_payload={
            "type": "confirm_action",
            "draft": {"ticket_id": "TKT-501", "severity": "P1"},
            "message": "Please confirm escalation.",
        },
    )
    assert packed["status"] == "awaiting_confirmation"
    assert packed["awaiting_confirmation"] is True
    assert packed["draft"]["ticket_id"] == "TKT-501"
    assert "awaiting_hitl" in packed["trust"]["flags"]


def test_chat_resume_requires_auth() -> None:
    response = client.post(
        "/chat/resume",
        json={"thread_id": "missing", "decision": "confirm"},
    )
    assert response.status_code == 401


def test_resume_without_interrupt_raises() -> None:
    user = AuthUser(
        user_id="maya",
        name="Maya",
        role="support_agent",
        account_id=None,
        persona_id="maya",
    )
    db = MagicMock()
    with pytest.raises(ValueError, match="not awaiting confirmation"):
        resume_agent_turn(
            user=user,
            db=db,
            thread_id="no-such-thread-xyz",
            decision="cancel",
        )


@needs_groq
@needs_db
def test_chat_hitl_escalate_confirm_smoke() -> None:
    """Maya asks to escalate TKT-501 → pause → confirm → completed."""
    from sqlalchemy import func, select

    from app.db.models import Escalation
    from app.db.session import get_session_factory

    login = client.post("/auth/login", json={"persona_id": "maya"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    before = get_session_factory()()
    count_before = before.scalar(select(func.count()).select_from(Escalation)) or 0
    before.close()

    paused = client.post(
        "/chat",
        headers=headers,
        json={
            "message": (
                "Please escalate ticket TKT-501 now. Severity P1. "
                "Reason: SLA breached and production impact. "
                "Recommended next step: page on-call and notify CSM. "
                "Use the create_escalation tool."
            )
        },
    )
    assert paused.status_code == 200, paused.text
    body = paused.json()
    assert body["status"] == "awaiting_confirmation", body
    assert body["awaiting_confirmation"] is True
    assert body["draft"]["ticket_id"] == "TKT-501"
    thread_id = body["thread_id"]

    mid = get_session_factory()()
    count_mid = mid.scalar(select(func.count()).select_from(Escalation)) or 0
    mid.close()
    assert count_mid == count_before  # no row until confirm

    resumed = client.post(
        "/chat/resume",
        headers=headers,
        json={"thread_id": thread_id, "decision": "confirm"},
    )
    assert resumed.status_code == 200, resumed.text
    done = resumed.json()
    assert done["status"] == "completed", done
    assert done["awaiting_confirmation"] is False
    tool_names = {t["tool"] for t in done["tools_used"]}
    assert "create_escalation" in tool_names

    after = get_session_factory()()
    count_after = after.scalar(select(func.count()).select_from(Escalation)) or 0
    after.close()
    assert count_after == count_before + 1


@needs_groq
@needs_db
def test_chat_hitl_update_ticket_confirm_smoke() -> None:
    """Maya updates TKT-504 notes → pause → confirm → ticket notes appended."""
    from app.db.models import Ticket
    from app.db.session import get_session_factory

    login = client.post("/auth/login", json={"persona_id": "maya"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    marker = "C4-HITL-NOTE-UPDATE"

    paused = client.post(
        "/chat",
        headers=headers,
        json={
            "message": (
                "Use the update_ticket tool now for TKT-504. "
                f"Append notes exactly: {marker}. "
                "Do not change status or assignee."
            )
        },
    )
    assert paused.status_code == 200, paused.text
    body = paused.json()
    assert body["status"] == "awaiting_confirmation", body
    assert body["interrupt"]["action_type"] == "update_ticket"
    assert body["draft"]["ticket_id"] == "TKT-504"
    thread_id = body["thread_id"]

    mid = get_session_factory()()
    ticket_mid = mid.get(Ticket, "TKT-504")
    hist_mid = ticket_mid.historical_resolution or ""
    mid.close()
    assert marker not in hist_mid

    resumed = client.post(
        "/chat/resume",
        headers=headers,
        json={"thread_id": thread_id, "decision": "confirm"},
    )
    assert resumed.status_code == 200, resumed.text
    done = resumed.json()
    assert done["status"] == "completed", done
    assert "update_ticket" in {t["tool"] for t in done["tools_used"]}

    after = get_session_factory()()
    ticket = after.get(Ticket, "TKT-504")
    hist = ticket.historical_resolution or ""
    after.close()
    assert marker in hist


@needs_groq
@needs_db
def test_chat_hitl_follow_up_cancel_smoke() -> None:
    """Maya proposes follow-up → pause → cancel → no task row."""
    from sqlalchemy import func, select

    from app.db.models import FollowUpTask
    from app.db.session import get_session_factory

    login = client.post("/auth/login", json={"persona_id": "maya"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    before = get_session_factory()()
    count_before = before.scalar(select(func.count()).select_from(FollowUpTask)) or 0
    before.close()

    paused = client.post(
        "/chat",
        headers=headers,
        json={
            "message": (
                "Use create_follow_up_task now. "
                "Title: C4 follow-up smoke. "
                "Details: call carrier tomorrow. "
                "ticket_id: TKT-502."
            )
        },
    )
    assert paused.status_code == 200, paused.text
    body = paused.json()
    assert body["status"] == "awaiting_confirmation", body
    assert body["interrupt"]["action_type"] == "create_follow_up_task"
    thread_id = body["thread_id"]

    resumed = client.post(
        "/chat/resume",
        headers=headers,
        json={"thread_id": thread_id, "decision": "cancel"},
    )
    assert resumed.status_code == 200, resumed.text
    done = resumed.json()
    assert done["status"] == "completed", done
    assert "create_follow_up_task" in {t["tool"] for t in done["tools_used"]}

    after = get_session_factory()()
    count_after = after.scalar(select(func.count()).select_from(FollowUpTask)) or 0
    after.close()
    assert count_after == count_before
