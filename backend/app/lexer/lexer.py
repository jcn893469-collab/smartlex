
import re
from dataclasses import dataclass, field
from typing import List

from app.lexer.errors import LexicalError, LexicalErrorCode
from app.lexer.token import KEYWORDS, Token, TokenType


OPERATORS_3 = ("<<=", ">>=")

OPERATORS_2 = (
    "++", "--", "+=", "-=", "*=", "/=", "%=", "==", "!=", "<=", ">=",
    "&&", "||", "<<", ">>", "->", "&=", "|=", "^=",
)

OPERATORS_1 = frozenset("+-*/%=<>!&|^~?:")
DELIMITERS = frozenset("(){}[];,.")
VALID_ESCAPES = frozenset("ntr0\\'\"abfv")

_BAD_EXPONENT = re.compile(r"\d+(\.\d+)?[eE]")


def _is_digit(ch: str) -> bool:
    return len(ch) == 1 and "0" <= ch <= "9"


def _is_alpha(ch: str) -> bool:
    return len(ch) == 1 and ch.isascii() and (ch.isalpha() or ch == "_")


def _is_alnum(ch: str) -> bool:
    return _is_alpha(ch) or _is_digit(ch)


@dataclass
class LexResult:
    tokens: List[Token] = field(default_factory=list)
    errors: List[LexicalError] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tokens": [t.to_dict() for t in self.tokens],
            "errors": [e.to_dict() for e in self.errors],
            "token_count": len(self.tokens),
            "error_count": len(self.errors),
            "has_errors": len(self.errors) > 0,
        }


