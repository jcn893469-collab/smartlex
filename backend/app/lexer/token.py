from dataclasses import dataclass
from enum import Enum


class TokenType(str, Enum):
    KEYWORD = "KEYWORD"
    IDENTIFIER = "IDENTIFIER"
    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    STRING = "STRING"
    CHAR = "CHAR"
    OPERATOR = "OPERATOR"
    DELIMITER = "DELIMITER"


KEYWORDS = frozenset(
    {
        "int",
        "float",
        "double",
        "char",
        "void",
        "if",
        "else",
        "while",
        "for",
        "do",
        "return",
        "break",
        "continue",
    }
)


@dataclass(frozen=True)
class Token:
    type: TokenType
    lexeme: str
    line: int
    column: int

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "lexeme": self.lexeme,
            "line": self.line,
            "column": self.column,
        }
