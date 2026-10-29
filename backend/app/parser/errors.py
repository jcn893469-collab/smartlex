from dataclasses import dataclass


@dataclass(frozen=True)
class ParseDiagnostic:
    category: str
    message: str
    line: int
    column: int
    lexeme: str
    expected: str | None = None
    actual: str | None = None

    def to_dict(self) -> dict:
        return {
            "kind": "syntax",
            "category": self.category,
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "lexeme": self.lexeme,
            "expected": self.expected,
            "actual": self.actual,
        }
