from fastapi import APIRouter

from app.lexer import tokenize
from app.models.schemas import LexRequest, LexResponse

router = APIRouter(tags=["lexer"])


@router.post("/lex", response_model=LexResponse)
def lex_source(request: LexRequest) -> dict:
    return tokenize(request.source, request.language).to_dict()
