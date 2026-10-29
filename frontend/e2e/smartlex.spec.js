import { expect, test } from "@playwright/test";

const SOURCE = "#source-input";
const API_BASE = "http://127.0.0.1:8001";
const createdRecordIds = new Set();

test.afterEach(async ({ request }) => {
  for (const recordId of createdRecordIds) {
    const response = await request.delete(`${API_BASE}/api/history/${recordId}`);
    expect([200, 404]).toContain(response.status());
    createdRecordIds.delete(recordId);
  }
});

async function selectMode(page, name) {
  await page.getByRole("tab", { name }).click();
}

async function analyze(page, modeName) {
  await page.getByRole("button", { name: `Run ${modeName} analysis` }).click();
}

test("opens the application and displays backend status", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "SMARTLEX", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "SMARTLEX Analysis Console" })).toBeVisible();
  await expect(page.getByText("● Connected")).toBeVisible();
});

test("valid source produces real tokens and a valid parse result", async ({ page }) => {
  await page.goto("/");
  await page.locator(SOURCE).fill("int total = 5 + 7;");

  await selectMode(page, "Lexical");
  await analyze(page, "Lexical");
  await expect(page.getByRole("cell", { name: "KEYWORD" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "total" })).toBeVisible();
  await expect(page.locator(".result-box")).toContainText("0 lexical errors");

  await selectMode(page, "Parse");
  await analyze(page, "Parse");
  await expect(page.locator(".result-box")).toContainText("Valid syntax");
  await expect(page.locator(".result-box")).toContainText("1 statements");
});

test("lexical errors display their character and source location", async ({ page }) => {
  await page.goto("/");
  await page.locator(SOURCE).fill("int x = 5 @ 3;");

  await selectMode(page, "Lexical");
  await analyze(page, "Lexical");

  await expect(page.locator(".result-box")).toContainText("Lexical errors");
  await expect(page.locator(".result-box")).toContainText("Invalid character '@'");
  await expect(page.locator(".result-box")).toContainText("Line 1, column 11");
  await expect(page.locator(".result-box")).toContainText("@");
});

test("parser displays a missing-semicolon error at its reported location", async ({ page }) => {
  await page.goto("/");
  await page.locator(SOURCE).fill("int x = 10");

  await selectMode(page, "Parse");
  await analyze(page, "Parse");

  await expect(page.locator(".result-box")).toContainText("Syntax errors");
  await expect(page.locator(".result-box")).toContainText("missing-token");
  await expect(page.locator(".result-box")).toContainText("Line 1, column 9");
  await expect(page.locator(".result-box")).toContainText("Expected: ;");
});

test("diagnosis and suggestions render from the API without modifying source", async ({ page }) => {
  const source = "int x = (1;";
  await page.goto("/");
  await page.locator(SOURCE).fill(source);

  await selectMode(page, "Diagnosis");
  await analyze(page, "Diagnosis");
  await expect(page.locator(".result-box")).toContainText("unmatched-delimiter");
  await expect(page.locator(".result-box")).toContainText("Line 1, column 11");

  await selectMode(page, "Suggestions");
  await analyze(page, "Suggestions");
  await expect(page.locator(".result-box")).toContainText("missing-closing-delimiter");
  await expect(page.locator(".result-box")).toContainText("Suggested text:");
  await expect(page.locator(".result-box")).toContainText("Suggestions are advisory only");
  await expect(page.locator(SOURCE)).toHaveValue(source);
});

test("selected C and Lex/Flex languages reach Gemini and render structured findings", async ({ page }) => {
  const requests = [];
  await page.route("**/api/diagnose", async (route) => {
    const body = route.request().postDataJSON();
    requests.push(body);
    const language = body.language === "lex" ? "lex" : "c";
    const category = language === "lex" ? "malformed-flex-rule" : "array-bounds";
    const message = language === "lex" ? "Missing action block." : "Index is out of bounds.";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        valid: false,
        source_length: body.source.length,
        token_count: 1,
        diagnoses: [],
        deterministic_findings: [],
        ai_analysis: {
          status: "available",
          error: null,
          analysis: {
            language,
            status: "complete",
            diagnostics: [{
              severity: "error",
              category,
              message,
              line: 3,
              column: 4,
              explanation: "The submitted source supports this location.",
              suggestion: "Add a valid rule action.",
            }],
            suggestions: [],
            summary: `${language} analysis completed.`,
          },
        },
        error_count: 1,
        has_errors: true,
        lexical_errors: [],
        syntax_errors: [],
      }),
    });
  });

  await page.goto("/");
  await page.locator(SOURCE).fill("int values[2]; values[5] = 1;");
  await analyze(page, "Diagnosis");
  await expect(page.locator(".result-box")).toContainText("array-bounds");
  await expect(page.locator(".result-box")).toContainText("Line 3, column 4");

  await page.locator("#language-select").selectOption("lex");
  const flexSource = "%%\n[a-z]+ { return WORD; }";
  await page.locator(SOURCE).fill(flexSource);
  await analyze(page, "Diagnosis");
  await expect(page.locator(".result-box")).toContainText("malformed-flex-rule");
  await expect(page.locator(".result-box")).toContainText("lex analysis completed.");

  expect(requests.map(({ language, source }) => [language, source])).toEqual([
    ["c", "int values[2]; values[5] = 1;"],
    ["lex", flexSource],
  ]);
});

