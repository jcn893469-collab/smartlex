import re
from bisect import bisect_right
from typing import List

from app.lexer.lexer import LexResult
from app.lexer.token import KEYWORDS, Token, TokenType

_FLEX_TOKEN = re.compile(
    r"%%|%\{|%\}|[A-Za-z_][A-Za-z_0-9]*|\d+(?:\.\d+)?|"
    r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|'
    r"\\.|->|==|!=|<=|>=|&&|\|\||[^\s]"
)


def tokenize_flex(source: str) -> LexResult:
    normalized = source.replace("\r\n", "\n").replace("\r", "\n")
    tokens: List[Token] = []
    line_starts = [0]
    line_starts.extend(match.end() for match in re.finditer("\n", normalized))
    for match in _FLEX_TOKEN.finditer(normalized):
        lexeme = match.group(0)
        line_index = bisect_right(line_starts, match.start()) - 1
        line = line_index + 1
        column = match.start() - line_starts[line_index] + 1
        if lexeme in KEYWORDS:
            token_type = TokenType.KEYWORD
        elif lexeme[0].isalpha() or lexeme[0] == "_":
            token_type = TokenType.IDENTIFIER
        elif lexeme[0].isdigit():
            token_type = TokenType.FLOAT if "." in lexeme else TokenType.INTEGER
        elif lexeme.startswith('"'):
            token_type = TokenType.STRING
        elif lexeme.startswith("'"):
            token_type = TokenType.CHAR
        elif lexeme in "(){}[];,. :":
            token_type = TokenType.DELIMITER
        else:
            token_type = TokenType.OPERATOR
        tokens.append(Token(token_type, lexeme, line, column))

    return LexResult(tokens=tokens, errors=[])


def validate_flex_structure(source: str) -> list[dict]:
    errors: list[dict] = []
    markers = [match.start() for match in re.finditer(r"(?m)^\s*%%\s*(?:$|#)", source)]
    prologue_opens = len(re.findall(r"%\{", source))
    prologue_closes = len(re.findall(r"%\}", source))

    def add_error(message: str, position: int, lexeme: str) -> None:
        prefix = source[:position]
        errors.append({
            "kind": "syntax",
            "category": "malformed-flex-structure",
            "message": message,
            "line": prefix.count("\n") + 1,
            "column": position - prefix.rfind("\n"),
            "lexeme": lexeme,
            "expected": None,
            "actual": lexeme,
        })

    if len(markers) == 0:
        add_error("A Lex/Flex specification must contain a '%%' rules delimiter", len(source), "EOF")
    elif len(markers) > 2:
        add_error("A Lex/Flex specification may contain at most two '%%' delimiters", markers[2], "%%")

    open_match = re.search(r"%\{", source)
    close_match = re.search(r"%\}", source)
    if prologue_opens != prologue_closes:
        position = open_match.start() if open_match else (close_match.start() if close_match else len(source))
        add_error("The '%{ ... %}' C prologue is not closed", position, "%{" if prologue_opens > prologue_closes else "%}")

    brace_source = source.replace("%{", "  ").replace("%}", "  ")
    depth = 0
    for position, char in enumerate(brace_source):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                add_error("Unexpected '}' in Lex/Flex rules or C action", position, "}")
                depth = 0
    if depth:
        add_error("A C action block is missing a closing '}'", len(source), "EOF")

    if markers:
        rules_start = source.find("\n", markers[0])
        rules_start = len(source) if rules_start < 0 else rules_start + 1
        rules_end = markers[1] if len(markers) > 1 else len(source)
        rule_text = source[rules_start:rules_end]
        meaningful = [line for line in rule_text.splitlines() if line.strip() and not line.lstrip().startswith("//")]
        if not meaningful:
            add_error("The Lex/Flex rules section is empty", rules_start, "%%")

    return errors


def flex_syntax_diagnostics(source: str) -> list[dict]:
    return validate_flex_structure(source)
