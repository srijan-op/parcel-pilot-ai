from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_list_personas() -> None:
    response = client.get("/auth/personas")
    assert response.status_code == 200
    personas = response.json()
    ids = {p["persona_id"] for p in personas}
    assert ids == {"northstar", "lumenworks", "beacon", "axis", "maya", "ops"}
    northstar = next(p for p in personas if p["persona_id"] == "northstar")
    assert northstar["role"] == "customer"
    assert northstar["account_id"] == "ACCT-001"
    maya = next(p for p in personas if p["persona_id"] == "maya")
    assert maya["role"] == "support_agent"
    assert maya["account_id"] is None


def test_login_returns_jwt() -> None:
    response = client.post("/auth/login", json={"persona_id": "northstar"})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["persona_id"] == "northstar"
    assert body["user"]["account_id"] == "ACCT-001"
    assert body["user"]["role"] == "customer"


def test_me_with_token() -> None:
    login = client.post("/auth/login", json={"persona_id": "maya"})
    token = login.json()["access_token"]
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["persona_id"] == "maya"
    assert body["role"] == "support_agent"
    assert body["account_id"] is None


def test_me_without_token_is_401() -> None:
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_login_unknown_persona() -> None:
    response = client.post("/auth/login", json={"persona_id": "nobody"})
    assert response.status_code == 404
