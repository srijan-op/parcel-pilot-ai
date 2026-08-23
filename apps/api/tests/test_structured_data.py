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
    reason="Requires configured DATABASE_URL (e.g. Supabase) in environment/.env",
)


def _login(persona_id: str) -> str:
    response = client.post("/auth/login", json={"persona_id": persona_id})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_list_intents() -> None:
    response = client.get("/tools/intents")
    assert response.status_code == 200
    body = response.json()
    assert "get_order" in body["lookups"]
    assert "calc_cancellation" in body["calculators_ready"]
    assert "calc_service_credit" in body["calculators_ready"]
    assert "calc_sla" in body["calculators_ready"]
    assert body["calculators_coming"] == []


@needs_db
def test_calc_service_credit_ord_2002_via_api() -> None:
    token = _login("lumenworks")
    response = client.post(
        "/tools/structured_data",
        json={"intent": "calc_service_credit", "order_id": "ORD-2002"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["eligible"] is True
    assert data["amount_inr"] == 300
    assert data["agreement_override"] is True


@needs_db
def test_calc_sla_tkt_501_via_api() -> None:
    token = _login("maya")
    response = client.post(
        "/tools/structured_data",
        json={"intent": "calc_sla", "ticket_id": "TKT-501"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["severity"] == "P1"
    assert data["target_minutes"] == 15
    assert data["breached"] is True


@needs_db
def test_calc_cancellation_ord_1001_via_api() -> None:
    token = _login("northstar")
    response = client.post(
        "/tools/structured_data",
        json={"intent": "calc_cancellation", "order_id": "ORD-1001"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["allowed"] is True
    assert data["fee_inr"] == 0
    assert data["agreement_override"] is True


@needs_db
def test_calc_cancellation_acl_blocks_other_account() -> None:
    token = _login("beacon")
    response = client.post(
        "/tools/structured_data",
        json={"intent": "calc_cancellation", "order_id": "ORD-1001"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_structured_data_requires_auth() -> None:
    response = client.post(
        "/tools/structured_data",
        json={"intent": "get_order", "order_id": "ORD-1001"},
    )
    assert response.status_code == 401


def test_unknown_intent() -> None:
    token = _login("maya")
    response = client.post(
        "/tools/structured_data",
        json={"intent": "drop_table"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


@needs_db
def test_customer_get_own_order() -> None:
    token = _login("northstar")
    response = client.post(
        "/tools/structured_data",
        json={"intent": "get_order", "order_id": "ORD-1001"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["order_id"] == "ORD-1001"
    assert data["account_id"] == "ACCT-001"


@needs_db
def test_customer_cannot_get_other_order() -> None:
    token = _login("northstar")
    response = client.post(
        "/tools/structured_data",
        json={"intent": "get_order", "order_id": "ORD-2001"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


@needs_db
def test_customer_list_orders_scoped() -> None:
    token = _login("northstar")
    response = client.post(
        "/tools/structured_data",
        json={"intent": "list_orders"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["scoped_account_id"] == "ACCT-001"
    assert all(o["account_id"] == "ACCT-001" for o in body["data"])


@needs_db
def test_internal_get_cross_account_ticket() -> None:
    token = _login("maya")
    response = client.post(
        "/tools/structured_data",
        json={"intent": "get_ticket", "ticket_id": "TKT-501"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["ticket_id"] == "TKT-501"


@needs_db
def test_get_account() -> None:
    token = _login("lumenworks")
    response = client.post(
        "/tools/structured_data",
        json={"intent": "get_account"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["account_id"] == "ACCT-002"
