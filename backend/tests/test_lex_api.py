from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_lex_valid_source():
    response = client.post("/api/lex", json={"source": "int age = 20;"})
    assert response.status_code == 200
    body = response.json()
    assert body["token_count"] == 5
    assert body["error_count"] == 0
    assert body["has_errors"] is False
    assert body["tokens"][0]["type"] == "KEYWORD"


def test_lex_source_with_error():
    response = client.post("/api/lex", json={"source": "int a = 5 @ 3;"})
    assert response.status_code == 200
    body = response.json()
    assert body["has_errors"] is True
    assert body["errors"][0]["code"] == "INVALID_CHARACTER"
    assert body["errors"][0]["line"] == 1
    assert body["errors"][0]["column"] == 11


def test_lex_empty_source():
    response = client.post("/api/lex", json={"source": ""})
    assert response.status_code == 200
    body = response.json()
    assert body["tokens"] == []
    assert body["errors"] == []


def test_lex_rejects_wrong_type():
    response = client.post("/api/lex", json={"source": ["int a;"]})
    assert response.status_code == 422


def test_lex_rejects_oversized_source():
    response = client.post("/api/lex", json={"source": "a" * 100001})
    assert response.status_code == 422
