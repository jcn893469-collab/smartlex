from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field


class LexRequest(BaseModel):
    source: str = Field(default="", max_length=100000)
    language: Literal["c", "lex", "flex"] = "c"


class TokenOut(BaseModel):
    type: str
    lexeme: str
    line: int
    column: int


class LexErrorOut(BaseModel):
    kind: str
    code: str
    message: str
    lexeme: str
    line: int
    column: int


class LexResponse(BaseModel):
    tokens: List[TokenOut]
    errors: List[LexErrorOut]
    token_count: int
    error_count: int
    has_errors: bool


class AnalysisRecordCreate(BaseModel):
    source: str = Field(default="", max_length=100000)
    analysis_type: str = Field(default="diagnosis")
    status: str = Field(default="unknown")
    token_count: int = Field(default=0, ge=0)
    error_count: int = Field(default=0, ge=0)
    summary: str = Field(default="")
    result: Dict[str, Any] = Field(default_factory=dict)


class AnalysisRecordOut(BaseModel):
    id: int
    source: str
    analysis_type: str
    status: str
    created_at: str
    token_count: int
    error_count: int
    summary: str
    result: Dict[str, Any]


class HistoryListResponse(BaseModel):
    items: List[AnalysisRecordOut]
    total: int
