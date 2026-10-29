from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_suggestions_endpoint_valid_source():
    response = client.post("/api/suggestions", json={"source": "int x = 1;"})
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["has_errors"] is False
    assert body["suggestions"] == []


def test_suggestions_endpoint_invalid_source():
    response = client.post("/api/suggestions", json={"source": "int x = (10 + 2;"})
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["has_errors"] is True
    assert len(body["suggestions"]) >= 1
    assert body["suggestions"][0]["action"] in {"insert", "replace", "remove", "explanatory_only"}


def test_suggestions_endpoint_rejects_malformed_input():
    response = client.post("/api/suggestions", json={"source": ["int x = 1;"]})
    assert response.status_code == 422
