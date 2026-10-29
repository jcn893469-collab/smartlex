from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_parse_valid_source():
    response = client.post("/api/parse", json={"source": "int total = 5 + 7;"})
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["has_errors"] is False
    assert body["statement_count"] == 1


def test_parse_invalid_source():
    response = client.post("/api/parse", json={"source": "int x = (10 + 2;"})
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["has_errors"] is True
    assert body["syntax_errors"][0]["category"] == "missing-token"


def test_parse_empty_source():
    response = client.post("/api/parse", json={"source": ""})
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["statements"] == []


def test_parse_rejects_wrong_type():
    response = client.post("/api/parse", json={"source": ["int x = 1;"]})
    assert response.status_code == 422


def test_parse_lexical_error_is_returned_as_syntax_error_payload():
    response = client.post("/api/parse", json={"source": "int x = 5 @ 3;"})
    assert response.status_code == 200
    body = response.json()
    assert body["has_errors"] is True
    assert body["diagnostics"][0]["kind"] == "lexical"
