from app.lexer import LexicalErrorCode, TokenType, tokenize


def lexemes(source):
    return [t.lexeme for t in tokenize(source).tokens]


def types(source):
    return [t.type for t in tokenize(source).tokens]


def error_codes(source):
    return [e.code for e in tokenize(source).errors]


def test_simple_declaration():
    result = tokenize("int age = 20;")
    assert [t.type for t in result.tokens] == [
        TokenType.KEYWORD,
        TokenType.IDENTIFIER,
        TokenType.OPERATOR,
        TokenType.INTEGER,
        TokenType.DELIMITER,
    ]
    assert [t.lexeme for t in result.tokens] == ["int", "age", "=", "20", ";"]
    assert result.errors == []


def test_line_and_column_positions():
    result = tokenize("int x;\nfloat y;")
    float_tok = result.tokens[3]
    y_tok = result.tokens[4]
    assert (float_tok.lexeme, float_tok.line, float_tok.column) == ("float", 2, 1)
    assert (y_tok.lexeme, y_tok.line, y_tok.column) == ("y", 2, 7)


def test_keyword_versus_identifier():
    assert types("integer int _x1") == [
        TokenType.IDENTIFIER,
        TokenType.KEYWORD,
        TokenType.IDENTIFIER,
    ]


def test_longest_match_operators():
    assert lexemes("a<<=b") == ["a", "<<=", "b"]
    assert lexemes("a==b!=c") == ["a", "==", "b", "!=", "c"]
    assert lexemes("i++") == ["i", "++"]
    assert lexemes("x->y") == ["x", "->", "y"]
    assert lexemes("a&&b||c") == ["a", "&&", "b", "||", "c"]


def test_delimiters():
    result = tokenize("(){}[];,.")
    assert len(result.tokens) == 9
    assert all(t.type == TokenType.DELIMITER for t in result.tokens)


def test_float_literals():
    result = tokenize("3.14 2e10 1.5E-3")
    assert [t.lexeme for t in result.tokens] == ["3.14", "2e10", "1.5E-3"]
    assert all(t.type == TokenType.FLOAT for t in result.tokens)
    assert result.errors == []


def test_string_literal_with_escaped_quote():
    result = tokenize('s = "a\\"b";')
    assert result.errors == []
    assert result.tokens[2].type == TokenType.STRING
    assert result.tokens[2].lexeme == '"a\\"b"'


def test_char_literals():
    result = tokenize("'a' '\\n'")
    assert result.errors == []
    assert [t.type for t in result.tokens] == [TokenType.CHAR, TokenType.CHAR]


def test_comments_are_skipped():
    result = tokenize("int a; // note\n/* multi\nline */ int b;")
    assert [t.lexeme for t in result.tokens] == ["int", "a", ";", "int", "b", ";"]
    assert result.tokens[-2].line == 3
    assert result.errors == []


def test_invalid_character():
    result = tokenize("int a = 5 @ 3;")
    assert len(result.errors) == 1
    err = result.errors[0]
    assert err.code == LexicalErrorCode.INVALID_CHARACTER
    assert err.lexeme == "@"
    assert (err.line, err.column) == (1, 11)
    assert "3" in [t.lexeme for t in result.tokens]


def test_non_ascii_character_is_invalid():
    assert error_codes("int é = 1;") == [LexicalErrorCode.INVALID_CHARACTER]


def test_multiple_invalid_characters():
    assert error_codes("int a = 5 @ 3 # 4;") == [
        LexicalErrorCode.INVALID_CHARACTER,
        LexicalErrorCode.INVALID_CHARACTER,
    ]


def test_identifier_starting_with_digit():
    result = tokenize("int 9abc = 1;")
    assert len(result.errors) == 1
    err = result.errors[0]
    assert err.code == LexicalErrorCode.INVALID_IDENTIFIER
    assert err.lexeme == "9abc"
    assert (err.line, err.column) == (1, 5)
    assert "9abc" not in [t.lexeme for t in result.tokens]


def test_malformed_numbers():
    assert error_codes("x = 1.2.3;") == [LexicalErrorCode.MALFORMED_NUMBER]
    assert error_codes("x = 1e;") == [LexicalErrorCode.MALFORMED_NUMBER]
    result = tokenize("x = 2e+;")
    assert [e.code for e in result.errors] == [LexicalErrorCode.MALFORMED_NUMBER]
    assert result.errors[0].lexeme == "2e+"


def test_unterminated_string_reports_position_and_recovers():
    result = tokenize('char *s = "hello;\nint x;')
    assert len(result.errors) == 1
    err = result.errors[0]
    assert err.code == LexicalErrorCode.UNTERMINATED_STRING
    assert (err.line, err.column) == (1, 11)
    int_tokens = [t for t in result.tokens if t.lexeme == "int"]
    assert int_tokens and int_tokens[0].line == 2


def test_unterminated_comment():
    result = tokenize("int a; /* oops")
    assert len(result.errors) == 1
    err = result.errors[0]
    assert err.code == LexicalErrorCode.UNTERMINATED_COMMENT
    assert (err.line, err.column) == (1, 8)


def test_char_literal_errors():
    assert error_codes("''") == [LexicalErrorCode.EMPTY_CHAR_LITERAL]
    assert error_codes("'ab'") == [LexicalErrorCode.MULTI_CHAR_LITERAL]
    assert error_codes("'a") == [LexicalErrorCode.UNTERMINATED_CHAR]


def test_invalid_escape_sequence_still_produces_string_token():
    result = tokenize('"a\\qb"')
    assert [e.code for e in result.errors] == [LexicalErrorCode.INVALID_ESCAPE]
    assert (result.errors[0].line, result.errors[0].column) == (1, 3)
    assert len(result.tokens) == 1
    assert result.tokens[0].type == TokenType.STRING


def test_empty_and_whitespace_only_source():
    for source in ("", "   \n\t\n  "):
        result = tokenize(source)
        assert result.tokens == []
        assert result.errors == []


def test_crlf_line_endings():
    result = tokenize("int a;\r\nint b;")
    assert result.tokens[-2].lexeme == "b"
    assert result.tokens[-2].line == 2


def test_to_dict_shape():
    data = tokenize("int a = 5 @;").to_dict()
    assert data["token_count"] == 5
    assert data["error_count"] == 1
    assert data["has_errors"] is True
    assert data["tokens"][0] == {
        "type": "KEYWORD",
        "lexeme": "int",
        "line": 1,
        "column": 1,
    }
    assert data["errors"][0]["kind"] == "lexical"
    assert data["errors"][0]["code"] == "INVALID_CHARACTER"
