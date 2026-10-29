from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.storage import configure_database, initialize_database

client = TestClient(app)


def analyze_source(source: str) -> dict:
    body = {"source": source}
    return {
        "lex": client.post("/api/lex", json=body),
        "parse": client.post("/api/parse", json=body),
        "diagnose": client.post("/api/diagnose", json=body),
        "suggestions": client.post("/api/suggestions", json=body),
    }


def assert_suggestions_reference_diagnoses(diagnoses: list[dict], suggestions: list[dict]) -> None:
    diagnosis_ids = {
        f"{item['category']}:{item['line']}:{item['column']}:{item['offending_token'] or 'unknown'}"
        for item in diagnoses
    }
    assert all(item["error_id"] in diagnosis_ids for item in suggestions)
    assert all(0 <= item["confidence"] <= 1 for item in suggestions)
    assert all(isinstance(item["requires_review"], bool) for item in suggestions)
    assert all(0 <= item["confidence"] <= 1 for item in diagnoses)


def test_valid_source_flows_consistently_through_all_analysis_apis():
    source = "int x = 1;\nx = x + 2;"
    responses = analyze_source(source)

    assert all(response.status_code == 200 for response in responses.values())
    lex = responses["lex"].json()
    parsed = responses["parse"].json()
    diagnosed = responses["diagnose"].json()
    suggested = responses["suggestions"].json()

    assert [token["lexeme"] for token in lex["tokens"]] == [
        "int", "x", "=", "1", ";", "x", "=", "x", "+", "2", ";"
    ]
    assert lex["token_count"] == len(lex["tokens"])
    assert parsed["valid"] is True
    assert parsed["statement_count"] == 2
    assert parsed["syntax_errors"] == []
    assert diagnosed["diagnoses"] == []
    assert suggested["suggestions"] == []


@pytest.mark.parametrize(
    "source",
    [
        "for (int i = 0; i < 3; i + 1) { x = x + i; }",
        "for (i = 0; i < 3; i + 1) x = x + i;",
    ],
)
def test_supported_for_loop_forms_flow_as_valid_across_apis(source: str):
    responses = analyze_source(source)

    assert all(response.status_code == 200 for response in responses.values())
    assert responses["parse"].json()["valid"] is True
    assert responses["parse"].json()["statements"][0]["kind"] == "for"
    assert responses["diagnose"].json()["diagnoses"] == []
    assert responses["suggestions"].json()["suggestions"] == []


def test_invalid_character_flows_from_lexer_to_diagnosis_and_suggestion():
    source = "int x = 5 @ 3;"
    responses = analyze_source(source)

    lex_error = responses["lex"].json()["errors"][0]
    parse = responses["parse"].json()
    diagnosis = responses["diagnose"].json()
    suggestion_result = responses["suggestions"].json()

    assert (
        lex_error["code"],
        lex_error["lexeme"],
        lex_error["line"],
        lex_error["column"],
    ) == ("INVALID_CHARACTER", "@", 1, 11)
    assert parse["lexical_errors"][0] == lex_error
    assert parse["syntax_errors"] == []
    assert diagnosis["diagnoses"][0]["category"] == "invalid-or-unrecognized-character"
    assert (diagnosis["diagnoses"][0]["line"], diagnosis["diagnoses"][0]["column"]) == (1, 11)
    assert suggestion_result["suggestions"][0]["rule_id"] == "invalid-character"
    assert suggestion_result["suggestions"][0]["original_text"] == "@"
    assert suggestion_result["suggestions"][0]["requires_review"] is False
    assert suggestion_result["source_length"] == len(source)
    assert_suggestions_reference_diagnoses(
        suggestion_result["diagnoses"], suggestion_result["suggestions"]
    )
    assert "corrected_source" not in suggestion_result
    assert "source" not in suggestion_result


