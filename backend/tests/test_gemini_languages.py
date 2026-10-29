import asyncio
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.ai import gemini
from app.core.config import BACKEND_ENV_FILE, Settings, get_settings
from app.main import app

client = TestClient(app)

VALID_C_ANALYSIS = {
    "language": "c",
    "status": "complete",
    "diagnostics": [{
        "severity": "error",
        "category": "array-bounds",
        "message": "Index is out of bounds.",
        "line": 3,
        "column": 9,
        "explanation": "The array has five elements.",
        "suggestion": "Use an index from 0 to 4.",
    }],
    "suggestions": ["Check all array indices."],
    "summary": "One array access is out of bounds.",
}
VALID_LEX_ANALYSIS = {
    "language": "lex",
    "status": "complete",
    "diagnostics": [],
    "suggestions": ["Add a catch-all rule."],
    "summary": "The scanner specification is structurally sound.",
}


def _mock_gemini(monkeypatch, response_text, timeout=3.0):
    class FakeModels:
        def generate_content(self, **kwargs):
            self.request = kwargs
            return SimpleNamespace(text=response_text)

    models = FakeModels()

    class FakeClient:
        def __init__(self, **kwargs):
            models.client_options = kwargs
            self.models = models

    fake_genai = ModuleType("google.genai")
    fake_genai.Client = FakeClient
    fake_types = SimpleNamespace(
        HttpOptions=lambda **kwargs: kwargs,
        HttpRetryOptions=lambda **kwargs: kwargs,
        GenerateContentConfig=lambda **kwargs: kwargs,
    )
    fake_genai.types = fake_types
    fake_google = ModuleType("google")
    fake_google.__path__ = []
    fake_google.genai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setattr(gemini, "get_settings", lambda: SimpleNamespace(
        gemini_api_key="test-key",
        gemini_model="mock-model",
        gemini_timeout_seconds=timeout,
    ))
    return models


def test_gemini_validates_and_keeps_language_specific_prompt(monkeypatch):
    models = _mock_gemini(monkeypatch, json.dumps(VALID_LEX_ANALYSIS))
    result = asyncio.run(gemini.get_gemini_analysis("%%\n[0-9]+ return;", "lex"))

    assert result["status"] == "available"
    assert result["analysis"]["language"] == "lex"
    assert "Lex/Flex" in models.request["contents"]
    assert "ordinary C" in models.request["contents"]
    assert models.client_options["api_key"] == "test-key"
    assert models.request["model"] == "mock-model"
    assert models.client_options["http_options"]["retry_options"]["attempts"] == 1


def test_missing_key_returns_disabled_without_calling_gemini(monkeypatch):
    monkeypatch.setattr(gemini, "get_settings", lambda: SimpleNamespace(gemini_api_key="  "))

    result = asyncio.run(gemini.get_gemini_analysis("int main() {}", "c"))

    assert result["status"] == "disabled"
    assert "GEMINI_API_KEY" in result["error"]
    assert result["analysis"] is None


def test_settings_load_dotenv_from_backend_path_outside_backend_cwd(monkeypatch, tmp_path):
    env_file = tmp_path / "backend.env"
    env_file.write_text("GEMINI_API_KEY=test-key-from-dotenv\n", encoding="utf-8")
    other_directory = tmp_path / "other-directory"
    other_directory.mkdir()
    monkeypatch.chdir(other_directory)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", env_file)
    get_settings.cache_clear()

    try:
        assert get_settings().gemini_api_key == "test-key-from-dotenv"
    finally:
        get_settings.cache_clear()

    assert BACKEND_ENV_FILE == Path(__file__).resolve().parents[1] / ".env"


