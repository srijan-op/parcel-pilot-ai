import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL") or "localhost" in os.getenv("DATABASE_URL", ""),
    reason="Requires configured Supabase DATABASE_URL in .env",
)
def test_data_stats_after_ingest() -> None:
    response = client.get("/data/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["accounts"] == 4
    assert body["orders"] == 6
    assert body["tickets"] == 7
    assert body["documents"] == 6
