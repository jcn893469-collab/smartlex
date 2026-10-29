import { spawn, spawnSync } from "node:child_process";
import { existsSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendDirectory = path.dirname(fileURLToPath(import.meta.url));
const backendDirectory = path.resolve(frontendDirectory, "..", "backend");
const databasePath = path.join(os.tmpdir(), `smartlex-playwright-${process.pid}.sqlite3`);
const outputDirectory = path.join(os.tmpdir(), `smartlex-playwright-results-${process.pid}`);
const playwrightCli = path.join(frontendDirectory, "node_modules", "playwright", "cli.js");
const viteCli = path.join(frontendDirectory, "node_modules", "vite", "bin", "vite.js");
const pythonEnvironment = path.join(
  backendDirectory,
  ".venv",
  process.platform === "win32" ? "Scripts" : "bin",
  process.platform === "win32" ? "python.exe" : "python",
);
const pythonCommand = existsSync(pythonEnvironment) ? pythonEnvironment : "python";
const testProcesses = [];

function startProcess(command, args, options) {
  const child = spawn(command, args, { stdio: "inherit", ...options });
  child.on("error", (error) => {
    child.startupError = error;
  });
  testProcesses.push(child);
  return child;
}

async function waitForServer(url, child, name) {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    if (child.startupError) throw child.startupError;
    if (child.exitCode !== null) throw new Error(`${name} exited before becoming ready.`);
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(1_000) });
      if (response.ok) return;
    } catch {
      // The server may still be starting; retry until the readiness deadline.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`${name} did not become ready at ${url}.`);
}

async function stopProcess(child) {
  if (child.exitCode !== null) return;
  const exited = new Promise((resolve) => child.once("exit", resolve));
  child.kill();
  await Promise.race([
    exited,
    new Promise((resolve) => setTimeout(resolve, 5_000)),
  ]);
  if (child.exitCode === null) {
    child.kill("SIGKILL");
    await exited;
  }
}

let exitCode = 1;
try {
  const backend = startProcess(
    pythonCommand,
    ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001"],
    {
      cwd: backendDirectory,
      env: { ...process.env, SMARTLEX_DB_PATH: databasePath },
    },
  );
  const frontend = startProcess(
    process.execPath,
    [viteCli, "--host", "127.0.0.1", "--port", "5174", "--strictPort"],
    {
      cwd: frontendDirectory,
      env: { ...process.env, SMARTLEX_API_TARGET: "http://127.0.0.1:8001" },
    },
  );
  await Promise.all([
    waitForServer("http://127.0.0.1:8001/api/health", backend, "SMARTLEX test backend"),
    waitForServer("http://127.0.0.1:5174/", frontend, "SMARTLEX test frontend"),
  ]);

  const result = spawnSync(process.execPath, [playwrightCli, "test"], {
    cwd: frontendDirectory,
    env: {
      ...process.env,
      SMARTLEX_E2E_DB_PATH: databasePath,
      SMARTLEX_E2E_OUTPUT_DIR: outputDirectory,
    },
    stdio: "inherit",
  });
  exitCode = result.status ?? 1;
} finally {
  await Promise.all(testProcesses.reverse().map(stopProcess));
  for (const suffix of ["", "-shm", "-wal"]) {
    rmSync(`${databasePath}${suffix}`, { force: true, maxRetries: 5, retryDelay: 200 });
  }
  rmSync(outputDirectory, { force: true, recursive: true, maxRetries: 5, retryDelay: 200 });
}

process.exitCode = exitCode;