def test_malformed_or_wrong_language_gemini_response_is_rejected(monkeypatch):
    _mock_gemini(monkeypatch, "not json")
    malformed = asyncio.run(gemini.get_gemini_analysis("int x;", "c"))
    assert malformed["status"] == "unavailable"
    assert "malformed" in malformed["error"].lower()

    _mock_gemini(monkeypatch, json.dumps(VALID_C_ANALYSIS))
    wrong_language = asyncio.run(gemini.get_gemini_analysis("%%\nx return;", "lex"))
    assert wrong_language["status"] == "unavailable"


def test_quota_errors_are_retryable_and_readable(monkeypatch):
    models = _mock_gemini(monkeypatch, json.dumps(VALID_C_ANALYSIS))

    def quota_error(**kwargs):
        raise RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded")

    models.generate_content = quota_error
    result = asyncio.run(gemini.get_gemini_analysis("int x;", "c"))

    assert result["status"] == "unavailable"
    assert "quota" in result["error"].lower()
    assert result["http_status"] == 429
    assert result["error_kind"] == "quota_exhausted"


def test_gemini_failure_logs_http_status_and_code_without_key_or_body(monkeypatch, caplog):
    models = _mock_gemini(monkeypatch, json.dumps(VALID_C_ANALYSIS))
    secret = "test-key-must-not-be-logged"
    monkeypatch.setattr(
        gemini,
        "get_settings",
        lambda: SimpleNamespace(
            gemini_api_key=secret,
            gemini_model="mock-model",
            gemini_timeout_seconds=3.0,
        ),
    )

    def api_error(**kwargs):
        error = RuntimeError(f"403 PERMISSION_DENIED {secret}")
        error.code = 403
        error.status = "PERMISSION_DENIED"
        error.details = {"error": {"code": 403, "status": "PERMISSION_DENIED"}}
        raise error

    models.generate_content = api_error
    with caplog.at_level("WARNING", logger="app.ai.gemini"):
        result = asyncio.run(gemini.get_gemini_analysis("int value;", "c"))

    assert result["status"] == "unavailable"
    assert "permission" in result["error"].lower()
    assert "RuntimeError" in caplog.text
    assert "http_status=403" in caplog.text
    assert "error_code=PERMISSION_DENIED" in caplog.text
    assert secret not in caplog.text


@pytest.mark.parametrize(
    (
        "http_status",
        "provider_status",
        "reason",
        "message",
        "metadata",
        "header_retry_after",
        "expected_kind",
        "expected_error",
        "expected_retry_after",
    ),
    [
        (
            429,
            "RESOURCE_EXHAUSTED",
            "RATE_LIMIT_EXCEEDED",
            "Requests per minute limit exceeded",
            {"quotaMetric": "generate_requests_per_minute"},
            "12",
            "rate_limited",
            "rate limit",
            12.0,
        ),
        (
            429,
            "RESOURCE_EXHAUSTED",
            "QUOTA_EXCEEDED",
            "Daily request quota exhausted",
            {"quotaMetric": "generate_requests_per_day"},
            None,
            "quota_exhausted",
            "quota is exhausted",
            90.0,
        ),
        (
            403,
            "PERMISSION_DENIED",
            "ACCOUNT_INELIGIBLE",
            "This account is not eligible for this API",
            {},
            None,
            "account_eligibility",
            "eligibility",
            None,
        ),
        (
            403,
            "PERMISSION_DENIED",
            "ACCESS_DENIED",
            "Permission denied for this model",
            {},
            None,
            "permission_denied",
            "permission",
            None,
        ),
        (
            503,
            "UNAVAILABLE",
            None,
            "Temporary service failure",
            {},
            None,
            "server_error",
            "server error",
            None,
        ),
    ],
)
def test_provider_errors_are_classified_and_retry_guidance_is_returned(
    monkeypatch,
    http_status,
    provider_status,
    reason,
    message,
    metadata,
    header_retry_after,
    expected_kind,
    expected_error,
    expected_retry_after,
):
    models = _mock_gemini(monkeypatch, json.dumps(VALID_C_ANALYSIS))

    def provider_error(**kwargs):
        error_info = {"reason": reason, "metadata": metadata} if reason else None
        retry_info = {"retryDelay": "90s"} if expected_retry_after == 90.0 else None
        details = [item for item in (error_info, retry_info) if item]
        response_json = {
            "error": {
                "code": http_status,
                "status": provider_status,
                "message": message,
                "details": details,
            }
        }
        error = RuntimeError(f"{http_status} {provider_status}: {message}")
        error.code = http_status
        error.status = provider_status
        error.details = response_json
        error.response = SimpleNamespace(
            headers={"Retry-After": header_retry_after}
            if header_retry_after is not None
            else {}
        )
        raise error

    models.generate_content = provider_error
    result = asyncio.run(gemini.get_gemini_analysis("int x;", "c"))

    assert result["status"] == "unavailable"
    assert result["http_status"] == http_status
    assert result["error_code"] == provider_status
    assert result["error_kind"] == expected_kind
    assert expected_error in result["error"].lower()
    assert result["retry_after_seconds"] == expected_retry_after


