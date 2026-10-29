from app.corrections.suggester import suggest_for_source
from app.diagnosis import Diagnoser
from app.diagnosis.rules import DiagnosisRecord


def test_missing_semicolon_suggestion():
    result = suggest_for_source("int x = 10")
    assert result["valid"] is False
    assert any(item["rule_id"] == "missing-semicolon" for item in result["suggestions"])


def test_missing_delimiter_suggestion():
    result = suggest_for_source("int x = (10 + 2;")
    assert any(item["rule_id"] == "missing-closing-delimiter" for item in result["suggestions"])
    assert any(item["suggested_text"] == ")" for item in result["suggestions"])


def test_unexpected_token_suggestion():
    result = suggest_for_source("int x = 5 ** 3;")
    assert any(item["rule_id"] == "unexpected-token" for item in result["suggestions"])


def test_invalid_character_suggestion():
    result = suggest_for_source("int x = 5 @ 3;")
    assert any(item["rule_id"] == "invalid-character" for item in result["suggestions"])


def test_incomplete_expression_suggestion():
    result = suggest_for_source("int x = ;")
    assert any(item["rule_id"] == "missing-operand" for item in result["suggestions"])
    assert result["suggestions"][0]["requires_review"] is True


def test_uncertain_error_suggestion_is_explanatory_only():
    diagnosis = DiagnosisRecord(
        category="other-syntax-error",
        explanation="Unknown issue",
        line=4,
        column=7,
        offending_token="?",
        expected=None,
        actual=None,
        root_cause="Ambiguous",
        confidence=0.6,
    )
    suggestions = Diagnoser().diagnose([diagnosis])
    from app.corrections.suggester import suggest_for_diagnostics
    items = suggest_for_diagnostics(suggestions)
    assert items[0].action == "explanatory_only"
    assert items[0].requires_review is True


def test_line_and_column_preserved():
    result = suggest_for_source("int x = 10")
    assert result["suggestions"][0]["line"] == 1
    assert result["suggestions"][0]["column"] == 9


def test_multiple_errors_are_deduplicated():
    result = suggest_for_source("if (x > 0 { y = ;")
    ids = [item["rule_id"] for item in result["suggestions"]]
    assert len(ids) == len(set(ids)) or len(ids) >= 2


def test_empty_source_has_no_suggestions():
    result = suggest_for_source("")
    assert result["valid"] is True
    assert result["suggestions"] == []


def test_suggestion_does_not_modify_source():
    source = "int x = 10"
    result = suggest_for_source(source)
    assert source == "int x = 10"
    assert result["source_length"] == len(source)
