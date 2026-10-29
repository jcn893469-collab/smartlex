from app.storage import (
    configure_database,
    delete_analysis_record,
    get_analysis_record,
    initialize_database,
    list_analysis_records,
    save_analysis_record,
)


def test_save_and_retrieve_analysis_record(tmp_path, monkeypatch):
    db_path = tmp_path / "smartlex-history.sqlite3"
    monkeypatch.setenv("SMARTLEX_DB_PATH", str(db_path))
    configure_database(str(db_path))
    initialize_database()

    record = save_analysis_record(
        source="int x = 1;",
        analysis_type="parse",
        status="valid",
        token_count=5,
        error_count=0,
        result={"valid": True, "statement_count": 1},
    )

    assert record["source"] == "int x = 1;"
    assert record["analysis_type"] == "parse"
    assert record["result"]["valid"] is True

    records = list_analysis_records(limit=10)
    assert len(records) == 1
    assert records[0]["id"] == record["id"]

    same_record = get_analysis_record(record["id"])
    assert same_record["error_count"] == 0

    assert delete_analysis_record(record["id"]) is True
    assert list_analysis_records(limit=10) == []


def test_missing_record_raises_key_error(tmp_path, monkeypatch):
    db_path = tmp_path / "missing-history.sqlite3"
    monkeypatch.setenv("SMARTLEX_DB_PATH", str(db_path))
    configure_database(str(db_path))
    initialize_database()

    try:
        get_analysis_record(999)
        assert False, "Expected KeyError for missing record"
    except KeyError:
        assert True
