from fastapi import APIRouter

from app.lexer import tokenize
from app.diagnosis.array_bounds import find_array_bounds_errors
from app.models.schemas import LexRequest
from app.parser.parser import parse_program

router = APIRouter(tags=["parser"])


@router.post("/parse")
def parse_source(request: LexRequest) -> dict:
    lex_result = tokenize(request.source, request.language)
    if lex_result.errors:
        return {
            "valid": False,
            "token_count": len(lex_result.tokens),
            "statement_count": 0,
            "diagnostics": [error.to_dict() for error in lex_result.errors],
            "syntax_errors": [],
            "lexical_errors": [error.to_dict() for error in lex_result.errors],
            "error_count": len(lex_result.errors),
            "has_errors": True,
            "statements": [],
        }
    parsed = parse_program(request.source, request.language)
    result = parsed.to_dict()
    semantic_errors = (
        find_array_bounds_errors(request.source)
        if request.language == "c"
        else []
    )
    result["semantic_errors"] = semantic_errors
    result["valid"] = result["valid"] and not semantic_errors
    result["error_count"] += len(semantic_errors)
    result["has_errors"] = result["has_errors"] or bool(semantic_errors)
    return result
