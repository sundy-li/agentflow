from fastapi.testclient import TestClient

from app.main import create_app


def test_health_check():
    client = TestClient(create_app())
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