def test_error_without_http_status_is_classified_as_network_failure(monkeypatch):
    models = _mock_gemini(monkeypatch, json.dumps(VALID_C_ANALYSIS))
    models.generate_content = lambda **kwargs: (_ for _ in ()).throw(
        OSError("connection reset")
    )

    result = asyncio.run(gemini.get_gemini_analysis("int x;", "c"))

    assert result["status"] == "unavailable"
    assert result["http_status"] is None
    assert result["error_kind"] == "network_error"
    assert result["retry_after_seconds"] is None


@pytest.mark.parametrize(
    ("exception_message", "expected_message"),
    [
        ("404 model not found", "model is unavailable"),
        ("network connection failed", "could not connect"),
    ],
)
def test_model_and_network_errors_are_readable(
    monkeypatch, exception_message, expected_message
):
    models = _mock_gemini(monkeypatch, json.dumps(VALID_C_ANALYSIS))

    def api_error(**kwargs):
        if "network" in exception_message:
            raise OSError(exception_message)
        raise RuntimeError(exception_message)

    models.generate_content = api_error
    result = asyncio.run(gemini.get_gemini_analysis("int x;", "c"))

    assert result["status"] == "unavailable"
    assert expected_message in result["error"].lower()


def test_invalid_key_errors_are_readable_and_locations_are_bounded(monkeypatch):
    models = _mock_gemini(monkeypatch, json.dumps(VALID_C_ANALYSIS))
    result = asyncio.run(gemini.get_gemini_analysis("int x;", "c"))
    diagnostic = result["analysis"]["diagnostics"][0]
    assert diagnostic["line"] is None
    assert diagnostic["column"] is None

    def invalid_key(**kwargs):
        raise RuntimeError("403 API key not valid")

    models.generate_content = invalid_key
    failed = asyncio.run(gemini.get_gemini_analysis("int x;", "c"))
    assert failed["status"] == "unavailable"
    assert "permission" in failed["error"].lower()


def test_gemini_timeout_returns_retryable_failure(monkeypatch):
    _mock_gemini(monkeypatch, json.dumps(VALID_C_ANALYSIS), timeout=1.0)
    original_wait_for = asyncio.wait_for

    async def timed_out(awaitable, timeout):
        awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(gemini.asyncio, "wait_for", timed_out)
    result = asyncio.run(gemini.get_gemini_analysis("int x;", "c"))
    monkeypatch.setattr(gemini.asyncio, "wait_for", original_wait_for)

    assert result["status"] == "unavailable"
    assert "timed out" in result["error"].lower()


