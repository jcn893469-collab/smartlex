from __future__ import annotations

from typing import Any, Iterable, List, Optional

from app.diagnosis.rules import DiagnosisRecord


def _suggestion_payload(
    diagnosis: DiagnosisRecord,
    rule_id: str,
    action: str,
    explanation: str,
    suggested_text: Optional[str] = None,
    requires_review: bool = False,
    original_text: Optional[str] = None,
) -> dict:
    original = original_text if original_text is not None else diagnosis.offending_token
    return {
        "error_id": f"{diagnosis.category}:{diagnosis.line}:{diagnosis.column}:{diagnosis.offending_token or 'unknown'}",
        "rule_id": rule_id,
        "action": action,
        "line": diagnosis.line,
        "column": diagnosis.column,
        "original_text": original,
        "suggested_text": suggested_text,
        "explanation": explanation,
        "confidence": round(float(diagnosis.confidence), 2),
        "requires_review": bool(requires_review),
    }


def make_missing_semicolon_suggestion(diagnosis: DiagnosisRecord) -> Optional[dict]:
    if diagnosis.category != "missing-semicolon-or-delimiter":
        return None
    return _suggestion_payload(
        diagnosis,
        rule_id="missing-semicolon",
        action="insert",
        explanation="Insert a semicolon to terminate the current statement before the next token or end of input.",
        suggested_text=";",
        requires_review=False,
    )


def make_missing_closing_delimiter_suggestion(diagnosis: DiagnosisRecord) -> Optional[dict]:
    expected = diagnosis.expected if diagnosis.expected else ""
    if diagnosis.category != "unmatched-delimiter" or not expected:
        return None
    return _suggestion_payload(
        diagnosis,
        rule_id="missing-closing-delimiter",
        action="insert",
        explanation=f"Insert the missing closing delimiter '{expected}' to close the current block or expression.",
        suggested_text=expected,
        requires_review=False,
    )


def make_unexpected_token_suggestion(diagnosis: DiagnosisRecord) -> Optional[dict]:
    if diagnosis.category != "unexpected-token":
        return None
    offending = diagnosis.offending_token or diagnosis.actual or ""
    if offending in {"*", "/", "%", "+", "-", "&&", "||", "==", "!="}:
        return _suggestion_payload(
            diagnosis,
            rule_id="unexpected-token",
            action="remove",
            explanation="Remove the extra or misplaced operator. Verify the expression operator matches the intended arithmetic or logical operation.",
            suggested_text="",
            original_text=offending,
            requires_review=True,
        )
    return _suggestion_payload(
        diagnosis,
        rule_id="unexpected-token",
        action="replace",
        explanation="Replace the unexpected token with a valid token for this grammar position.",
        suggested_text="",
        original_text=offending,
        requires_review=True,
    )


def make_invalid_character_suggestion(diagnosis: DiagnosisRecord) -> Optional[dict]:
    if diagnosis.category != "invalid-or-unrecognized-character":
        return None
    offending = diagnosis.offending_token or diagnosis.actual or ""
    return _suggestion_payload(
        diagnosis,
        rule_id="invalid-character",
        action="remove",
        explanation="Remove or replace the invalid character with a valid token separator or operator.",
        suggested_text="",
        original_text=offending,
        requires_review=False,
    )




def make_missing_operand_suggestion(diagnosis: DiagnosisRecord) -> Optional[dict]:
    supported_categories = {
        "missing-operand-or-operator",
        "missing-assignment-value",
        "missing-operand-after-operator",
    }

    if diagnosis.category not in supported_categories:
        return None

    offending = diagnosis.offending_token or diagnosis.actual or ""

    # An operator has no right-hand operand.
    if diagnosis.category == "missing-operand-after-operator":
        return _suggestion_payload(
            diagnosis,
            rule_id="missing-operand",
            action="insert_before",
            explanation=diagnosis.explanation,
            suggested_text="<expression>",
            original_text=offending or ";",
            requires_review=True,
        )

    return _suggestion_payload(
        diagnosis,
        rule_id="missing-operand",
        action="explanatory_only",
        explanation=(
            "A value or expression may be missing. "
            "Review the surrounding expression and enter "
            "the appropriate value, variable, or expression."
        ),
        suggested_text=None,
        requires_review=True,
    )




def make_invalid_declaration_suggestion(diagnosis: DiagnosisRecord) -> Optional[dict]:
    if diagnosis.category != "invalid-declaration-or-assignment":
        return None
    return _suggestion_payload(
        diagnosis,
        rule_id="invalid-declaration",
        action="explanatory_only",
        explanation="Review the declaration or assignment syntax: confirm the type, identifier, and assignment operator are in the correct order.",
        suggested_text=None,
        requires_review=True,
    )


def make_other_suggestion(diagnosis: DiagnosisRecord) -> Optional[dict]:
    if diagnosis.category not in {"other-syntax-error", "malformed-token", "other-lexical-error", "other-syntax-error"}:
        return None
    return _suggestion_payload(
        diagnosis,
        rule_id="other-error",
        action="explanatory_only",
        explanation="The root cause is ambiguous from the current diagnostics. Review the surrounding statement and token sequence before making a fix.",
        suggested_text=None,
        requires_review=True,
    )


DEFAULT_SUGGESTION_RULES: Iterable[Any] = (
    make_missing_semicolon_suggestion,
    make_missing_closing_delimiter_suggestion,
    make_unexpected_token_suggestion,
    make_invalid_character_suggestion,
    make_missing_operand_suggestion,
    make_invalid_declaration_suggestion,
    make_other_suggestion,
)
