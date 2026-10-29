import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import get_settings


logger = logging.getLogger(__name__)


class GeminiDiagnostic(BaseModel):
    model_config = ConfigDict(extra="ignore")

    severity: Literal["error", "warning", "info"]
    category: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=1000)
    line: int | None = Field(default=None, ge=1)
    column: int | None = Field(default=None, ge=1)
    explanation: str = Field(min_length=1, max_length=2000)
    suggestion: str = Field(max_length=1000)


class GeminiAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")

    language: Literal["c", "lex"]
    status: Literal["complete", "partial"]
    diagnostics: list[GeminiDiagnostic] = Field(max_length=100)
    suggestions: list[str] = Field(max_length=20)
    summary: str = Field(max_length=2000)


def parse_gemini_json(
    text: str, expected_language: str, source: str = ""
) -> dict[str, Any]:
    payload = GeminiAnalysis.model_validate_json(text)
    language = "lex" if expected_language in {"lex", "flex"} else "c"
    if payload.language != language:
        raise ValueError("Gemini returned a different language than requested")
    result = payload.model_dump()
    source_lines = source.splitlines()
    for diagnostic in result["diagnostics"]:
        line = diagnostic["line"]
        column = diagnostic["column"]
        if line is None:
            diagnostic["column"] = None
        elif line > len(source_lines):
            diagnostic["line"] = None
            diagnostic["column"] = None
        elif column is not None and column > len(source_lines[line - 1]) + 1:
            diagnostic["column"] = None
    return result


def _error_payload(error: Exception) -> dict[str, Any]:
    details = getattr(error, "details", None)
    if not isinstance(details, dict):
        details = {}
    nested_error = details.get("error")
    if not isinstance(nested_error, dict):
        nested_error = details

    raw_status_code = (
        getattr(error, "code", None)
        or getattr(error, "status_code", None)
        or nested_error.get("code")
    )
    try:
        status_code = int(raw_status_code) if raw_status_code is not None else None
    except (TypeError, ValueError):
        status_code = None
    if status_code is None:
        status_match = re.search(r"\b([1-5]\d\d)\b", str(error))
        if status_match:
            status_code = int(status_match.group(1))

    error_code = (
        getattr(error, "status", None)
        or nested_error.get("status")
        or nested_error.get("reason")
    )
    if error_code is None:
        error_code_match = re.search(
            r"\b(RESOURCE_EXHAUSTED|PERMISSION_DENIED|UNAVAILABLE|INTERNAL)\b",
            str(error),
        )
        if error_code_match:
            error_code = error_code_match.group(1)
    message = getattr(error, "message", None) or nested_error.get("message") or str(error)
    combined_details = " ".join(
        str(value)
        for value in (message, error_code, nested_error.get("details", ""))
    ).lower()

    retry_after = _retry_after_seconds(error, nested_error)
    if status_code == 429:
        quota_markers = (
            "quota_exceeded",
            "daily",
            "per_day",
            "requests_per_day",
            "quota limit",
            "quota exceeded",
            "free_tier",
        )
        rate_markers = (
            "rate_limit",
            "per_minute",
            "requests_per_minute",
            "rate limit",
        )
        if any(marker in combined_details for marker in quota_markers):
            kind = "quota_exhausted"
            error_message = "Gemini request quota is exhausted. Wait for the quota reset before retrying; local analysis is still available."
        elif any(marker in combined_details for marker in rate_markers):
            kind = "rate_limited"
            error_message = "Gemini rate limit reached. Wait before retrying; local analysis is still available."
        else:
            kind = "rate_limited"
            error_message = "Gemini returned HTTP 429. Wait before retrying; local analysis is still available."
    elif status_code == 403:
        if any(marker in combined_details for marker in ("billing", "free_tier", "account", "region", "eligible", "eligibility")):
            kind = "account_eligibility"
            error_message = "Gemini denied access for this account, region, or plan. Check Gemini API eligibility; local analysis is still available."
        else:
            kind = "permission_denied"
            error_message = "Gemini denied permission for this request. Check API access and model permissions; local analysis is still available."
    elif status_code == 401:
        kind = "authentication"
        error_message = "Gemini authentication failed. Check GEMINI_API_KEY in the backend environment."
    elif status_code == 404:
        kind = "model_unavailable"
        error_message = "The configured Gemini model is unavailable to this account. Set GEMINI_MODEL to a supported model and retry."
    elif status_code is not None and status_code >= 500:
        kind = "server_error"
        error_message = "Gemini is temporarily experiencing a server error. Retry later; local analysis is still available."
    elif status_code == 400 or "invalid_argument" in combined_details:
        kind = "invalid_request"
        error_message = "Gemini rejected the request configuration. Check the configured model and request settings; local analysis is still available."
    elif isinstance(error, (TimeoutError, asyncio.TimeoutError)) or any(
        term in combined_details for term in ("timeout", "timed out")
    ):
        kind = "timeout"
        error_message = "Gemini analysis timed out. Retry the request or use local analysis."
    elif isinstance(error, (OSError, ConnectionError)) or type(error).__name__ in {
        "ConnectError",
        "ConnectTimeout",
        "NetworkError",
        "ReadError",
        "ReadTimeout",
        "RemoteProtocolError",
        "WriteError",
        "WriteTimeout",
    }:
        kind = "network_error"
        error_message = "Could not connect to Gemini. Check the network connection and retry; local analysis is still available."
    else:
        kind = "unavailable"
        error_message = "Gemini is temporarily unavailable. Retry the request; local analysis is still available."

    return {
        "status": "unavailable",
        "error": error_message,
        "analysis": None,
        "error_kind": kind,
        "http_status": status_code,
        "error_code": str(error_code) if error_code is not None else None,
        "retry_after_seconds": retry_after,
    }


