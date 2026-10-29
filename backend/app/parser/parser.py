from dataclasses import dataclass, field
from typing import Any, List, Optional

from app.lexer import TokenType, tokenize
from app.lexer.token import Token
from app.parser.errors import ParseDiagnostic

PRIMITIVE_TYPES = {"int", "float", "double", "char", "bool", "void"}


@dataclass
class ParseResult:
    valid: bool
    statements: List[dict] = field(default_factory=list)
    syntax_errors: List[ParseDiagnostic] = field(default_factory=list)
    lexical_errors: List[dict] = field(default_factory=list)
    token_count: int = 0

    def to_dict(self) -> dict:
        diagnostics = [error.to_dict() for error in self.syntax_errors]
        diagnostics.extend(self.lexical_errors)
        return {
            "valid": self.valid,
            "token_count": self.token_count,
            "statement_count": len(self.statements),
            "diagnostics": diagnostics,
            "syntax_errors": [error.to_dict() for error in self.syntax_errors],
            "lexical_errors": self.lexical_errors,
            "error_count": len(self.syntax_errors) + len(self.lexical_errors),
            "has_errors": bool(self.syntax_errors or self.lexical_errors),
            "statements": self.statements,
        }


class Parser:
    def __init__(self, tokens: List[Token]) -> None:
        self.tokens = tokens
        self.index = 0
        self.syntax_errors: List[ParseDiagnostic] = []
        self.statements: List[dict] = []

    def parse(self) -> ParseResult:
        while not self._at_end():
            start_index = self.index
            token = self._current()
            if token.lexeme == "}":
                self._error(
                    "unexpected-token",
                    "Unexpected '}' in program",
                    token,
                    expected="statement",
                    actual="}",
                )
                self._advance()
                continue
            statement = self._parse_statement()
            if statement is not None:
                self.statements.append(statement)
            if self.index == start_index:
                self._error(
                    "unexpected-token",
                    f"Unexpected token '{token.lexeme}'",
                    token,
                    expected="statement",
                    actual=token.lexeme,
                )
                self._advance()
        return ParseResult(
            valid=not self.syntax_errors,
            statements=self.statements,
            syntax_errors=self.syntax_errors,
            lexical_errors=[],
            token_count=len(self.tokens),
        )

    def _current(self) -> Token:
        if self.index < len(self.tokens):
            return self.tokens[self.index]
        return self._eof_token()

    def _peek(self, offset: int = 0) -> Token:
        pos = self.index + offset
        if pos < len(self.tokens):
            return self.tokens[pos]
        return self._eof_token()

    def _advance(self) -> Token:
        token = self._current()
        if not self._at_end():
            self.index += 1
        return token

    def _at_end(self) -> bool:
        return self.index >= len(self.tokens)

    def _eof_token(self) -> Token:
        if self.tokens:
            last = self.tokens[-1]
            return Token(TokenType.DELIMITER, "EOF", last.line, last.column)
        return Token(TokenType.DELIMITER, "EOF", 1, 1)

    def _match(self, *lexemes: str) -> bool:
        if self._current().lexeme in lexemes:
            self._advance()
            return True
        return False

    def _match_keyword(self, *keywords: str) -> bool:
        token = self._current()
        if token.type == TokenType.KEYWORD and token.lexeme in keywords:
            self._advance()
            return True
        if token.type == TokenType.IDENTIFIER and token.lexeme in keywords:
            self._advance()
            return True
        return False

    def _expect(self, expected: str, message: str) -> Optional[Token]:
        token = self._current()
        if token.lexeme == expected:
            return self._advance()
        self._error(
            "missing-token",
            message,
            token,
            expected=expected,
            actual=token.lexeme if token.lexeme else "EOF",
        )
        return None

    def _error(
        self,
        category: str,
        message: str,
        token: Optional[Token],
        expected: Optional[str] = None,
        actual: Optional[str] = None,
    ) -> None:
        if token is None:
            token = self._eof_token()
        self.syntax_errors.append(
            ParseDiagnostic(
                category=category,
                message=message,
                line=token.line,
                column=token.column,
                lexeme=token.lexeme,
                expected=expected,
                actual=actual,
            )
        )

    def _skip_to(self, stop_tokens: set[str]) -> None:
        while not self._at_end():
            if self._current().lexeme in stop_tokens:
                return
            self._advance()

    def _parse_statement(self) -> Optional[dict]:
        token = self._current()

        if self._match_keyword("if"):
            return self._parse_if_statement()
        if self._match_keyword("while"):
            return self._parse_while_statement()
        if self._match_keyword("for"):
            return self._parse_for_statement()
        if self._match_keyword("return"):
            value = self._parse_expression() if self._current().lexeme not in {";", "}"} else None
            self._expect(";", "Expected ';' after return statement")
            return {"kind": "return", "value": value}
        if self._match_keyword("print"):
            self._expect("(", "Expected '(' after print")
            value = self._parse_expression()
            self._expect(")", "Expected ')' after print argument")
            self._expect(";", "Expected ';' after print statement")
            return {"kind": "print", "argument": value}
        if self._match("{"):
            return self._parse_block_statement()
        if (
            self._is_type_name(token)
            and self._peek(1).type == TokenType.IDENTIFIER
            and self._peek(2).lexeme == "("
        ):
            return self._parse_function_definition()
        if self._is_type_name(token):
            return self._parse_declaration_statement()
        if token.type == TokenType.IDENTIFIER and self._peek(1).lexeme in {"=", "["}:
            return self._parse_assignment_statement()
        if token.lexeme == "}":
            return None
        if self._at_end():
            return None

        if token.lexeme == ";":
            self._advance()
            return {"kind": "empty_statement"}

        expr = self._parse_expression()
        self._expect(";", "Expected ';' after statement")
        return {"kind": "expression", "expression": expr}

    def _parse_function_definition(self) -> dict:
        return_type = self._advance().lexeme
        name = self._advance().lexeme

        self._expect("(", "Expected '(' after function name")

        parameters = []

        if self._current().lexeme == "void" and self._peek(1).lexeme == ")":
            self._advance()
        elif self._current().lexeme != ")":
            while not self._at_end():
                if not self._is_type_name(self._current()):
                    self._error(
                        "invalid-parameter",
                        "Expected parameter type",
                        self._current(),
                        expected="type",
                        actual=self._current().lexeme,
                    )
                    break

                param_type = self._advance().lexeme
                param_name = self._current()

                if param_name.type != TokenType.IDENTIFIER:
                    self._error(
                        "invalid-parameter",
                        "Expected parameter name",
                        param_name,
                        expected="identifier",
                        actual=param_name.lexeme,
                    )
                    break

                self._advance()
                parameters.append({
                    "type": param_type,
                    "name": param_name.lexeme,
                })

                if not self._match(","):
                    break

        self._expect(")", "Expected ')' after function parameters")
        self._expect("{", "Expected '{' to begin function body")

        body = self._parse_block_statement()

        return {
            "kind": "function",
            "return_type": return_type,
            "name": name,
            "parameters": parameters,
            "body": body,
        }

    def _parse_block_statement(self) -> dict:
        statements: List[dict] = []
        while not self._at_end():
            if self._current().lexeme == "}":
                self._advance()
                return {"kind": "block", "statements": statements}
            statement = self._parse_statement()
            if statement is not None:
                statements.append(statement)
        self._error(
            "missing-token",
            "Expected '}' to close block",
            self._current(),
            expected="}",
            actual=self._current().lexeme if self._current().lexeme else "EOF",
        )
        return {"kind": "block", "statements": statements}

    def _parse_if_statement(self) -> dict:
        self._expect("(", "Expected '(' after if")
        condition = self._parse_expression()
        self._expect(")", "Expected ')' after if condition")
        then_branch = self._parse_statement()
        else_branch = None
        if self._match_keyword("else"):
            else_branch = self._parse_statement()
        return {"kind": "if", "condition": condition, "then": then_branch, "else": else_branch}

    def _parse_while_statement(self) -> dict:
        self._expect("(", "Expected '(' after while")
        condition = self._parse_expression()
        self._expect(")", "Expected ')' after while condition")
        body = self._parse_statement()
        return {"kind": "while", "condition": condition, "body": body}

    def _parse_for_statement(self) -> dict:
        self._expect("(", "Expected '(' after for")
        init = None
        if not self._match(";"):
            if self._current().type == TokenType.IDENTIFIER and self._peek(1).lexeme == "=":
                init = self._parse_assignment_statement(consume_terminator=False)
            elif self._is_type_name(self._current()):
                init = self._parse_declaration_statement(consume_terminator=False)
            else:
                init = {"kind": "expression", "expression": self._parse_expression()}
            self._expect(";", "Expected ';' after for initializer")

        condition = None
        if not self._match(";"):
            condition = self._parse_expression()
            self._expect(";", "Expected ';' after for condition")

        update = None
        if not self._match(")"):
            update = {"kind": "expression", "expression": self._parse_expression()}
            self._expect(")", "Expected ')' after for update")

        body = self._parse_statement()
        return {"kind": "for", "init": init, "condition": condition, "update": update, "body": body}

    def _parse_declaration_statement(self, *, consume_terminator: bool = True) -> dict:
        type_name = self._advance().lexeme
        name_token = self._current()
        if name_token.type != TokenType.IDENTIFIER:
            self._error(
                "invalid-statement",
                f"Expected identifier after type '{type_name}'",
                name_token,
                expected="identifier",
                actual=name_token.lexeme if name_token.lexeme else "EOF",
            )
            self._skip_to({";", "}"})
            if consume_terminator and self._current().lexeme == ";":
                self._advance()
            return {"kind": "declaration", "type": type_name, "name": None, "initializer": None}

        name = self._advance().lexeme
        array_size = None
        if self._match("["):
            array_size = self._parse_expression()
            self._expect("]", "Expected ']' after array size")
        initializer = None
        if self._match("="):
            initializer = self._parse_expression()
        if consume_terminator:
            self._expect(";", "Expected ';' after declaration")
        return {
            "kind": "declaration",
            "type": type_name,
            "name": name,
            "array_size": array_size,
            "initializer": initializer,
        }

    def _parse_assignment_statement(self, *, consume_terminator: bool = True) -> dict:
        name = self._advance().lexeme
        index = None
        if self._match("["):
            index = self._parse_expression()
            self._expect("]", "Expected ']' after array index")
        self._expect("=", "Expected '=' in assignment")
        value = self._parse_expression()
        if consume_terminator:
            self._expect(";", "Expected ';' after assignment")
        if index is not None:
            return {"kind": "array_assignment", "target": name, "index": index, "value": value}
        return {"kind": "assignment", "target": name, "value": value}

    def _is_type_name(self, token: Token) -> bool:
        return token.type in {TokenType.KEYWORD, TokenType.IDENTIFIER} and token.lexeme in PRIMITIVE_TYPES

    def _parse_expression(self) -> Any:
        return self._parse_logical_or()

    def _parse_logical_or(self) -> Any:
        left = self._parse_logical_and()
        while self._match("||"):
            operator = self.tokens[self.index - 1]
            right = self._parse_logical_and()
            left = {"kind": "binary", "operator": operator.lexeme, "left": left, "right": right}
        return left

    def _parse_logical_and(self) -> Any:
        left = self._parse_equality()
        while self._match("&&"):
            operator = self.tokens[self.index - 1]
            right = self._parse_equality()
            left = {"kind": "binary", "operator": operator.lexeme, "left": left, "right": right}
        return left

    def _parse_equality(self) -> Any:
        left = self._parse_relational()
        while self._current().lexeme in {"==", "!="}:
            operator = self._advance()
            right = self._parse_relational()
            left = {"kind": "binary", "operator": operator.lexeme, "left": left, "right": right}
        return left

    def _parse_relational(self) -> Any:
        left = self._parse_additive()
        while self._current().lexeme in {"<", "<=", ">", ">="}:
            operator = self._advance()
            right = self._parse_additive()
            left = {"kind": "binary", "operator": operator.lexeme, "left": left, "right": right}
        return left

    def _parse_additive(self) -> Any:
        left = self._parse_multiplicative()
        while self._current().lexeme in {"+", "-"}:
            operator = self._advance()
            right = self._parse_multiplicative()
            left = {"kind": "binary", "operator": operator.lexeme, "left": left, "right": right}
        return left

    def _parse_multiplicative(self) -> Any:
        left = self._parse_unary()
        while self._current().lexeme in {"*", "/", "%"}:
            operator = self._advance()
            right = self._parse_unary()
            left = {"kind": "binary", "operator": operator.lexeme, "left": left, "right": right}
        return left

    def _parse_unary(self) -> Any:
        if self._current().lexeme in {"+", "-", "!"}:
            operator = self._advance()
            operand = self._parse_unary()
            return {"kind": "unary", "operator": operator.lexeme, "operand": operand}
        return self._parse_primary()

    def _parse_primary(self) -> Any:
        token = self._current()

        if token.type in {TokenType.INTEGER, TokenType.FLOAT, TokenType.STRING, TokenType.CHAR}:
            self._advance()
            return {"kind": "literal", "value": token.lexeme, "token_type": token.type.value}
        if token.type == TokenType.IDENTIFIER:
            self._advance()
            if self._match("["):
                index = self._parse_expression()
                self._expect("]", "Expected ']' after array index")
                return {"kind": "array_access", "name": token.lexeme, "index": index}
            if self._match("("):
                args: List[Any] = []
                if not self._match(")"):
                    while True:
                        args.append(self._parse_expression())
                        if not self._match(","):
                            break
                    self._expect(")", "Expected ')' after function argument list")
                return {"kind": "call", "name": token.lexeme, "args": args}
            return {"kind": "identifier", "name": token.lexeme}
        if self._match("("):
            expr = self._parse_expression()
            self._expect(")", "Expected ')' to close expression")
            return expr
        if token.lexeme in {"true", "false"}:
            self._advance()
            return {"kind": "literal", "value": token.lexeme, "token_type": "BOOLEAN"}

        
        if token.lexeme in {";", ")", "}", ","}:
            previous = self.tokens[self.index - 1] if self.index > 0 else None
            previous_lexeme = previous.lexeme if previous else ""

            if token.lexeme == ";" and previous_lexeme == "=":
                message = "Missing assignment value after '='"
            elif token.lexeme == ";" and previous_lexeme in {
                "+", "-", "*", "/", "%"
            }:
                message = f"Missing right-hand operand after '{previous_lexeme}'"
            else:
                message = "Missing operand in expression"

            self._error(
                "missing-operand",
                message,
                token,
                expected="expression",
                actual=token.lexeme,
            )
            if token.lexeme in {";", ")", "}"}:
                return {"kind": "error", "value": None}
            self._advance()
            return {"kind": "error", "value": None}

        self._error(
            "unexpected-token",
            f"Unexpected token '{token.lexeme}' in expression",
            token,
            expected="expression",
            actual=token.lexeme,
        )
        if not self._at_end():
            self._advance()
        return {"kind": "error", "value": None}