test("empty source is rejected locally with a clear message", async ({ page }) => {
  await page.goto("/");
  await page.locator(SOURCE).fill("");

  await analyze(page, "Diagnosis");

  await expect(page.getByText("Enter source code before running an analysis.")).toBeVisible();
  await expect(page.locator(".result-box")).toContainText("Submit source code");
});

test("loading disables editor and duplicate submissions until the response arrives", async ({ page }) => {
  let requestReceived;
  const received = new Promise((resolve) => {
    requestReceived = resolve;
  });
  let releaseResponse;
  const responseGate = new Promise((resolve) => {
    releaseResponse = resolve;
  });

  await page.goto("/");
  await page.locator(SOURCE).fill("int x = 1;");
  await selectMode(page, "Lexical");
  await page.route("**/api/lex", async (route) => {
    requestReceived();
    await responseGate;
    await route.continue();
  });

  try {
    await page.getByRole("button", { name: "Run Lexical analysis" }).click();
    await received;
    await expect(page.getByRole("status")).toHaveText("Analyzing source code…");
    await expect(page.locator(SOURCE)).toBeDisabled();
    await expect(page.getByRole("button", { name: "Analyzing..." })).toBeDisabled();
  } finally {
    releaseResponse();
  }

  await expect(page.getByRole("cell", { name: "KEYWORD" })).toBeVisible();
  await page.unroute("**/api/lex");
});

test("network failures, unsuccessful responses, and malformed JSON are reported", async ({ page }) => {
  await page.goto("/");
  await page.locator(SOURCE).fill("int x = 1;");
  await selectMode(page, "Lexical");

  await page.route("**/api/lex", (route) => route.abort());
  await analyze(page, "Lexical");
  await expect(page.getByText(/Unable to reach the SMARTLEX backend/)).toBeVisible();
  await page.unroute("**/api/lex");

  await page.route("**/api/lex", (route) =>
    route.fulfill({ status: 503, contentType: "application/json", body: '{"detail":"Service unavailable"}' }),
  );
  await analyze(page, "Lexical");
  await expect(page.getByText("Service unavailable")).toBeVisible();
  await page.unroute("**/api/lex");

  await page.route("**/api/lex", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "{}" }),
  );
  await analyze(page, "Lexical");
  await expect(page.getByText(/backend returned an incomplete response/)).toBeVisible();
  await page.unroute("**/api/lex");
});

test("stale results are identified and cannot be saved against edited source", async ({ page }) => {
  const originalSource = "int original = 1;";
  const historyWrites = [];
  await page.goto("/");
  await page.locator(SOURCE).fill(originalSource);
  await selectMode(page, "Lexical");
  await analyze(page, "Lexical");
  await expect(page.getByRole("cell", { name: "original" })).toBeVisible();

  page.on("request", (request) => {
    if (request.url().endsWith("/api/history") && request.method() === "POST") {
      historyWrites.push(request);
    }
  });
  await page.locator(SOURCE).fill("int changed = 2;");
  await expect(page.locator(".analyzed-source-note")).toContainText("editor has since changed");
  await page.getByRole("button", { name: "Save to history" }).click();
  await expect(page.getByText(/source has changed since this result was produced/)).toBeVisible();
  expect(historyWrites).toHaveLength(0);
  await expect(page.locator(SOURCE)).toHaveValue("int changed = 2;");
});

test("history saves and reopens the analyzed source snapshot", async ({ page }) => {
  const source = "int saved_value = 7;";
  await page.goto("/");
  await page.locator(SOURCE).fill(source);
  await selectMode(page, "Lexical");
  await analyze(page, "Lexical");
  await expect(page.getByRole("cell", { name: "saved_value" })).toBeVisible();

  const createResponsePromise = page.waitForResponse(
    (response) => response.url().endsWith("/api/history") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Save to history" }).click();
  const createResponse = await createResponsePromise;
  expect(createResponse.status()).toBe(200);
  const record = await createResponse.json();
  createdRecordIds.add(record.id);
  expect(record.source).toBe(source);
  expect(record.analysis_type).toBe("lex");

  await page.reload();
  await expect(page.getByText("lex", { exact: true })).toBeVisible();
  await page.locator(SOURCE).fill("int other_value = 9;");
  await page.getByRole("button", { name: "Load" }).click();
  await expect(page.locator(SOURCE)).toHaveValue(source);
});

test("analysis layout fits a mobile viewport without horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.locator(SOURCE).fill("int mobile = 1;");
  await selectMode(page, "Suggestions");
  await analyze(page, "Suggestions");
  await expect(page.locator(".result-box")).toContainText("No correction suggestions");

  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);
});
