from dataclasses import dataclass
from enum import Enum


class LexicalErrorCode(str, Enum):
    INVALID_CHARACTER = "INVALID_CHARACTER"
    INVALID_IDENTIFIER = "INVALID_IDENTIFIER"
    MALFORMED_NUMBER = "MALFORMED_NUMBER"
    UNTERMINATED_STRING = "UNTERMINATED_STRING"
    UNTERMINATED_CHAR = "UNTERMINATED_CHAR"
    EMPTY_CHAR_LITERAL = "EMPTY_CHAR_LITERAL"
    MULTI_CHAR_LITERAL = "MULTI_CHAR_LITERAL"
    UNTERMINATED_COMMENT = "UNTERMINATED_COMMENT"
    INVALID_ESCAPE = "INVALID_ESCAPE"


@dataclass(frozen=True)
class LexicalError:
    code: LexicalErrorCode
    message: str
    lexeme: str
    line: int
    column: int

    def to_dict(self) -> dict:
        return {
            "kind": "lexical",
            "code": self.code.value,
            "message": self.message,
            "lexeme": self.lexeme,
            "line": self.line,
            "column": self.column,
        }
