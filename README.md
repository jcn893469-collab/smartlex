# SMARTLEX

Intelligent Error Diagnosis for Lexical & Syntax Analysis.

Stack: React + Vite (frontend), FastAPI (backend), Python lexer/parser, SQLite, Pytest.

Status: Phase 6 frontend analysis integration and the proposed Phase 7
integration-quality and proposed Phase 8 browser-testing scopes are complete;
see `docs/BUILD_PROGRESS.md`. Full project documentation remains planned for
Phase 9.

## Run (Windows PowerShell)

Backend:

    cd backend
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    if (!(Test-Path .env)) { Copy-Item .env.example .env }
    # Edit backend\.env locally and set GEMINI_API_KEY to enable Gemini analysis.
    # GEMINI_MODEL defaults to gemini-3-flash-preview and can be changed to a model available to your account.
    uvicorn app.main:app --reload --port 8000

Frontend (second terminal):

    cd frontend
    npm install
    npm run dev

Open http://localhost:5173

## Supported language subset

SMARTLEX implements a small C-like teaching language, not the complete C
language. The lexer recognizes primitive type names (`int`, `float`, `double`,
`char`, `bool`, `void`), identifiers, integer/float/string/character literals,
comments, operators, and delimiters. The parser currently handles variable
declarations, assignments, expression statements, `if`/`else`, `while`, `for`,
`return`, `print(...)`, and brace-delimited blocks.

Expressions support unary `+`, `-`, `!`; arithmetic `+`, `-`, `*`, `/`, `%`;
relational and equality operators; logical `&&` and `||`; grouping with
parentheses; identifiers, literals, and identifier-based calls. The lexer
recognizes some additional C-like tokens that are not necessarily valid in the
parser grammar. Full C constructs such as function definitions, arrays,
structures, pointers, and the complete operator grammar are not implemented.
Array declarations and indexed reads/writes are supported, and statically
provable out-of-bounds accesses are reported locally without Gemini.
`for` loops support declaration or assignment initializers, a condition
expression, an update expression, and a statement body; assignment expressions
and increment/decrement expressions are not implemented in the loop update.

The parser and diagnosis pipeline currently short-circuits syntax parsing when
lexical errors are present. In that case it reports lexical errors and does
not infer additional syntax errors from the incomplete token stream.

## API

All routes are prefixed with `/api`. Source-analysis POST endpoints accept JSON
in the form `{"source":"...","language":"c"}` (`language` may be `c`,
`lex`, or `flex`; it defaults to `c`; source is limited to 100,000 characters).
Invalid JSON, an unsupported language, a non-string source, or an oversized
source is rejected with HTTP 422. Gemini is optional and configured only in
the backend `.env` file with `GEMINI_API_KEY`; choose the model with `GEMINI_MODEL` (defaults to
`gemini-3-flash-preview`). The backend loads that file relative to the backend
project, regardless of the shell's working directory. Set the key only in
`backend\.env` (never in frontend code), keep that file out of Git, and use the
blank `GEMINI_API_KEY=` setting in `.env.example` as the template. Analysis
requests have a 15-second Gemini timeout by default (Gemini requires at least
10 seconds). Free-tier usage is subject
to Google's changing per-model rate limits, quotas, account eligibility, and
regional availability; reaching a limit leaves deterministic local analysis
available.
Gemini findings are advisory and are labeled separately from deterministic
local syntax, lexical, and array-bounds findings. SMARTLEX does not compile or
execute submitted source.

| Method and path | Purpose | Response shape |
| --- | --- | --- |
| `GET /api/health` | Health check | `status`, `app`, `version`, `timestamp` |
| `POST /api/lex` | Tokenize source | `tokens`, `errors`, `token_count`, `error_count`, `has_errors` |
| `POST /api/parse` | Parse source | `valid`, `token_count`, `statement_count`, `diagnostics`, `syntax_errors`, `lexical_errors`, `error_count`, `has_errors`, `statements` |
| `POST /api/diagnose` | Classify lexical or parser errors | `valid`, `source_length`, `token_count`, `diagnoses`, `error_count`, `has_errors`, `lexical_errors`, `syntax_errors` |
| `POST /api/suggestions` | Explain conservative corrections | Diagnosis fields plus `suggestions` |
| `POST /api/history` | Save an analysis record | Record fields: `id`, `source`, `analysis_type`, `status`, `created_at`, `token_count`, `error_count`, `summary`, `result` |
| `GET /api/history?limit=20` | List recent records (`limit` 1–100) | `items`, `total` |
| `GET /api/history/{analysis_id}` | Retrieve one record | Analysis record fields |
| `DELETE /api/history/{analysis_id}` | Delete one record | `deleted`, `id`; missing IDs return HTTP 404 |

Inspect the running API's OpenAPI schema at `http://127.0.0.1:8000/openapi.json`
for field types and current route definitions. The frontend uses the existing
Vite `/api` proxy to reach the backend.

## Validation

Run the backend test suite from `backend/`:

    python -m pytest -v

Build the frontend from `frontend/`:

    npm run build

## Browser end-to-end tests

The frontend's Playwright tests run a separate FastAPI backend on port `8001`
and Vite server on port `5174`, so they do not stop or use the application's
usual development servers. The test backend uses a unique temporary SQLite
database that is removed when the test command exits. History records created
by the tests are also deleted through the API.

Install frontend dependencies, including Playwright:

    cd frontend
    npm install

The default browser configuration uses an installed stable Google Chrome.
Run the complete browser suite with:

    npm run test:e2e

On a machine without Google Chrome, install Playwright's Chromium browser and
select it for the test run:

    npx playwright install chromium
    $env:SMARTLEX_E2E_BROWSER = "chromium"
    npm run test:e2e

The automated browser tests verify app startup and health, valid tokenization
and parsing, lexical and syntax errors, diagnosis and suggestions, empty input,
loading/disabled controls, backend/network/malformed-response errors, stale
source snapshot protection, history save/reopen/cleanup, and mobile-width
overflow. Ports `8001` and `5174` must be available; the test runner fails
without terminating any process that already occupies them.

## Diagnosis and correction limitations

Diagnosis and correction are rule-based and use the lexer/parser diagnostics
and their available token positions. They are not a substitute for a complete
compiler and cannot reliably infer user intent. Ambiguous cases use
explanatory-only suggestions that require review. Even specific suggestions
are advisory: the API returns them as separate data and never rewrites the
submitted source.