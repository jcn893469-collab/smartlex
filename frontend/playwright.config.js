import os from "node:os";
import path from "node:path";
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  outputDir: process.env.SMARTLEX_E2E_OUTPUT_DIR
    || path.join(os.tmpdir(), `smartlex-playwright-results-${process.pid}`),
  use: {
    baseURL: "http://127.0.0.1:5174",
    browserName: "chromium",
    channel: process.env.SMARTLEX_E2E_BROWSER === "chromium" ? undefined : "chrome",
    headless: true,
    viewport: { width: 1280, height: 900 },
    trace: "retain-on-failure",
  },
});
