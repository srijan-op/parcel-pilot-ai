import os

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv()

from app.agent.list_documents import list_documents
from app.auth.models import AuthUser
from app.main import app

client = TestClient(app)

_has_groq = bool(os.getenv("GROQ_API_KEY"))
needs_groq = pytest.mark.skipif(not _has_groq, reason="Requires GROQ_API_KEY")


def test_list_documents_customer_hides_other_agreements() -> None:
    user = AuthUser(
        user_id="northstar",
        name="Northstar User",
        role="customer",
        account_id="ACCT-001",
        persona_id="northstar",
    )
    docs = list_documents(user)
    ids = {d["doc_id"] for d in docs}
    assert "05_Northstar_Logistics_Enterprise_Agreement" in ids
    assert "06_LumenWorks_Service_Agreement" not in ids
    assert "02_Support_Policy_v2_DEPRECATED" not in ids


def test_chat_requires_auth() -> None:
    response = client.post("/chat", json={"message": "Can I cancel ORD-1001?"})
    assert response.status_code == 401


@needs_groq
def test_chat_agent_cancel_fee_smoke() -> None:
    login = client.post("/auth/login", json={"persona_id": "northstar"})
    token = login.json()["access_token"]
    response = client.post(
        "/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "Can Northstar cancel ORD-1001 without a cancellation fee?"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["thread_id"]
    assert body["answer"]
    tool_names = {t["tool"] for t in body["tools_used"]}
    # Agent should use structured data and/or calculators
    assert tool_names & {
        "structured_data_query",
        "document_search",
        "list_documents",
    }
