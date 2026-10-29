const BASE_URL = "/api";

function hasFields(payload, fields) {
  return fields.every(([field, expectedType]) => {
    const value = payload[field];
    if (expectedType === "array") return Array.isArray(value);
    if (expectedType === "object") {
      return value !== null && typeof value === "object" && !Array.isArray(value);
    }
    return typeof value === expectedType;
  });
}

async function request(path, options = {}, responseFields = []) {
  let response;
  let responseText;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
      signal: controller.signal,
    });
    responseText = await response.text();
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("The request timed out. Please retry the analysis.");
    }
    if (error instanceof TypeError) {
      throw new Error("Unable to reach the SMARTLEX backend. Check that the backend is running and try again.");
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }

  let payload;
  if (responseText) {
    try {
      payload = JSON.parse(responseText);
    } catch {
      if (response.ok) {
        throw new Error("The backend returned an invalid response. Please try again.");
      }
    }
  }

  if (!response.ok) {
    const detail = payload?.detail;
    const message = typeof detail === "string"
      ? detail
      : Array.isArray(detail)
        ? detail.map((item) => item.msg).filter(Boolean).join("; ")
        : `Request failed with status ${response.status}`;
    if (response.status === 404) {
      throw new Error("The requested backend endpoint was not found (404). Restart the backend from this workspace to load the current API routes.");
    }
    throw new Error(message);
  }

  if (payload === undefined) {
    throw new Error("The backend returned an empty response. Please try again.");
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("The backend returned an unexpected response format. Please try again.");
  }
  if (!hasFields(payload, responseFields)) {
    throw new Error("The backend returned an incomplete response. Please try again.");
  }
  return payload;
}

export function getHealth() {
  return request("/health", {}, [
    ["status", "string"],
    ["app", "string"],
    ["version", "string"],
    ["timestamp", "string"],
  ]);
}

export function analyzeLex(source, language = "c") {
  return request("/lex", {
    method: "POST",
    body: JSON.stringify({ source, language }),
  }, [
    ["tokens", "array"],
    ["errors", "array"],
    ["token_count", "number"],
    ["error_count", "number"],
    ["has_errors", "boolean"],
  ]);
}

export function analyzeParse(source, language = "c") {
  return request("/parse", {
    method: "POST",
    body: JSON.stringify({ source, language }),
  }, [
    ["valid", "boolean"],
    ["token_count", "number"],
    ["statement_count", "number"],
    ["syntax_errors", "array"],
    ["lexical_errors", "array"],
    ["error_count", "number"],
    ["has_errors", "boolean"],
    ["statements", "array"],
  ]);
}

export function analyzeDiagnose(source, language = "c") {
  return request("/diagnose", {
    method: "POST",
    body: JSON.stringify({ source, language }),
  }, [
    ["valid", "boolean"],
    ["token_count", "number"],
    ["diagnoses", "array"],
    ["error_count", "number"],
    ["has_errors", "boolean"],
    ["lexical_errors", "array"],
    ["syntax_errors", "array"],
    ["ai_analysis", "object"],
  ]);
}

export function analyzeSuggestions(source, language = "c") {
  return request("/suggestions", {
    method: "POST",
    body: JSON.stringify({ source, language }),
  }, [
    ["valid", "boolean"],
    ["token_count", "number"],
    ["diagnoses", "array"],
    ["suggestions", "array"],
    ["error_count", "number"],
    ["has_errors", "boolean"],
    ["lexical_errors", "array"],
    ["syntax_errors", "array"],
    ["ai_analysis", "object"],
  ]);
}

export function saveAnalysisRecord(payload) {
  return request("/history", {
    method: "POST",
    body: JSON.stringify(payload),
  }, [
    ["id", "number"],
    ["source", "string"],
    ["analysis_type", "string"],
    ["status", "string"],
    ["created_at", "string"],
    ["token_count", "number"],
    ["error_count", "number"],
    ["summary", "string"],
    ["result", "object"],
  ]);
}

export function listAnalysisRecords(limit = 20) {
  return request(`/history?limit=${limit}`, {}, [
    ["items", "array"],
    ["total", "number"],
  ]);
}

export function getAnalysisRecord(recordId) {
  return request(`/history/${recordId}`, {}, [
    ["id", "number"],
    ["source", "string"],
    ["analysis_type", "string"],
    ["status", "string"],
    ["created_at", "string"],
    ["token_count", "number"],
    ["error_count", "number"],
    ["summary", "string"],
    ["result", "object"],
  ]);
}

export function deleteAnalysisRecord(recordId) {
  return request(`/history/${recordId}`, {
    method: "DELETE",
  }, [
    ["deleted", "boolean"],
    ["id", "number"],
  ]);
}