def test_language_aware_lex_and_parse_routes_accept_flex_without_c_errors(monkeypatch):
    async def unavailable(source, language):
        return {"status": "unavailable", "error": "mocked", "analysis": None}

    monkeypatch.setattr("app.api.diagnose.get_gemini_analysis", unavailable)
    source = "%{\n#include <stdio.h>\n%}\n%%\n[0-9]+ { printf(\"%s\", yytext); }\n%%"

    lexed = client.post("/api/lex", json={"source": source, "language": "lex"})
    parsed = client.post("/api/parse", json={"source": source, "language": "lex"})
    diagnosed = client.post("/api/diagnose", json={"source": source, "language": "lex"})

    assert lexed.status_code == 200
    assert lexed.json()["errors"] == []
    assert parsed.status_code == 200
    assert parsed.json()["valid"] is True
    assert diagnosed.status_code == 200
    assert diagnosed.json()["ai_analysis"]["status"] == "unavailable"


def test_malformed_flex_is_reported_as_flex_diagnostics():
    response = client.post("/api/parse", json={"source": "[0-9]+ { return; }", "language": "flex"})

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert any("%%" in item["message"] for item in body["syntax_errors"])
    assert body["lexical_errors"] == []


def test_array_bounds_are_reported_deterministically_and_valid_access_is_not_flagged():
    source = "int main() { int arr[5]; int index = 10; arr[index] = 100; return arr[4]; }"
    response = client.post("/api/diagnose", json={"source": source, "language": "c"})
    valid = client.post("/api/diagnose", json={
        "source": "int data[5]; data[0] = 2; return data[4];",
        "language": "c",
    })

    assert response.status_code == 200
    finding = response.json()["deterministic_findings"][0]
    assert finding["category"] == "array-index-out-of-bounds"
    assert finding["actual"] == "10"
    assert finding["expected"] == "0–4"
    assert finding["source"] == "deterministic"
    assert valid.status_code == 200
    assert valid.json()["deterministic_findings"] == []


def test_deterministic_analysis_survives_gemini_unavailable(monkeypatch):
    async def unavailable(source, language):
        return {"status": "unavailable", "error": "mock failure", "analysis": None}

    monkeypatch.setattr("app.api.diagnose.get_gemini_analysis", unavailable)
    response = client.post("/api/diagnose", json={
        "source": "int values[2]; values[8] = 0;",
        "language": "c",
    })

    assert response.status_code == 200
    assert response.json()["deterministic_findings"]
    assert response.json()["ai_analysis"]["status"] == "unavailable"


def test_diagnosis_endpoint_returns_structured_gemini_diagnostics(monkeypatch):
    async def available(source, language):
        return {"status": "available", "error": None, "analysis": VALID_C_ANALYSIS}

    monkeypatch.setattr("app.api.diagnose.get_gemini_analysis", available)
    response = client.post("/api/diagnose", json={"source": "int x = 1;", "language": "c"})

    assert response.status_code == 200
    body = response.json()
    assert body["ai_analysis"]["analysis"]["language"] == "c"
    diagnostic = body["ai_analysis"]["analysis"]["diagnostics"][0]
    assert diagnostic["severity"] == "error"
    assert diagnostic["line"] == 3
    assert diagnostic["suggestion"]


@pytest.mark.parametrize(
    ("language", "expected_language", "source"),
    [
        ("c", "c", "int value = 0;"),
        ("flex", "lex", "%%\n[0-9]+ { return NUMBER; }\n%%"),
    ],
)
def test_diagnosis_endpoint_sends_selected_language_to_gemini(
    monkeypatch, language, expected_language, source
):
    calls = []

    async def available(request_source, request_language):
        calls.append((request_source, request_language))
        return {
            "status": "available",
            "error": None,
            "analysis": {
                **(VALID_C_ANALYSIS if expected_language == "c" else VALID_LEX_ANALYSIS),
                "language": expected_language,
            },
        }

    monkeypatch.setattr("app.api.diagnose.get_gemini_analysis", available)
    response = client.post(
        "/api/diagnose",
        json={"source": source, "language": language},
    )

    assert response.status_code == 200
    assert calls == [(source, language)]
    assert response.json()["ai_analysis"]["analysis"]["language"] == expected_language
