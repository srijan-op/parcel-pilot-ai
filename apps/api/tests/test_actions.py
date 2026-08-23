import os

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv()

from app.main import app

client = TestClient(app)

_db_url = os.getenv("DATABASE_URL", "")
needs_db = pytest.mark.skipif(
    not _db_url or "localhost" in _db_url or "user:password" in _db_url,
    reason="Requires configured DATABASE_URL",
)


def _login(persona_id: str) -> str:
    response = client.post("/auth/login", json={"persona_id": persona_id})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_actions_require_auth() -> None:
    response = client.post(
        "/actions/escalate",
        json={
            "ticket_id": "TKT-501",
            "severity": "P1",
            "reason": "breached",
            "recommended_next_step": "page on-call",
        },
    )
    assert response.status_code == 401


@needs_db
def test_g14_escalation_without_confirm_no_row() -> None:
    from sqlalchemy import func, select

    from app.db.models import Escalation
    from app.db.session import get_session_factory

    token = _login("maya")
    before = get_session_factory()()
    count_before = before.scalar(select(func.count()).select_from(Escalation)) or 0
    before.close()

    propose = client.post(
        "/actions/escalate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "ticket_id": "TKT-501",
            "severity": "P1",
            "reason": "Production outage; SLA breached",
            "recommended_next_step": "Page on-call + notify CSM Priya Mehta",
        },
    )
    assert propose.status_code == 200
    body = propose.json()
    assert body["needs_confirmation"] is True
    pending_id = body["pending_action"]["pending_id"]
    assert body["pending_action"]["status"] == "pending"

    after = get_session_factory()()
    count_after = after.scalar(select(func.count()).select_from(Escalation)) or 0
    after.close()
    assert count_after == count_before  # no escalation row yet


@needs_db
def test_g15_escalation_with_confirm_creates_row() -> None:
    token = _login("maya")
    propose = client.post(
        "/actions/escalate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "ticket_id": "TKT-501",
            "severity": "P1",
            "reason": "Production outage; SLA breached",
            "recommended_next_step": "Page on-call + notify CSM",
        },
    )
    pending_id = propose.json()["pending_action"]["pending_id"]

    confirm = client.post(
        f"/actions/{pending_id}/confirm",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert confirm.status_code == 200
    body = confirm.json()
    assert body["executed"] is True
    assert body["result_ref"].startswith("ESC-")
    assert body["pending_action"]["status"] == "confirmed"


@needs_db
def test_cancel_pending_no_mutation() -> None:
    token = _login("maya")
    propose = client.post(
        "/actions/escalate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "ticket_id": "TKT-505",
            "severity": "P1",
            "reason": "API key exposure",
            "recommended_next_step": "Rotate keys + escalate",
        },
    )
    pending_id = propose.json()["pending_action"]["pending_id"]

    cancel = client.post(
        f"/actions/{pending_id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert cancel.status_code == 200
    assert cancel.json()["executed"] is False
    assert cancel.json()["pending_action"]["status"] == "cancelled"

    # Confirm after cancel should fail
    confirm = client.post(
        f"/actions/{pending_id}/confirm",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert confirm.status_code == 400


@needs_db
def test_customer_cannot_escalate_other_account() -> None:
    token = _login("beacon")
    response = client.post(
        "/actions/escalate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "ticket_id": "TKT-501",
            "severity": "P1",
            "reason": "x",
            "recommended_next_step": "y",
        },
    )
    assert response.status_code == 403