class Lexer:
    def __init__(self, source: str) -> None:
        self.source = source.replace("\r\n", "\n").replace("\r", "\n")
        self.length = len(self.source)
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens: List[Token] = []
        self.errors: List[LexicalError] = []

    # ---------- helpers ----------

    def _peek(self, offset: int = 0) -> str:
        index = self.pos + offset
        if index < self.length:
            return self.source[index]
        return ""

    def _advance(self) -> str:
        ch = self.source[self.pos]
        self.pos += 1

        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1

        return ch

    def _emit(
        self, token_type: TokenType, lexeme: str, line: int, col: int
    ) -> None:
        self.tokens.append(Token(token_type, lexeme, line, col))

    def _error(
        self,
        code: LexicalErrorCode,
        message: str,
        lexeme: str,
        line: int,
        col: int,
    ) -> None:
        self.errors.append(LexicalError(code, message, lexeme, line, col))

    def _check_escape(self, ch: str, line: int, col: int) -> None:
        if ch not in VALID_ESCAPES:
            self._error(
                LexicalErrorCode.INVALID_ESCAPE,
                f"Unknown escape sequence '\\{ch}'",
                "\\" + ch,
                line,
                col,
            )

    # ---------- main loop ----------

    def tokenize(self) -> LexResult:
        while self.pos < self.length:
            ch = self._peek()

            # Skip supported C preprocessor include directives.
            if ch == "#" and self.col == 1:
                end = self.source.find("\n", self.pos)

                if end == -1:
                    end = self.length

                directive = self.source[self.pos:end]

                if re.fullmatch(
                    r'#\s*include\s*[<"][^>\n"]+[>"]\s*',
                    directive,
                ):
                    while self.pos < self.length and self._peek() != "\n":
                        self._advance()
                    continue

            if ch in " \t\n\f\v":
                self._advance()
            elif ch == "/" and self._peek(1) == "/":
                self._skip_line_comment()
            elif ch == "/" and self._peek(1) == "*":
                self._skip_block_comment()
            elif _is_alpha(ch):
                self._scan_word()
            elif _is_digit(ch):
                self._scan_number()
            elif ch == '"':
                self._scan_string()
            elif ch == "'":
                self._scan_char()
            else:
                self._scan_symbol()

        return LexResult(tokens=self.tokens, errors=self.errors)

    # ---------- comments ----------

    def _skip_line_comment(self) -> None:
        while self.pos < self.length and self._peek() != "\n":
            self._advance()

    def _skip_block_comment(self) -> None:
        line, col = self.line, self.col

        self._advance()
        self._advance()

        while self.pos < self.length:
            if self._peek() == "*" and self._peek(1) == "/":
                self._advance()
                self._advance()
                return

            self._advance()

        self._error(
            LexicalErrorCode.UNTERMINATED_COMMENT,
            "Comment starting with '/*' is never closed with '*/'",
            "/*",
            line,
            col,
        )

    # ---------- words ----------

    def _scan_word(self) -> None:
        line, col = self.line, self.col
        start = self.pos

        while _is_alnum(self._peek()):
            self._advance()

        lexeme = self.source[start:self.pos]
        token_type = (
            TokenType.KEYWORD if lexeme in KEYWORDS else TokenType.IDENTIFIER
        )

        self._emit(token_type, lexeme, line, col)

    # ---------- numbers ----------

    def _scan_number(self) -> None:
        line, col = self.line, self.col
        start = self.pos
        is_float = False

        while _is_digit(self._peek()):
            self._advance()

        if self._peek() == "." and _is_digit(self._peek(1)):
            is_float = True
            self._advance()

            while _is_digit(self._peek()):
                self._advance()

        if self._peek() in ("e", "E"):
            nxt = self._peek(1)

            if _is_digit(nxt) or (
                nxt in ("+", "-") and _is_digit(self._peek(2))
            ):
                is_float = True
                self._advance()

                if self._peek() in ("+", "-"):
                    self._advance()

                while _is_digit(self._peek()):
                    self._advance()

            elif nxt in ("+", "-"):
                self._advance()
                self._advance()

                lexeme = self.source[start:self.pos]

                self._error(
                    LexicalErrorCode.MALFORMED_NUMBER,
                    f"Malformed number '{lexeme}': exponent has no digits",
                    lexeme,
                    line,
                    col,
                )
                return

        trailing = False

        while _is_alnum(self._peek()) or (
            self._peek() == "." and _is_digit(self._peek(1))
        ):
            trailing = True
            self._advance()

        lexeme = self.source[start:self.pos]

        if trailing:
            if is_float or "." in lexeme or _BAD_EXPONENT.fullmatch(lexeme):
                self._error(
                    LexicalErrorCode.MALFORMED_NUMBER,
                    f"Malformed number '{lexeme}'",
                    lexeme,
                    line,
                    col,
                )
            else:
                self._error(
                    LexicalErrorCode.INVALID_IDENTIFIER,
                    f"'{lexeme}' is not a valid identifier: "
                    "identifiers cannot start with a digit",
                    lexeme,
                    line,
                    col,
                )
            return

        token_type = TokenType.FLOAT if is_float else TokenType.INTEGER
        self._emit(token_type, lexeme, line, col)

    # ---------- strings and chars ----------

    def _scan_string(self) -> None:
        line, col = self.line, self.col
        start = self.pos

        self._advance()
        terminated = False

        while self.pos < self.length:
            ch = self._peek()

            if ch == "\n":
                break

            if ch == '"':
                self._advance()
                terminated = True
                break

            if ch == "\\":
                esc_line, esc_col = self.line, self.col
                self._advance()

                nxt = self._peek()

                if nxt == "" or nxt == "\n":
                    break

                self._advance()
                self._check_escape(nxt, esc_line, esc_col)
                continue

            self._advance()

        lexeme = self.source[start:self.pos]

        if terminated:
            self._emit(TokenType.STRING, lexeme, line, col)
        else:
            self._error(
                LexicalErrorCode.UNTERMINATED_STRING,
                "String literal is missing its closing double quote",
                lexeme,
                line,
                col,
            )

    def _scan_char(self) -> None:
        line, col = self.line, self.col
        start = self.pos

        self._advance()
        terminated = False
        count = 0

        while self.pos < self.length:
            ch = self._peek()

            if ch == "\n":
                break

            if ch == "'":
                self._advance()
                terminated = True
                break

            if ch == "\\":
                esc_line, esc_col = self.line, self.col
                self._advance()

                nxt = self._peek()

                if nxt == "" or nxt == "\n":
                    break

                self._advance()
                self._check_escape(nxt, esc_line, esc_col)
                count += 1
                continue

            self._advance()
            count += 1

        lexeme = self.source[start:self.pos]

        if not terminated:
            self._error(
                LexicalErrorCode.UNTERMINATED_CHAR,
                "Character literal is missing its closing single quote",
                lexeme,
                line,
                col,
            )
        elif count == 0:
            self._error(
                LexicalErrorCode.EMPTY_CHAR_LITERAL,
                "Character literal is empty",
                lexeme,
                line,
                col,
            )
        elif count > 1:
            self._error(
                LexicalErrorCode.MULTI_CHAR_LITERAL,
                f"Character literal {lexeme} contains more than one character",
                lexeme,
                line,
                col,
            )
        else:
            self._emit(TokenType.CHAR, lexeme, line, col)

    # ---------- operators, delimiters, invalid characters ----------

    def _scan_symbol(self) -> None:
        line, col = self.line, self.col
        ch = self._peek()

        for width, group in ((3, OPERATORS_3), (2, OPERATORS_2)):
            candidate = self.source[self.pos:self.pos + width]

            if len(candidate) == width and candidate in group:
                for _ in range(width):
                    self._advance()

                self._emit(TokenType.OPERATOR, candidate, line, col)
                return

        if ch in OPERATORS_1:
            self._advance()
            self._emit(TokenType.OPERATOR, ch, line, col)
            return

        if ch in DELIMITERS:
            self._advance()
            self._emit(TokenType.DELIMITER, ch, line, col)
            return

        self._advance()
        self._error(
            LexicalErrorCode.INVALID_CHARACTER,
            f"Invalid character {ch!r} is not part of the supported language",
            ch,
            line,
            col,
        )


def tokenize(source: str, language: str = "c") -> LexResult:
    if language in {"lex", "flex"}:
        from app.lexer.flex import tokenize_flex

        return tokenize_flex(source)
    return Lexer(source).tokenize()
