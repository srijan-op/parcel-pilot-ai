import pytest
from fastapi.testclient import TestClient

from app.auth.acl import (
    ACLError,
    assert_account_access,
    resolve_account_scope,
    scope_document_search,
)
from app.auth.models import AuthUser
from app.main import app

client = TestClient(app)


def _customer(account_id: str = "ACCT-001") -> AuthUser:
    return AuthUser(
        user_id="northstar",
        name="Northstar User",
        role="customer",
        account_id=account_id,
        persona_id="northstar",
    )


def _internal() -> AuthUser:
    return AuthUser(
        user_id="maya",
        name="Maya",
        role="support_agent",
        account_id=None,
        persona_id="maya",
    )


def test_customer_forced_to_own_account() -> None:
    assert resolve_account_scope(_customer(), None) == "ACCT-001"
    assert resolve_account_scope(_customer(), "ACCT-001") == "ACCT-001"


def test_customer_cannot_request_other_account() -> None:
    with pytest.raises(ACLError):
        resolve_account_scope(_customer("ACCT-001"), "ACCT-002")


def test_internal_can_query_any_or_all() -> None:
    assert resolve_account_scope(_internal(), None) is None
    assert resolve_account_scope(_internal(), "ACCT-002") == "ACCT-002"


def test_assert_account_access() -> None:
    assert_account_access(_customer(), "ACCT-001")
    assert_account_access(_customer(), None)  # global docs OK
    with pytest.raises(ACLError):
        assert_account_access(_customer(), "ACCT-002")
    assert_account_access(_internal(), "ACCT-004")


def test_scope_document_search_strips_deprecated_for_customer() -> None:
    account, include_deprecated = scope_document_search(
        _customer(),
        requested_account_id=None,
        include_deprecated=True,
    )
    assert account == "ACCT-001"
    assert include_deprecated is False


def test_search_requires_auth() -> None:
    response = client.get("/search/documents", params={"q": "P1 response"})
    assert response.status_code == 401


def test_customer_search_forbidden_other_account() -> None:
    login = client.post("/auth/login", json={"persona_id": "northstar"})
    token = login.json()["access_token"]
    response = client.get(
        "/search/documents",
        params={"q": "P1", "account_id": "ACCT-002"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_customer_search_scopes_own_account() -> None:
    login = client.post("/auth/login", json={"persona_id": "northstar"})
    token = login.json()["access_token"]
    response = client.get(
        "/search/documents",
        params={"q": "P1 response time"},
        headers={"Authorization": f"Bearer {token}"},
    )
    # 200 if Chroma+Gemini available; 503 if embeddings unavailable in CI
    assert response.status_code in (200, 503)
    if response.status_code == 200:
        body = response.json()
        assert body["scoped_account_id"] == "ACCT-001"
        for chunk in body["chunks"]:
            chunk_account = chunk.get("account_id")
            assert chunk_account in (None, "ACCT-001")
