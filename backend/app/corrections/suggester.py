
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Sequence

from app.diagnosis.rules import DiagnosisRecord, DiagnosisResult
from app.corrections.rules import DEFAULT_SUGGESTION_RULES


@dataclass(frozen=True)
class Suggestion:
    error_id: str
    rule_id: str
    action: str
    line: int
    column: int
    original_text: Optional[str]
    suggested_text: Optional[str]
    explanation: str
    confidence: float
    requires_review: bool

    def to_dict(self) -> dict:
        return {
            "error_id": self.error_id,
            "rule_id": self.rule_id,
            "action": self.action,
            "line": self.line,
            "column": self.column,
            "original_text": self.original_text,
            "suggested_text": self.suggested_text,
            "explanation": self.explanation,
            "confidence": self.confidence,
            "requires_review": self.requires_review,
        }


class SuggestionEngine:
    def suggest(
        self, diagnoses: Iterable[DiagnosisRecord]
    ) -> List[Suggestion]:
        seen = set()
        suggestions: List[Suggestion] = []

        for diagnosis in diagnoses or []:
            if diagnosis is None:
                continue

            for rule in DEFAULT_SUGGESTION_RULES:
                payload = rule(diagnosis)
                if payload is None:
                    continue

                key = (
                    payload["rule_id"],
                    payload["line"],
                    payload["column"],
                    payload["action"],
                    payload["suggested_text"],
                )

                if key in seen:
                    continue

                seen.add(key)

                suggestions.append(
                    Suggestion(
                        error_id=payload["error_id"],
                        rule_id=payload["rule_id"],
                        action=payload["action"],
                        line=payload["line"],
                        column=payload["column"],
                        original_text=payload.get("original_text"),
                        suggested_text=payload.get("suggested_text"),
                        explanation=payload["explanation"],
                        confidence=float(payload["confidence"]),
                        requires_review=bool(
                            payload["requires_review"]
                        ),
                    )
                )
                break

        return suggestions

    def suggest_with_source(
        self,
        diagnoses: Iterable[DiagnosisRecord],
        source: str,
    ) -> List[Suggestion]:
        suggestions = self.suggest(diagnoses)
        source_lines = source.splitlines()
        updated_suggestions: List[Suggestion] = []

        for suggestion in suggestions:
            if (
                suggestion.rule_id == "missing-operand"
                and suggestion.action == "insert_before"
                and 1 <= suggestion.line <= len(source_lines)
            ):
                line = source_lines[suggestion.line - 1]
                before_error = line[
                    :max(0, suggestion.column - 1)
                ].rstrip()

                # Inspect the expression after the last assignment operator.
                if "=" in before_error:
                    rhs = before_error.rsplit("=", 1)[-1].strip()
                else:
                    rhs = before_error.strip()

                # Explain the specific missing operand where possible.
                if rhs.endswith("+"):
                    explanation = (
                        "The '+' operator is missing its right-hand "
                        "operand. Add an appropriate value, variable, "
                        "or expression."
                    )
                elif rhs.endswith("-"):
                    explanation = (
                        "The '-' operator is missing its right-hand "
                        "operand. Add an appropriate value, variable, "
                        "or expression."
                    )
                elif rhs.endswith("*"):
                    explanation = (
                        "The '*' operator is missing its right-hand "
                        "operand. Add an appropriate value, variable, "
                        "or expression."
                    )
                elif rhs.endswith("/"):
                    explanation = (
                        "The '/' operator is missing its right-hand "
                        "operand. Add an appropriate value, variable, "
                        "or expression."
                    )
                elif rhs == "" and "=" in before_error:
                    explanation = (
                        "The assignment operator '=' has no value "
                        "after it. Enter an appropriate value, "
                        "variable, or expression before the semicolon."
                    )
                else:
                    explanation = (
                        "An operand is missing near this location. "
                        "Check the surrounding expression and enter "
                        "the appropriate value, variable, or expression."
                    )

                suggestion = Suggestion(
                    error_id=suggestion.error_id,
                    rule_id=suggestion.rule_id,
                    action=suggestion.action,
                    line=suggestion.line,
                    column=suggestion.column,
                    original_text=suggestion.original_text,
                    suggested_text="<expression>",
                    explanation=explanation,
                    confidence=suggestion.confidence,
                    requires_review=True,
                )

            updated_suggestions.append(suggestion)

        return updated_suggestions


