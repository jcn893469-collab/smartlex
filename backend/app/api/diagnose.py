from fastapi import APIRouter

from app.ai.gemini import get_gemini_analysis
from app.diagnosis import Diagnoser
from app.diagnosis.array_bounds import find_array_bounds_errors
from app.lexer import tokenize
from app.models.schemas import LexRequest
from app.parser.parser import parse_program

router = APIRouter(tags=["diagnosis"])


@router.post("/diagnose")
async def diagnose_source(request: LexRequest) -> dict:
    lex_result = tokenize(request.source, request.language)
    ai_analysis = await get_gemini_analysis(request.source, request.language)
    if lex_result.errors:
        diagnoses = Diagnoser().diagnose_lexical(lex_result.errors)
        return {
            "valid": False,
            "source_length": len(request.source),
            "token_count": len(lex_result.tokens),
            "diagnoses": [item.to_dict() for item in diagnoses.items],
            "deterministic_findings": [],
            "ai_analysis": ai_analysis,
            "error_count": diagnoses.error_count,
            "has_errors": diagnoses.has_errors,
            "lexical_errors": [error.to_dict() for error in lex_result.errors],
            "syntax_errors": [],
        }

    parsed = parse_program(request.source, request.language)
    diagnostics = Diagnoser().diagnose_mixed([], parsed.syntax_errors)
    diagnoses = [item.to_dict() for item in diagnostics.items]
    findings = (
        find_array_bounds_errors(request.source)
        if request.language == "c"
        else []
    )
    diagnoses.extend(findings)
    return {
        "valid": parsed.valid and not findings,
        "source_length": len(request.source),
        "token_count": parsed.token_count,
        "diagnoses": diagnoses,
        "deterministic_findings": findings,
        "ai_analysis": ai_analysis,
        "error_count": len(diagnoses),
        "has_errors": bool(diagnoses),
        "lexical_errors": parsed.lexical_errors,
        "syntax_errors": [error.to_dict() for error in parsed.syntax_errors],
    }