@pytest.mark.parametrize(
    (
        "source",
        "expected_category",
        "expected_token",
        "expected_position",
        "expected_rule",
        "expected_text",
        "expected_action",
    ),
    [
        (
            "int x = 1", "missing-semicolon-or-delimiter", "EOF", (1, 9),
            "missing-semicolon", ";", "insert",
        ),
        (
            "int x = (1;", "unmatched-delimiter", ";", (1, 11),
            "missing-closing-delimiter", ")", "insert",
        ),
        (
            "if (x > 0) { x = 1;", "unmatched-delimiter", "EOF", (1, 19),
            "missing-closing-delimiter", "}", "insert",
        ),
        (
            "int x = ;", "missing-operand-or-operator", ";", (1, 9),
            "missing-operand", None, "explanatory_only",
        ),
    ],
)
def test_syntax_diagnostics_preserve_locations_and_suggestions_reference_errors(
    source: str,
    expected_category: str,
    expected_token: str,
    expected_position: tuple[int, int],
    expected_rule: str,
    expected_text: str | None,
    expected_action: str,
):
    responses = analyze_source(source)
    parsed = responses["parse"].json()
    diagnosis = responses["diagnose"].json()
    suggestion_result = responses["suggestions"].json()

    assert parsed["valid"] is False
    syntax_error = parsed["syntax_errors"][0]
    diagnosed = diagnosis["diagnoses"][0]
    assert diagnosed["category"] == expected_category
    assert diagnosed["offending_token"] == expected_token
    assert (diagnosed["line"], diagnosed["column"]) == expected_position
    assert (diagnosed["line"], diagnosed["column"]) == (syntax_error["line"], syntax_error["column"])
    assert_suggestions_reference_diagnoses(
        suggestion_result["diagnoses"], suggestion_result["suggestions"]
    )
    suggestion = suggestion_result["suggestions"][0]
    assert (suggestion["rule_id"], suggestion["suggested_text"], suggestion["action"]) == (
        expected_rule,
        expected_text,
        expected_action,
    )
    assert suggestion["requires_review"] is (expected_action == "explanatory_only")
    assert all(
        item["action"] == "explanatory_only"
        and item["suggested_text"] is None
        and item["requires_review"] is True
        for item in suggestion_result["suggestions"]
        if item["rule_id"] == "missing-operand"
    )


def test_multiple_syntax_errors_are_diagnosed_and_suggested_individually():
    source = "int x = ;\nint y = (2;"
    responses = analyze_source(source)
    parse = responses["parse"].json()
    diagnosis = responses["diagnose"].json()
    suggestion_result = responses["suggestions"].json()

    assert len(parse["syntax_errors"]) == 2
    assert len(diagnosis["diagnoses"]) == 2
    assert {(item["line"], item["column"]) for item in diagnosis["diagnoses"]} == {
        (1, 9), (2, 11)
    }
    assert_suggestions_reference_diagnoses(
        suggestion_result["diagnoses"], suggestion_result["suggestions"]
    )
    assert len({item["error_id"] for item in suggestion_result["suggestions"]}) == len(
        suggestion_result["suggestions"]
    )
    assert suggestion_result["source_length"] == len(source)


def test_multiple_lexical_errors_are_reported_without_inventing_syntax_errors():
    source = "int x = 5 @ 3;\nint y = 8 # 2;"
    responses = analyze_source(source)
    parse = responses["parse"].json()
    diagnosis = responses["diagnose"].json()
    suggestion_result = responses["suggestions"].json()

    assert [(item["lexeme"], item["line"], item["column"]) for item in parse["lexical_errors"]] == [
        ("@", 1, 11), ("#", 2, 11)
    ]
    assert parse["syntax_errors"] == []
    assert len(diagnosis["diagnoses"]) == 2
    assert len(suggestion_result["suggestions"]) == 2
    assert_suggestions_reference_diagnoses(
        suggestion_result["diagnoses"], suggestion_result["suggestions"]
    )


