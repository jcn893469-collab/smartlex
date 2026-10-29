
import { useState } from "react";

import {
  analyzeDiagnose,
  analyzeLex,
  analyzeParse,
  analyzeSuggestions,
  saveAnalysisRecord,
} from "../services/api.js";

const MODES = [
  { key: "lex", label: "Lexical" },
  { key: "parse", label: "Parse" },
  { key: "diagnose", label: "Diagnosis" },
  { key: "suggestions", label: "Suggestions" },
];

const SAMPLE_SOURCE = `int x = 10;
if (x > 5) {
  x = x + 1;
}`;

function summarizeResult(mode, data) {
  if (!data) return "No result yet.";

  if (mode === "lex") {
    return `${data.token_count ?? data.tokens?.length ?? 0} tokens | ${data.error_count ?? data.errors?.length ?? 0} lexical errors`;
  }

  if (mode === "parse") {
    return `${data.statement_count ?? data.statements?.length ?? 0} statements | ${data.error_count ?? 0} errors`;
  }

  if (mode === "diagnose") {
    return `${data.error_count ?? data.diagnoses?.length ?? 0} diagnoses`;
  }

  return `${data.suggestions?.length ?? 0} suggestions`;
}

function Location({ item }) {
  if (item.line == null && item.column == null) return null;

  return (
    <span className="result-location">
      {item.line != null ? `Line ${item.line}` : ""}
      {item.line != null && item.column != null ? ", " : ""}
      {item.column != null ? `column ${item.column}` : ""}
    </span>
  );
}

function EmptyState({ children }) {
  return <p className="muted result-empty">{children}</p>;
}

