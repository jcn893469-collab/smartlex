from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from app.lexer.errors import LexicalError
from app.parser.errors import ParseDiagnostic


@dataclass(frozen=True)
class DiagnosisRule:
    category: str
    description: str
    predicate: Any


@dataclass(frozen=True)
class DiagnosisRecord:
    category: str
    explanation: str
    line: int
    column: int
    offending_token: Optional[str]
    expected: Optional[str]
    actual: Optional[str]
    root_cause: str
    confidence: float

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "explanation": self.explanation,
            "line": self.line,
            "column": self.column,
            "offending_token": self.offending_token,
            "expected": self.expected,
            "actual": self.actual,
            "root_cause": self.root_cause,
            "confidence": self.confidence,
        }


class DiagnosisResult:
    def __init__(self, items: Optional[List[DiagnosisRecord]] = None) -> None:
        self.items = items or []

    @property
    def error_count(self) -> int:
        return len(self.items)

    @property
    def has_errors(self) -> bool:
        return bool(self.items)

    def to_dict(self) -> dict:
        return {
            "diagnoses": [item.to_dict() for item in self.items],
            "error_count": self.error_count,
            "has_errors": self.has_errors,
        }


def _token_from_error(error: Any) -> Optional[str]:
    if hasattr(error, "lexeme"):
        return error.lexeme or None
    if isinstance(error, dict):
        return error.get("lexeme") or error.get("offending_token") or None
    return None


def _rule_missing_semicolon(error: Any) -> Optional[DiagnosisRecord]:
    if not isinstance(error, ParseDiagnostic):
        return None
    if error.category == "missing-token" and error.expected == ";":
        return DiagnosisRecord(
            category="missing-semicolon-or-delimiter",
            explanation="A statement appears to be missing a terminating semicolon or delimiter.",
            line=error.line,
            column=error.column,
            offending_token=_token_from_error(error),
            expected=";",
            actual=error.actual,
            root_cause="The parser reached the end of a statement without encountering the expected terminator.",
            confidence=0.92,
        )
    return None


def _rule_unmatched_delimiter(error: Any) -> Optional[DiagnosisRecord]:
    if not isinstance(error, ParseDiagnostic):
        return None
    token = error.lexeme or ""
    if error.category in {"missing-token", "unexpected-token"} and any(marker in (error.message or "") for marker in ["Expected ')'", "Expected '}'", "Expected ']'", "Expected '('", "Expected '{'"]):
        if "Expected ')'" in (error.message or ""):
            expected = ")"
        elif "Expected '}'" in (error.message or ""):
            expected = "}"
        elif "Expected ']'" in (error.message or ""):
            expected = "]"
        else:
            expected = None
        return DiagnosisRecord(
            category="unmatched-delimiter",
            explanation="A delimiter appears to be missing or mismatched.",
            line=error.line,
            column=error.column,
            offending_token=token or None,
            expected=expected,
            actual=error.actual,
            root_cause="The parser encountered a block or grouped expression that was not closed before the next token or end of input.",
            confidence=0.96 if expected else 0.85,
        )
    return None



def _rule_missing_operand(error: Any) -> Optional[DiagnosisRecord]:
    if not isinstance(error, ParseDiagnostic):
        return None

    if error.category != "missing-operand":
        return None

    token = _token_from_error(error)
    message = error.message or ""
    actual = error.actual

    if "Missing right-hand operand after" in message:
        operator = message.rsplit("'", 2)[1]
        return DiagnosisRecord(
            category="missing-operand-after-operator",
            explanation=(
                f"The '{operator}' operator is missing its "
                "right-hand operand. Add an expression after it."
            ),
            line=error.line,
            column=error.column,
            offending_token=token,
            expected="right-hand operand",
            actual=actual,
            root_cause=(
                f"The expression ends with '{operator}' before "
                "the semicolon, so the operator has no right-hand operand."
            ),
            confidence=0.95,
        )

    return DiagnosisRecord(
        category="missing-operand-or-operator",
        explanation="An expression is missing the required operand or operator.",
        line=error.line,
        column=error.column,
        offending_token=token,
        expected="expression",
        actual=actual,
        root_cause=(
            "The parser encountered a token that cannot begin "
            "or continue a valid expression."
        ),
        confidence=0.91,
    )