def test_uncertain_lexical_error_is_explanatory_and_does_not_modify_source():
    source = "int x = 'ab';"
    responses = analyze_source(source)
    suggestion_result = responses["suggestions"].json()
    suggestions = suggestion_result["suggestions"]

    assert suggestion_result["diagnoses"][0]["category"] == "other-lexical-error"
    assert len(suggestions) == 1
    assert suggestions[0]["action"] == "explanatory_only"
    assert suggestions[0]["suggested_text"] is None
    assert suggestions[0]["requires_review"] is True
    assert suggestions[0]["confidence"] == 0.95
    assert suggestion_result["source_length"] == len(source)


def test_empty_source_is_a_valid_empty_analysis_across_apis():
    responses = analyze_source("")

    assert all(response.status_code == 200 for response in responses.values())
    assert responses["lex"].json()["tokens"] == []
    assert responses["parse"].json()["statements"] == []
    assert responses["diagnose"].json()["diagnoses"] == []
    assert responses["suggestions"].json()["suggestions"] == []


@pytest.mark.parametrize(
    "path",
    ["/api/lex", "/api/parse", "/api/diagnose", "/api/suggestions"],
)
def test_analysis_apis_reject_malformed_source_payloads(path: str):
    response = client.post(path, json={"source": ["not", "source"]})

    assert response.status_code == 422
    assert response.json()["detail"]


def test_analysis_apis_reject_invalid_json_payloads():
    for path in ("/api/lex", "/api/parse", "/api/diagnose", "/api/suggestions"):
        response = client.post(path, content="{invalid", headers={"Content-Type": "application/json"})
        assert response.status_code == 422
        assert response.json()["detail"]


@pytest.mark.parametrize(
    "payload",
    [
        {"source": None},
        {"source": "x" * 100001},
    ],
)
def test_analysis_apis_reject_null_and_oversized_source(payload: dict):
    for path in ("/api/lex", "/api/parse", "/api/diagnose", "/api/suggestions"):
        response = client.post(path, json=payload)
        assert response.status_code == 422
        assert response.json()["detail"]


def test_openapi_advertises_the_existing_analysis_and_history_routes():
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert {"post"} <= set(paths["/api/lex"])
    assert {"post"} <= set(paths["/api/parse"])
    assert {"post"} <= set(paths["/api/diagnose"])
    assert {"post"} <= set(paths["/api/suggestions"])
    assert {"get", "post"} <= set(paths["/api/history"])
    assert {"get", "delete"} <= set(paths["/api/history/{analysis_id}"])


def test_history_routes_return_expected_validation_and_not_found_statuses():
    assert client.get("/api/history?limit=0").status_code == 422
    assert client.get("/api/history/not-an-id").status_code == 422
    assert client.get("/api/history/987654321").status_code == 404
    assert client.delete("/api/history/987654321").status_code == 404


def test_history_api_validates_payload_and_isolates_saved_records(tmp_path, monkeypatch):
    db_path = tmp_path / "workflow-history.sqlite3"
    monkeypatch.setenv("SMARTLEX_DB_PATH", str(db_path))
    configure_database(str(db_path))
    initialize_database()

    assert client.get("/api/history").json() == {"items": [], "total": 0}
    invalid = client.post("/api/history", json={"source": ["invalid"]})
    assert invalid.status_code == 422

    created = client.post(
        "/api/history",
        json={
            "source": "int saved = 1;",
            "analysis_type": "parse",
            "status": "valid",
            "token_count": 5,
            "error_count": 0,
            "summary": "Temporary workflow test record",
            "result": {"valid": True},
        },
    )
    assert created.status_code == 200
    record = created.json()
    assert record["source"] == "int saved = 1;"
    assert client.get("/api/history").json()["items"] == [record]
    assert client.get(f"/api/history/{record['id']}").json() == record
    assert client.delete(f"/api/history/{record['id']}").json() == {
        "deleted": True,
        "id": record["id"],
    }
    assert client.get(f"/api/history/{record['id']}").status_code == 404