function TokenResults({ data }) {
  const tokens = Array.isArray(data.tokens) ? data.tokens : [];
  const errors = Array.isArray(data.errors) ? data.errors : [];

  return (
    <>
      <p className={errors.length ? "status status-down" : "status status-up"}>
        {summarizeResult("lex", data)}
      </p>

      {tokens.length ? (
        <div className="table-scroll">
          <table className="result-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Lexeme</th>
                <th>Line</th>
                <th>Column</th>
              </tr>
            </thead>
            <tbody>
              {tokens.map((token, index) => (
                <tr key={`${token.line}-${token.column}-${index}`}>
                  <td>{token.type ?? "Unknown"}</td>
                  <td><code>{token.lexeme ?? ""}</code></td>
                  <td>{token.line ?? "—"}</td>
                  <td>{token.column ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState>No tokens were returned.</EmptyState>
      )}

      {errors.length > 0 && (
        <ResultList
          title="Lexical errors"
          items={errors}
          messageKey="message"
        />
      )}
    </>
  );
}

function ResultList({ title, items, messageKey }) {
  if (!items.length) {
    return <EmptyState>No {title.toLowerCase()} reported.</EmptyState>;
  }

  return (
    <section className="result-section">
      <h4>
        {title} <span className="count-badge">{items.length}</span>
      </h4>

      <ul className="result-list">
        {items.map((item, index) => (
          <li
            key={`${item.line ?? "unknown"}-${item.column ?? "unknown"}-${index}`}
          >
            <div className="result-item-heading">
              <strong>
                {item.category ?? item.kind ?? item.code ?? title}
              </strong>
              <Location item={item} />
            </div>

            <p>
              {item[messageKey] ??
                item.explanation ??
                item.message ??
                "No details provided."}
            </p>

            {item.lexeme && (
              <p className="result-meta">
                Token: <code>{item.lexeme}</code>
              </p>
            )}

            {(item.expected || item.actual) && (
              <p className="result-meta">
                {item.expected && (
                  <>Expected: <code>{item.expected}</code> </>
                )}
                {item.actual && (
                  <>Actual: <code>{item.actual}</code></>
                )}
              </p>
            )}

            {item.root_cause && (
              <p className="result-meta">
                Probable cause: {item.root_cause}
              </p>
            )}

            {item.confidence != null && (
              <p className="result-meta">
                Confidence: {Math.round(item.confidence * 100)}%
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function SuggestionResults({ data, onSourceChange }) {
  const suggestions = Array.isArray(data.suggestions)
    ? data.suggestions
    : [];

  const diagnoses = Array.isArray(data.diagnoses)
    ? data.diagnoses
    : [];

  return (
    <>
      <p className={data.has_errors ? "status status-down" : "status status-up"}>
        {summarizeResult("suggestions", data)}
        {data.token_count != null ? ` | ${data.token_count} tokens` : ""}
        {data.error_count != null ? ` | ${data.error_count} errors` : ""}
      </p>

      <ResultList
        title="Error diagnoses"
        items={diagnoses}
        messageKey="explanation"
      />

      {suggestions.length ? (
        <section className="result-section">
          <h4>
            Correction suggestions{" "}
            <span className="count-badge">{suggestions.length}</span>
          </h4>

          <ul className="result-list">
            {suggestions.map((suggestion, index) => (
              <li
                key={`${suggestion.error_id ?? "error"}-${suggestion.rule_id ?? index}-${index}`}
              >
                <div className="result-item-heading">
                  <strong>{suggestion.rule_id ?? "Suggestion"}</strong>
                  <Location item={suggestion} />
                </div>

                <p>
                  {suggestion.explanation ??
                    "Review this suggestion before applying it."}
                </p>

                <p className="result-meta">
                  Action:{" "}
                  <code>{suggestion.action ?? "explanatory_only"}</code>
                  {suggestion.confidence != null && (
                    <>
                      {" "}· Confidence:{" "}
                      {Math.round(suggestion.confidence * 100)}%
                    </>
                  )}
                  {suggestion.requires_review && (
                    <> · Review recommended</>
                  )}
                </p>

                {suggestion.original_text != null && (
                  <p className="result-meta">
                    Current text:{" "}
                    <code>{suggestion.original_text || "(empty)"}</code>
                  </p>
                )}

                {suggestion.suggested_text != null &&
                  suggestion.action !== "explanatory_only" && (
                    <p className="suggested-code">
                      Suggested text:{" "}
                      <code>{suggestion.suggested_text || "(remove)"}</code>
                    </p>
                  )}

                {suggestion.action === "explanatory_only" && (
                  <p className="result-meta">
                    No replacement text is proposed.
                  </p>
                )}

                {/* NEW: Complete corrected-code preview */}
                {suggestion.corrected_source != null && (
                  <div className="suggestion-correction">
                    <h5>Suggested corrected code</h5>

                    <pre className="suggested-code">
                      <code>{suggestion.corrected_source}</code>
                    </pre>

                    {suggestion.requires_review && (
                      <p className="result-meta">
                        Review this correction carefully before applying it.
                      </p>
                    )}

                    <button
                      className="btn"
                      type="button"
                      disabled={typeof onSourceChange !== "function"}
                      onClick={() =>
                        onSourceChange(suggestion.corrected_source)
                      }
                    >
                      Apply suggestion
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>

          <p className="muted suggestion-notice">
            Suggestions are advisory only; your source code has not been
            changed unless you apply a correction.
          </p>
        </section>
      ) : (
        <EmptyState>No correction suggestions were returned.</EmptyState>
      )}
    </>
  );
}

function AIAnalysisResults({ result }) {
  const ai = result?.ai_analysis;
  if (!ai) return null;
  if (ai.status !== "available" || !ai.analysis) {
    return (
      <section className="result-section" aria-live="polite">
        <h4>Gemini AI analysis</h4>
        <p className="status status-down">
          {ai.status === "disabled"
            ? "Gemini was not configured for this backend."
            : "Gemini request failed; no AI findings were produced."}
        </p>
        <p>{ai.error ?? "Retry the analysis after resolving the Gemini configuration or service error."}</p>
        {ai.http_status != null && (
          <p className="result-meta">
            Gemini HTTP status: {ai.http_status}
            {ai.error_code ? ` · Error code: ${ai.error_code}` : ""}
          </p>
        )}
        {ai.retry_after_seconds != null && (
          <p className="result-meta">
            Google requested waiting at least {Math.ceil(ai.retry_after_seconds)} seconds before retrying.
          </p>
        )}
        <p className="muted">
          Any findings shown above are local deterministic results, not Gemini output.
          Retry manually after resolving the issue; SMARTLEX will not automatically repeat quota-consuming requests.
        </p>
      </section>
    );
  }

  const analysis = ai.analysis;
  const diagnostics = Array.isArray(analysis.diagnostics) ? analysis.diagnostics : [];
  const suggestions = Array.isArray(analysis.suggestions) ? analysis.suggestions : [];
  return (
    <section className="result-section" aria-live="polite">
      <h4>Gemini AI analysis <span className="count-badge">Request succeeded · AI, not compiler-verified</span></h4>
      {analysis.summary && <p>{analysis.summary}</p>}
      {diagnostics.length ? (
        <ul className="result-list">
          {diagnostics.map((item, index) => (
            <li key={`${item.category}-${item.line ?? "unknown"}-${index}`}>
              <div className="result-item-heading">
                <strong>{item.severity?.toUpperCase()}: {item.category}</strong>
                <Location item={item} />
              </div>
              <p>{item.message}</p>
              <p className="result-meta">{item.explanation}</p>
              {item.suggestion && <p className="suggested-code">Suggestion: {item.suggestion}</p>}
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState>No AI diagnostics returned.</EmptyState>
      )}
      {suggestions.length > 0 && (
        <ul className="result-list">
          {suggestions.map((suggestion, index) => <li key={index}>{suggestion}</li>)}
        </ul>
      )}
    </section>
  );
}

function renderDetails(mode, data, onSourceChange) {
  if (!data) {
    return <EmptyState>Submit source code to inspect the output.</EmptyState>;
  }

  if (mode === "lex") {
    return <TokenResults data={data} />;
  }

  if (mode === "parse") {
    const syntaxErrors = Array.isArray(data.syntax_errors)
      ? data.syntax_errors
      : [];

    const lexicalErrors = Array.isArray(data.lexical_errors)
      ? data.lexical_errors
      : [];
    const semanticErrors = Array.isArray(data.semantic_errors)
      ? data.semantic_errors
      : [];

    const valid = data.valid === true;

    return (
      <>
        <p className={valid ? "status status-up" : "status status-down"}>
          {summarizeResult("parse", data)}
          {valid ? " | Valid syntax" : " | Syntax errors found"}
        </p>

        {data.token_count != null && (
          <p className="result-meta">
            Tokens analyzed: {data.token_count}
          </p>
        )}

        {syntaxErrors.length ? (
          <ResultList
            title="Syntax errors"
            items={syntaxErrors}
            messageKey="message"
          />
        ) : (
          <EmptyState>No syntax errors reported.</EmptyState>
        )}

        {lexicalErrors.length > 0 && (
          <ResultList
            title="Lexical errors"
            items={lexicalErrors}
            messageKey="message"
          />
        )}

        {semanticErrors.length > 0 && (
          <ResultList
            title="Deterministic local findings"
            items={semanticErrors}
            messageKey="explanation"
          />
        )}

        {data.statement_count != null && (
          <p className="result-meta">
            Statements parsed: {data.statement_count}
          </p>
        )}
      </>
    );
  }

  if (mode === "diagnose") {
    const diagnoses = Array.isArray(data.diagnoses)
      ? data.diagnoses
      : [];
    const deterministicFindings = Array.isArray(data.deterministic_findings)
      ? data.deterministic_findings
      : [];
    const otherDiagnoses = diagnoses.filter((item) => item.source !== "deterministic");

    return (
      <>
        <p className={data.has_errors ? "status status-down" : "status status-up"}>
          {summarizeResult(mode, data)}
          {data.token_count != null ? ` | ${data.token_count} tokens` : ""}
        </p>

        {otherDiagnoses.length ? (
          <ResultList
            title="Local syntax and lexical diagnoses"
            items={otherDiagnoses}
            messageKey="explanation"
          />
        ) : (
          <EmptyState>No errors were diagnosed.</EmptyState>
        )}
        {deterministicFindings.length > 0 && (
          <ResultList
            title="Deterministic local findings"
            items={deterministicFindings}
            messageKey="explanation"
          />
        )}
        <AIAnalysisResults result={data} />
      </>
    );
  }

  return (
    <SuggestionResults
      data={data}
      onSourceChange={onSourceChange}
    />
  );
}

export default function AnalysisPanel({ source, onSourceChange, language = "c", onLanguageChange }) {
  const [mode, setMode] = useState("diagnose");
  const [result, setResult] = useState(null);
  const [analyzedSource, setAnalyzedSource] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [saveStatus, setSaveStatus] = useState("");

  const currentSource = source ?? SAMPLE_SOURCE;
  const activeMode = MODES.find((item) => item.key === mode) ?? MODES[0];

  async function handleAnalyze() {
    if (!currentSource.trim()) {
      setResult(null);
      setAnalyzedSource("");
      setError("Enter source code before running an analysis.");
      setSaveStatus("");
      return;
    }

    const sourceSnapshot = currentSource;

    setLoading(true);
    setError(null);
    setSaveStatus("");
    setResult(null);
    setAnalyzedSource("");

    try {
      const apiCall =
        mode === "lex"
          ? analyzeLex
          : mode === "parse"
            ? analyzeParse
            : mode === "diagnose"
              ? analyzeDiagnose
              : analyzeSuggestions;

      const payload = await apiCall(sourceSnapshot, language);

      if (!payload || typeof payload !== "object") {
        throw new Error(
          "The backend returned an unexpected analysis result."
        );
      }

      setResult(payload);
      setAnalyzedSource(sourceSnapshot);
    } catch (err) {
      setError(err.message || "Analysis failed. Please try again.");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    if (!result) {
      setSaveStatus("Run an analysis before saving.");
      return;
    }

    if (currentSource !== analyzedSource) {
      setSaveStatus(
        "The source has changed since this result was produced. Run the analysis again before saving."
      );
      return;
    }

    try {
      const payload = {
        source: analyzedSource,
        analysis_type: mode,
        status:
          result.valid === false || result.has_errors ? "error" : "valid",
        token_count: result.token_count ?? 0,
        error_count: result.error_count ?? 0,
        summary: summarizeResult(mode, result),
        result,
      };

      await saveAnalysisRecord(payload);
      setSaveStatus("Saved to analysis history.");
    } catch (err) {
      setSaveStatus(
        err.message || "Unable to save the analysis record."
      );
    }
  }

  return (
    <div className="card analysis-panel">
      <div className="panel-header">
        <div>
          <h2>SMARTLEX Analysis Console</h2>
          <p className="muted">
            Run real lexer, parser, diagnosis, and suggestion checks against
            the backend.
          </p>
        </div>
      </div>

      <label className="field-label" htmlFor="language-select">Language</label>
      <select
        id="language-select"
        className="language-select"
        value={language}
        onChange={(event) => {
          onLanguageChange?.(event.target.value);
          setResult(null);
          setAnalyzedSource("");
          setError(null);
          setSaveStatus("");
        }}
        disabled={loading}
      >
        <option value="c">C</option>
        <option value="lex">Lex/Flex</option>
      </select>

      <div
        className="mode-switcher"
        role="tablist"
        aria-label="Analysis mode selector"
      >
        {MODES.map((item) => (
          <button
            key={item.key}
            type="button"
            className={item.key === mode ? "mode-btn active" : "mode-btn"}
            onClick={() => {
              setMode(item.key);
              setResult(null);
              setAnalyzedSource("");
              setError(null);
              setSaveStatus("");
            }}
            disabled={loading}
            role="tab"
            aria-selected={item.key === mode}
          >
            {item.label}
          </button>
        ))}
      </div>

      <label className="field-label" htmlFor="source-input">
        Source code
      </label>

      <textarea
        id="source-input"
        className="source-input"
        value={currentSource}
        onChange={(event) => onSourceChange?.(event.target.value)}
        rows={12}
        spellCheck={false}
        disabled={loading}
        aria-describedby="source-help"
      />

      <p id="source-help" className="muted editor-help">
        {language === "lex"
          ? "Lex/Flex specifications are analyzed as scanner definitions, rules, and embedded C actions."
          : "Analysis is advisory and never compiles or executes this C source."}
      </p>

      <div className="panel-actions">
        <button
          className="btn"
          type="button"
          onClick={handleAnalyze}
          disabled={loading}
        >
          {loading ? "Analyzing..." : `Run ${activeMode.label} analysis`}
        </button>

        <button
          className="btn secondary"
          type="button"
          onClick={handleSave}
          disabled={loading || !result}
        >
          Save to history
        </button>
      </div>

      {loading && (
        <p className="status status-up" role="status" aria-live="polite">
          Analyzing source code…
        </p>
      )}

      {error && <p className="status status-down">{error}</p>}
      {saveStatus && <p className="muted">{saveStatus}</p>}

      <div className="result-box">
        <h3>{activeMode.label} Results</h3>

        {result && (
          <p className="muted analyzed-source-note">
            Results for the submitted source snapshot
            {currentSource !== analyzedSource
              ? " (the editor has since changed)"
              : ""}
            .
          </p>
        )}

        {/* Pass onSourceChange to enable Apply suggestion */}
        {renderDetails(mode, result, onSourceChange)}
        {mode === "suggestions" && <AIAnalysisResults result={result} />}
      </div>
    </div>
  );
}
