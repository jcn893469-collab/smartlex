from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import diagnose, health, history, lex, parse, suggestions
from app.core.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.getLogger("uvicorn.error").info(
        "Gemini API key configured: %s",
        bool(settings.gemini_api_key and settings.gemini_api_key.strip()),
    )
    yield

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Intelligent Error Diagnosis for Lexical & Syntax Analysis",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(lex.router, prefix="/api")
app.include_router(parse.router, prefix="/api")
app.include_router(diagnose.router, prefix="/api")
app.include_router(suggestions.router, prefix="/api")
app.include_router(history.router, prefix="/api")


@app.get("/")
def root() -> dict:
    return {"message": "SMARTLEX backend is running", "docs": "/docs"}