def suggest_for_diagnostics(
    diagnoses: Sequence[DiagnosisRecord] | DiagnosisResult,
) -> List[Suggestion]:
    if isinstance(diagnoses, DiagnosisResult):
        items = diagnoses.items
    else:
        items = list(diagnoses or [])

    return SuggestionEngine().suggest(items)


def suggest_for_source(
    source: str, *, diagnostics: Any = None
) -> dict:
    from app.diagnosis import Diagnoser
    from app.lexer import tokenize
    from app.parser.parser import parse_program

    if diagnostics is None:
        lex_result = tokenize(source)

        if lex_result.errors:
            diagnosis_result = Diagnoser().diagnose_lexical(
                lex_result.errors
            )
            suggestions = SuggestionEngine().suggest_with_source(
                diagnosis_result.items, source
            )

            return {
                "valid": False,
                "source_length": len(source),
                "token_count": len(lex_result.tokens),
                "diagnoses": [
                    item.to_dict()
                    for item in diagnosis_result.items
                ],
                "suggestions": [
                    {
                        **item.to_dict(),
                        "corrected_source": attach_corrected_source(
                            source, item
                        ),
                    }
                    for item in suggestions
                ],
                "error_count": diagnosis_result.error_count,
                "has_errors": diagnosis_result.has_errors,
                "lexical_errors": [
                    error.to_dict()
                    for error in lex_result.errors
                ],
                "syntax_errors": [],
            }

        parsed = parse_program(source)
        diagnosis_result = Diagnoser().diagnose_syntax(
            parsed.syntax_errors
        )
        suggestions = SuggestionEngine().suggest_with_source(
            diagnosis_result.items, source
        )

        return {
            "valid": parsed.valid,
            "source_length": len(source),
            "token_count": parsed.token_count,
            "diagnoses": [
                item.to_dict()
                for item in diagnosis_result.items
            ],
            "suggestions": [
                item.to_dict() for item in suggestions
            ],
            "error_count": diagnosis_result.error_count,
            "has_errors": diagnosis_result.has_errors,
            "lexical_errors": parsed.lexical_errors,
            "syntax_errors": [
                error.to_dict()
                for error in parsed.syntax_errors
            ],
        }

    if isinstance(diagnostics, DiagnosisResult):
        items = diagnostics.items
    else:
        items = list(diagnostics or [])

    suggestions = SuggestionEngine().suggest_with_source(
        items, source
    )

    return {
        "diagnoses": [
            item.to_dict() for item in items
        ],
        "suggestions": [
            item.to_dict() for item in suggestions
        ],
        "error_count": len(items),
        "has_errors": bool(items),
    }


def attach_corrected_source(
    source: str, suggestion: Suggestion
) -> Optional[str]:
    """Build corrected source for supported delimiter insertions."""

    if suggestion.rule_id not in {
        "missing-semicolon",
        "missing-closing-delimiter",
    }:
        return None

    insertion = suggestion.suggested_text
    if not insertion:
        return None

    lines = source.splitlines(keepends=True)
    if not lines:
        return None

    line_index = suggestion.line - 1

    if line_index < 0 or line_index >= len(lines):
        return None

    line = lines[line_index]
    content = line.rstrip("\r\n")
    newline = line[len(content):]

    if suggestion.rule_id == "missing-semicolon":
        position = len(content.rstrip())
    else:
        position = max(
            0, min(suggestion.column - 1, len(content))
        )

    corrected_line = (
        content[:position]
        + insertion
        + content[position:]
        + newline
    )

    lines[line_index] = corrected_line
    return "".join(lines)
