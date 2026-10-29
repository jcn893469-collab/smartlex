from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_diagnose_valid_source():
    response = client.post("/api/diagnose", json={"source": "int x = 1;"})
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["has_errors"] is False
    assert body["diagnoses"] == []


def test_diagnose_invalid_source():
    response = client.post("/api/diagnose", json={"source": "int x = (10 + 2;"})
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["has_errors"] is True
    assert len(body["diagnoses"]) >= 1
    assert body["diagnoses"][0]["category"] == "unmatched-delimiter"


def test_diagnose_lexical_error_source():
    response = client.post("/api/diagnose", json={"source": "int x = 5 @ 3;"})
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["has_errors"] is True
    assert body["diagnoses"][0]["category"] == "invalid-or-unrecognized-character"


def test_diagnose_empty_source():
    response = client.post("/api/diagnose", json={"source": ""})
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["has_errors"] is False
    assert body["diagnoses"] == []
