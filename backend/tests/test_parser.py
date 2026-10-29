from app.lexer import tokenize
from app.parser.parser import parse_program


def test_valid_variable_declaration():
    result = parse_program("int x = 10;")
    assert result.valid is True
    assert result.syntax_errors == []
    assert result.statements[0]["kind"] == "declaration"


def test_valid_assignment():
    result = parse_program("x = 25;")
    assert result.valid is True
    assert result.statements[0]["kind"] == "assignment"


def test_valid_arithmetic_expression():
    result = parse_program("int total = (a + 2) * 3;")
    assert result.valid is True
    assert result.statements[0]["initializer"]["kind"] == "binary"


def test_valid_multiple_statement_program():
    result = parse_program("int x = 1; x = x + 2; int y = 3;")
    assert result.valid is True
    assert len(result.statements) == 3


def test_valid_for_loop_with_declaration_initializer():
    result = parse_program("for (int i = 0; i < 3; i + 1) { x = x + i; }")
    assert result.valid is True
    assert result.statements[0]["kind"] == "for"
    assert result.statements[0]["init"]["kind"] == "declaration"


def test_valid_for_loop_with_assignment_initializer():
    result = parse_program("for (i = 0; i < 3; i + 1) x = x + i;")
    assert result.valid is True
    assert result.statements[0]["kind"] == "for"
    assert result.statements[0]["init"]["kind"] == "assignment"


def test_missing_semicolon():
    result = parse_program("int x = 10")
    assert result.valid is False
    assert any(error.category == "missing-token" for error in result.syntax_errors)


def test_missing_closing_parenthesis():
    result = parse_program("int x = (10 + 2;")
    assert result.valid is False
    assert any("Expected ')'" in error.message for error in result.syntax_errors)


def test_missing_closing_brace():
    result = parse_program("if (x > 0) { x = x + 1; ")
    assert result.valid is False
    assert any("Expected '}'" in error.message for error in result.syntax_errors)


def test_missing_operand():
    result = parse_program("int x = ;")
    assert result.valid is False
    assert any(error.category == "missing-operand" for error in result.syntax_errors)


def test_unexpected_operator():
    result = parse_program("int x = 5 ** 3;")
    assert result.valid is False
    assert any(error.category == "unexpected-token" for error in result.syntax_errors)


def test_invalid_statement_structure():
    result = parse_program("if x = 1;")
    assert result.valid is False
    assert any("Expected '('" in error.message for error in result.syntax_errors)


def test_empty_input():
    result = parse_program("")
    assert result.valid is True
    assert result.statements == []


def test_multiple_syntax_errors_in_one_program():
    result = parse_program("if (x > 0 { y = ;")
    assert result.valid is False
    assert len(result.syntax_errors) >= 2


def test_unexpected_end_of_input():
    result = parse_program("int x = (1 + 2")
    assert result.valid is False
    assert any("Expected ')'" in error.message for error in result.syntax_errors)


def test_valid_program_with_comments_and_whitespace():
    result = parse_program("// comment\nint x = 1; /* block comment */\nif (x > 0) { x = 2; }")
    assert result.valid is True
    assert len(result.statements) == 2


def test_lexical_errors_passed_through():
    result = parse_program("int x = 5 @ 3;")
    assert result.valid is False
    assert len(result.lexical_errors) == 1
    assert result.lexical_errors[0]["code"] == "INVALID_CHARACTER"
    assert result.lexical_errors[0]["lexeme"] == "@"
    assert result.syntax_errors == []


def test_lexer_and_health_endpoints_still_work():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    health = client.get("/api/health")
    lexed = client.post("/api/lex", json={"source": "int x = 10;"})
    assert health.status_code == 200
    assert lexed.status_code == 200
    assert lexed.json()["token_count"] == 5
