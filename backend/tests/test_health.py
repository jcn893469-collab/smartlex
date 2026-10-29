from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint_returns_ok():
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "SMARTLEX"
    assert "version" in body
    assert "timestamp" in body


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert "SMARTLEX" in response.json()["message"]