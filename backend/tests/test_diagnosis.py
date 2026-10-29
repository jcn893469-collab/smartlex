from app.diagnosis import Diagnoser
from app.lexer.errors import LexicalError, LexicalErrorCode
from app.parser.errors import ParseDiagnostic
from app.parser.parser import parse_program


def test_missing_semicolon_diagnosis():
    result = parse_program("int x = 10")
    diagnoses = Diagnoser().diagnose_syntax(result.syntax_errors)
    assert diagnoses.error_count >= 1
    assert diagnoses.items[0].category == "missing-semicolon-or-delimiter"


def test_unmatched_delimiter_diagnosis():
    result = parse_program("int x = (10 + 2;")
    diagnoses = Diagnoser().diagnose_syntax(result.syntax_errors)
    assert any(item.category == "unmatched-delimiter" for item in diagnoses.items)


def test_unexpected_token_diagnosis():
    result = parse_program("int x = 5 ** 3;")
    diagnoses = Diagnoser().diagnose_syntax(result.syntax_errors)
    assert any(item.category == "unexpected-token" for item in diagnoses.items)


def test_lexical_error_diagnosis():
    error = LexicalError(
        LexicalErrorCode.INVALID_CHARACTER,
        "Invalid character '@'",
        "@",
        1,
        9,
    )
    diagnoses = Diagnoser().diagnose_lexical([error])
    assert diagnoses.error_count == 1
    assert diagnoses.items[0].category == "invalid-or-unrecognized-character"
    assert diagnoses.items[0].offending_token == "@"


def test_multiple_errors_diagnosis():
    result = parse_program("if (x > 0 { y = ;")
    diagnoses = Diagnoser().diagnose_syntax(result.syntax_errors)
    assert diagnoses.error_count >= 2
    assert {item.category for item in diagnoses.items} <= {
        "missing-semicolon-or-delimiter",
        "unmatched-delimiter",
        "missing-operand-or-operator",
        "other-syntax-error",
        "unexpected-token",
    }


def test_empty_or_valid_input_diagnosis():
    diagnoses = Diagnoser().diagnose([])
    assert diagnoses.error_count == 0
    assert diagnoses.has_errors is False

    valid_result = parse_program("int x = 1;")
    assert valid_result.valid is True
    empty_diagnoses = Diagnoser().diagnose_syntax(valid_result.syntax_errors)
    assert empty_diagnoses.error_count == 0


def test_missing_diagnostic_details_are_safe():
    error = ParseDiagnostic(
        category="other",
        message="Unknown issue",
        line=4,
        column=7,
        lexeme="",
        expected=None,
        actual=None,
    )
    diagnosis = Diagnoser().diagnose([error]).items[0]
    assert diagnosis.line == 4
    assert diagnosis.column == 7
    assert diagnosis.explanation == "Unknown issue"
    assert diagnosis.confidence >= 0.0
    assert diagnosis.offending_token is None
