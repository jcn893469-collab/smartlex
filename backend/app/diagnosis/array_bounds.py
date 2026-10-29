import ast
import operator
from typing import Optional

from app.lexer import tokenize
from app.lexer.token import Token, TokenType

_TYPES = {"int", "float", "double", "char", "bool"}
_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.FloorDiv: lambda left, right: int(left / right),
    ast.Div: lambda left, right: int(left / right),
    ast.Mod: operator.mod,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _evaluate(tokens: list[Token], constants: dict[str, int]) -> Optional[int]:
    expression = "".join(token.lexeme for token in tokens)
    if not expression:
        return None
    try:
        node = ast.parse(expression, mode="eval").body
    except (SyntaxError, ValueError):
        return None

    def visit(value: ast.AST) -> int:
        if isinstance(value, ast.Constant) and isinstance(value.value, int):
            return value.value
        if isinstance(value, ast.Name) and value.id in constants:
            return constants[value.id]
        if isinstance(value, ast.BinOp) and type(value.op) in _BINARY_OPERATORS:
            right = visit(value.right)
            if isinstance(value.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
                raise ValueError
            return _BINARY_OPERATORS[type(value.op)](visit(value.left), right)
        if isinstance(value, ast.UnaryOp) and type(value.op) in _UNARY_OPERATORS:
            return _UNARY_OPERATORS[type(value.op)](visit(value.operand))
        raise ValueError

    try:
        return visit(node)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def _closing_bracket(tokens: list[Token], opening: int) -> Optional[int]:
    depth = 0
    for index in range(opening, len(tokens)):
        if tokens[index].lexeme == "[":
            depth += 1
        elif tokens[index].lexeme == "]":
            depth -= 1
            if depth == 0:
                return index
    return None


def find_array_bounds_errors(source: str) -> list[dict]:
    tokens = tokenize(source).tokens
    arrays: dict[str, int] = {}
    constants: dict[str, int] = {}
    declaration_ids: set[int] = set()
    findings: list[dict] = []
    index = 0

    while index < len(tokens):
        token = tokens[index]
        if (
            token.type in {TokenType.KEYWORD, TokenType.IDENTIFIER}
            and token.lexeme in _TYPES
            and index + 2 < len(tokens)
            and tokens[index + 1].type == TokenType.IDENTIFIER
        ):
            name = tokens[index + 1].lexeme
            following = tokens[index + 2].lexeme
            if following == "[":
                closing = _closing_bracket(tokens, index + 2)
                declaration_ids.add(index + 1)
                if closing is not None:
                    size = _evaluate(tokens[index + 3:closing], constants)
                    if size is not None and size > 0:
                        arrays[name] = size
            elif following == "=":
                end = index + 3
                while end < len(tokens) and tokens[end].lexeme != ";":
                    end += 1
                value = _evaluate(tokens[index + 3:end], constants)
                if value is not None:
                    constants[name] = value
                else:
                    constants.pop(name, None)

        if token.type == TokenType.IDENTIFIER and token.lexeme in arrays and index not in declaration_ids:
            if index + 1 < len(tokens) and tokens[index + 1].lexeme == "[":
                closing = _closing_bracket(tokens, index + 1)
                if closing is not None:
                    index_tokens = tokens[index + 2:closing]
                    resolved = _evaluate(index_tokens, constants)
                    if resolved is not None and not 0 <= resolved < arrays[token.lexeme]:
                        location = index_tokens[0] if index_tokens else tokens[index + 1]
                        findings.append({
                            "category": "array-index-out-of-bounds",
                            "explanation": (
                                f"Index {resolved} is outside the valid range "
                                f"0–{arrays[token.lexeme] - 1} for array '{token.lexeme}'."
                            ),
                            "line": location.line,
                            "column": location.column,
                            "offending_token": str(resolved),
                            "expected": f"0–{arrays[token.lexeme] - 1}",
                            "actual": str(resolved),
                            "root_cause": "A statically known array index is outside the declared array bounds.",
                            "confidence": 1.0,
                            "source": "deterministic",
                        })

        if token.type == TokenType.IDENTIFIER and index + 1 < len(tokens) and tokens[index + 1].lexeme == "=":
            if token.lexeme not in arrays:
                end = index + 2
                while end < len(tokens) and tokens[end].lexeme != ";":
                    end += 1
                value = _evaluate(tokens[index + 2:end], constants)
                if value is not None:
                    constants[token.lexeme] = value
                else:
                    constants.pop(token.lexeme, None)
        index += 1

    return findings