def _rule_unexpected_token(error: Any) -> Optional[DiagnosisRecord]:
    if not isinstance(error, ParseDiagnostic):
        return None
    if error.category == "unexpected-token":
        return DiagnosisRecord(
            category="unexpected-token",
            explanation="The token does not fit the grammar at this position.",
            line=error.line,
            column=error.column,
            offending_token=_token_from_error(error),
            expected=error.expected,
            actual=error.actual,
            root_cause="The parser is in a context where this token cannot legally appear.",
            confidence=0.88,
        )
    return None


def _rule_invalid_declaration(error: Any) -> Optional[DiagnosisRecord]:
    if not isinstance(error, ParseDiagnostic):
        return None
    if error.category == "invalid-statement" or "identifier after type" in (error.message or ""):
        return DiagnosisRecord(
            category="invalid-declaration-or-assignment",
            explanation="The declaration or assignment statement is malformed.",
            line=error.line,
            column=error.column,
            offending_token=_token_from_error(error),
            expected=error.expected,
            actual=error.actual,
            root_cause="A variable declaration or assignment is missing a name, initializer, or required operator.",
            confidence=0.9,
        )
    return None


def _rule_lexical_error(error: Any) -> Optional[DiagnosisRecord]:
    if not isinstance(error, LexicalError):
        return None
    code = error.code.value if hasattr(error.code, "value") else str(error.code)
    if code == "INVALID_CHARACTER":
        category = "invalid-or-unrecognized-character"
        root = "The lexer encountered a character that is not valid in the current language subset."
        expected = "valid identifier, number, string, operator, or delimiter"
    elif code in {"INVALID_IDENTIFIER", "MALFORMED_NUMBER"}:
        category = "malformed-token"
        root = "The token was started but does not match the language rules for identifiers or numeric literals."
        expected = "identifier or numeric literal"
    else:
        category = "other-lexical-error"
        root = "The lexer found a malformed token or unterminated construct."
        expected = "valid token form"
    return DiagnosisRecord(
        category=category,
        explanation=error.message,
        line=error.line,
        column=error.column,
        offending_token=error.lexeme or None,
        expected=expected,
        actual=error.lexeme,
        root_cause=root,
        confidence=0.95,
    )


DEFAULT_RULES: Iterable[DiagnosisRule] = (
    DiagnosisRule("missing-semicolon", "Missing semicolon/delimiter", _rule_missing_semicolon),
    DiagnosisRule("unmatched-delimiter", "Unmatched delimiter", _rule_unmatched_delimiter),
    DiagnosisRule("missing-operand", "Missing operand", _rule_missing_operand),
    DiagnosisRule("unexpected-token", "Unexpected token", _rule_unexpected_token),
    DiagnosisRule("invalid-declaration", "Invalid declaration or assignment", _rule_invalid_declaration),
    DiagnosisRule("lexical-error", "Lexical error", _rule_lexical_error),
)


def build_default_fallback(error: Any) -> DiagnosisRecord:
    token = _token_from_error(error)
    line = getattr(error, "line", 1)
    column = getattr(error, "column", 1)
    message = getattr(error, "message", str(error))
    actual = getattr(error, "actual", None)
    expected = getattr(error, "expected", None)
    return DiagnosisRecord(
        category="other-syntax-error",
        explanation=message or "A syntax issue was detected, but the exact cause could not be determined from the available evidence.",
        line=int(line),
        column=int(column),
        offending_token=token,
        expected=expected,
        actual=actual,
        root_cause="The parser encountered a structure that does not fit the known grammar, but the precise root cause is ambiguous from the available tokens.",
        confidence=0.6,
    )


def classify_error(error: Any) -> DiagnosisRecord:
    if isinstance(error, LexicalError):
        diagnosis = _rule_lexical_error(error)
        if diagnosis is not None:
            return diagnosis
    if isinstance(error, ParseDiagnostic):
        for rule in DEFAULT_RULES:
            diagnosis = rule.predicate(error)
            if diagnosis is not None:
                return diagnosis
    return build_default_fallback(error)
