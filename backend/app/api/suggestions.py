
from fastapi import APIRouter

from app.ai.gemini import get_gemini_analysis
from app.diagnosis.array_bounds import find_array_bounds_errors
from app.diagnosis import Diagnoser
from app.lexer import tokenize
from app.models.schemas import LexRequest
from app.parser.parser import parse_program
from app.corrections.suggester import SuggestionEngine

router = APIRouter(tags=["suggestions"])


@router.post("/suggestions")
async def suggest_source(request: LexRequest) -> dict:
    lex_result = tokenize(request.source, request.language)
    ai_analysis = await get_gemini_analysis(request.source, request.language)

    if lex_result.errors:
        diagnosis_result = Diagnoser().diagnose_lexical(
            lex_result.errors
        )

        suggestions = SuggestionEngine().suggest_with_source(
            diagnosis_result.items,
            request.source,
        )

        return {
            "valid": False,
            "source_length": len(request.source),
            "token_count": len(lex_result.tokens),
            "diagnoses": [
                item.to_dict()
                for item in diagnosis_result.items
            ],
            "ai_analysis": ai_analysis,
            "suggestions": [
                item.to_dict()
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

    parsed = parse_program(request.source, request.language)

    diagnosis_result = Diagnoser().diagnose_syntax(
        parsed.syntax_errors
    )

    suggestions = SuggestionEngine().suggest_with_source(
        diagnosis_result.items,
        request.source,
    )
    findings = (
        find_array_bounds_errors(request.source)
        if request.language == "c"
        else []
    )

    return {
        "valid": parsed.valid and not findings,
        "source_length": len(request.source),
        "token_count": parsed.token_count,
        "diagnoses": [
            item.to_dict()
            for item in diagnosis_result.items
        ] + findings,
        "deterministic_findings": findings,
        "ai_analysis": ai_analysis,
        "suggestions": [
            item.to_dict()
            for item in suggestions
        ],
        "error_count": diagnosis_result.error_count + len(findings),
        "has_errors": diagnosis_result.has_errors or bool(findings),
        "lexical_errors": parsed.lexical_errors,
        "syntax_errors": [
            error.to_dict()
            for error in parsed.syntax_errors
        ],
    }
