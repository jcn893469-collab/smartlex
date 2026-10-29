from fastapi.testclient import TestClient

from app.main import app
from app.storage import configure_database, initialize_database


def test_history_api_round_trip(tmp_path, monkeypatch):
    db_path = tmp_path / "history-api.sqlite3"
    monkeypatch.setenv("SMARTLEX_DB_PATH", str(db_path))
    configure_database(str(db_path))
    initialize_database()

    client = TestClient(app)

    create_response = client.post(
        "/api/history",
        json={
            "source": "int x = 1;",
            "analysis_type": "parse",
            "status": "valid",
            "token_count": 5,
            "error_count": 0,
            "summary": "Saved valid parse",
            "result": {"valid": True, "statement_count": 1},
        },
    )
    assert create_response.status_code == 200
    body = create_response.json()
    assert body["source"] == "int x = 1;"
    assert body["analysis_type"] == "parse"

    list_response = client.get("/api/history")
    assert list_response.status_code == 200
    assert list_response.json()["total"] >= 1

    record_response = client.get(f"/api/history/{body['id']}")
    assert record_response.status_code == 200
    assert record_response.json()["id"] == body["id"]

    delete_response = client.delete(f"/api/history/{body['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True

    missing_response = client.get(f"/api/history/{body['id']}")
    assert missing_response.status_code == 404


def test_history_api_rejects_invalid_payload(tmp_path, monkeypatch):
    db_path = tmp_path / "history-invalid.sqlite3"
    monkeypatch.setenv("SMARTLEX_DB_PATH", str(db_path))
    configure_database(str(db_path))
    initialize_database()

    client = TestClient(app)
    response = client.post("/api/history", json={"source": ["not", "valid"]})
    assert response.status_code == 422