def parse_program(source: str, language: str = "c") -> ParseResult:
    token_result = tokenize(source, language)
    if token_result.errors:
        return ParseResult(
            valid=False,
            statements=[],
            syntax_errors=[],
            lexical_errors=[error.to_dict() for error in token_result.errors],
            token_count=len(token_result.tokens),
        )

    if language in {"lex", "flex"}:
        from app.lexer.flex import flex_syntax_diagnostics

        syntax_errors = [
            ParseDiagnostic(
                category=item["category"],
                message=item["message"],
                line=item["line"],
                column=item["column"],
                lexeme=item["lexeme"],
                expected=item.get("expected"),
                actual=item.get("actual"),
            )
            for item in flex_syntax_diagnostics(source)
        ]
        return ParseResult(
            valid=not syntax_errors,
            statements=[{"kind": "flex_specification"}] if source.strip() else [],
            syntax_errors=syntax_errors,
            lexical_errors=[],
            token_count=len(token_result.tokens),
        )

    parser = Parser(token_result.tokens)
    try:
        result = parser.parse()
    except RecursionError:
        token = parser._current()
        diagnostic = ParseDiagnostic(
            category="nesting-limit",
            message="Source nesting is too deep for the supported parser limit",
            line=token.line,
            column=token.column,
            lexeme=token.lexeme,
            expected="shallower expression or block nesting",
            actual=token.lexeme or "EOF",
        )
        return ParseResult(
            valid=False,
            statements=[],
            syntax_errors=[diagnostic],
            lexical_errors=[],
            token_count=len(token_result.tokens),
        )
    result.lexical_errors = []
    return result