def _retry_after_seconds(error: Exception, error_body: dict[str, Any]) -> float | None:
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    retry_after = headers.get("Retry-After") if headers is not None else None
    if retry_after is not None:
        try:
            return max(0.0, float(retry_after))
        except (TypeError, ValueError):
            try:
                retry_time = parsedate_to_datetime(str(retry_after))
                if retry_time.tzinfo is None:
                    retry_time = retry_time.replace(tzinfo=timezone.utc)
                return max(0.0, (retry_time - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass

    for detail in error_body.get("details", []):
        if not isinstance(detail, dict):
            continue
        retry_delay = detail.get("retryDelay")
        if isinstance(retry_delay, str):
            match = re.fullmatch(r"(\d+(?:\.\d+)?)s", retry_delay.strip())
            if match:
                return max(0.0, float(match.group(1)))
    return None


def _safe_log_code(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(value))[:80] if value is not None else "unknown"


async def get_gemini_analysis(
    source: str, language: str
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.gemini_api_key or not settings.gemini_api_key.strip():
        return {
            "status": "disabled",
            "error": "Gemini is not configured. Set GEMINI_API_KEY in the backend environment.",
            "analysis": None,
        }

    normalized_language = "lex" if language in {"lex", "flex"} else "c"
    language_name = "Lex/Flex" if normalized_language == "lex" else "C"
    prompt = f"""Analyze the following {language_name} source code. Treat it only as {language_name}; do not interpret Lex/Flex as ordinary C. Identify supported syntax errors, undeclared variables when provable, array bounds when provable, malformed expressions, likely runtime risks, and concise code improvements. Do not claim to compile or execute the source. Never invent a line or column: use null when the location is uncertain. Return ONLY JSON with exactly these fields: language (\"{normalized_language}\"), status (\"complete\" or \"partial\"), diagnostics (array), suggestions (array of strings), summary (string). Each diagnostic must contain severity (error, warning, or info), category, message, line (integer or null), column (integer or null), explanation, and suggestion. Keep diagnostics evidence-based and suggestions concise.

SOURCE:
```{language_name.lower()}
{source}
```"""

    # Gemini rejects request deadlines shorter than 10 seconds.
    timeout = max(10.0, min(settings.gemini_timeout_seconds, 20.0))
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=settings.gemini_api_key.strip(),
            http_options=types.HttpOptions(
                timeout=int(timeout * 1000),
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.models.generate_content,
                model=settings.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            ),
            timeout=timeout,
        )
        response_text = getattr(response, "text", None)
        if not isinstance(response_text, str) or not response_text.strip():
            raise ValueError("Gemini returned an empty response")
        analysis = parse_gemini_json(response_text, normalized_language, source)
        return {"status": "available", "error": None, "analysis": analysis}
    except (ValidationError, ValueError, json.JSONDecodeError):
        return {
            "status": "unavailable",
            "error": "Gemini returned malformed analysis. Retry the request; local analysis is still available.",
            "analysis": None,
        }
    except Exception as error:
        failure = _error_payload(error)
        logger.warning(
            "Gemini request failed model=%s language=%s exception=%s http_status=%s error_code=%s error_kind=%s retry_after_seconds=%s",
            settings.gemini_model,
            normalized_language,
            type(error).__name__,
            failure["http_status"],
            _safe_log_code(failure["error_code"]),
            failure["error_kind"],
            failure["retry_after_seconds"],
        )
        return failure
