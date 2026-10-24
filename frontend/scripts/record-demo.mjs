import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { randomBytes } from "node:crypto";
import { mkdir, copyFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.resolve(frontendDir, "..");
const width = 1920;
const height = 1080;
const siteOrigin = "http://127.0.0.1:3000";
const apiOrigin = "http://127.0.0.1:8001";
const taskDescription = "Fix the division by zero defect in the calculator";
const runId = new Date().toISOString().replaceAll(":", "-").replaceAll(".", "-");
const outputDir = path.join(repositoryRoot, "demo-recordings", runId);
const browserVideoDir = path.join(outputDir, "browser-video");
const children = [];
let browser;
let context;
let recordingPage;
let recordingVideo;
let complete = false;

const fixturePath = path.join(repositoryRoot, "tests", "fixtures", "planning_repo").replaceAll("\\", "/");
const recordingPassword = randomBytes(32).toString("base64url");
const baseEnvironment = {
  ...process.env,
  ENVIRONMENT: "development",
  INFERENCE_PROVIDER: "mock",
  NEBIUS_LIVE_INFERENCE_ENABLED: "false",
  NEBIUS_API_KEY: "",
  AUTHORIZED_REPOSITORIES: JSON.stringify({ "planning-fixture": fixturePath }),
  ENABLE_LOCAL_REVIEWS: "true",
  ENABLE_ISOLATED_RUNTIME_VALIDATION: "false",
  DEMO_AUTH_USERNAME: "local-recording",
  DEMO_AUTH_PASSWORD: recordingPassword,
  DEMO_AUTH_ORIGIN: siteOrigin,
  BACKEND_API_URL: apiOrigin,
  NEXT_PUBLIC_REPOSITORY_IDS: "planning-fixture",
  NEXT_PUBLIC_LOCAL_REVIEWER_ID: "demo_reviewer",
  NEXT_PUBLIC_EXECUTION_AUTHORIZER_ID: "local_authorizer",
  NEXT_TELEMETRY_DISABLED: "1",
};

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function assertPortFree(port) {
  await new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", (error) => {
      if (error.code === "EADDRINUSE") reject(new Error(`Required loopback port ${port} is already in use; no existing process was stopped.`));
      else reject(error);
    });
    server.listen(port, "127.0.0.1", () => server.close(resolve));
  });
}

function launch(executable, args, cwd, env) {
  const child = spawn(executable, args, {
    cwd,
    env,
    windowsHide: true,
    stdio: "ignore",
  });
  children.push(child);
  child.once("error", () => {});
  return child;
}

async function runBuild(executable, args, cwd, env) {
  await new Promise((resolve, reject) => {
    const child = spawn(executable, args, { cwd, env, windowsHide: true, stdio: "ignore" });
    child.once("error", () => reject(new Error("Next.js production build could not start.")));
    child.once("exit", (code) => code === 0 ? resolve() : reject(new Error(`Next.js production build failed with exit code ${code ?? "unknown"}.`)));
  });
}

async function waitFor(url, label, headers = {}, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { headers, signal: AbortSignal.timeout(3_000) });
      if (response.ok) return response;
    } catch {
      // The local service may still be starting; retry only the health probe.
    }
    await delay(400);
  }
  throw new Error(`${label} did not become ready within the bounded startup window.`);
}

async function waitUntil(recordingStartedAt, offsetMs) {
  const remaining = recordingStartedAt + offsetMs - Date.now();
  if (remaining > 0) await delay(remaining);
}

async function stopChildren() {
  for (const child of children.reverse()) {
    if (child.exitCode === null && child.signalCode === null) child.kill();
  }
  await Promise.all(children.map((child) => new Promise((resolve) => {
    if (child.exitCode !== null || child.signalCode !== null) return resolve();
    const timer = setTimeout(resolve, 4_000);
    child.once("exit", () => { clearTimeout(timer); resolve(); });
  })));
}

async function run() {
  await assertPortFree(8001);
  await assertPortFree(3000);
  await mkdir(browserVideoDir, { recursive: true });

  const python = path.join(repositoryRoot, ".venv", "Scripts", "python.exe");
  const nextBin = path.join(frontendDir, "node_modules", "next", "dist", "bin", "next");
  const node = process.execPath;

  console.log("Building production dashboard with mock-only recording configuration…");
  await runBuild(node, [nextBin, "build", "--webpack"], frontendDir, baseEnvironment);

  console.log("Starting loopback-only FastAPI and production Next.js…");
  launch(python, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001", "--workers", "1"], repositoryRoot, baseEnvironment);
  await waitFor(`${apiOrigin}/health`, "FastAPI health endpoint");
  launch(node, [nextBin, "start", "--hostname", "127.0.0.1", "--port", "3000"], frontendDir, baseEnvironment);

  const basicAuth = Buffer.from(`local-recording:${recordingPassword}`).toString("base64");
  await waitFor(`${siteOrigin}/`, "Authenticated dashboard", { Authorization: `Basic ${basicAuth}` });

  browser = await chromium.launch({ headless: true });
  context = await browser.newContext({
    viewport: { width, height },
    screen: { width, height },
    deviceScaleFactor: 1,
    httpCredentials: { username: "local-recording", password: recordingPassword },
    recordVideo: { dir: browserVideoDir, size: { width, height } },
  });
  recordingPage = await context.newPage();
  recordingPage.setDefaultTimeout(20_000);

  await recordingPage.goto(siteOrigin, { waitUntil: "domcontentloaded", timeout: 30_000 });
  await recordingPage.getByRole("heading", { name: /Good work starts with context/i }).waitFor();
  await recordingPage.getByText("FastAPI is responding", { exact: true }).waitFor();
  const selector = recordingPage.getByRole("combobox", { name: "Select configured repository" });
  if (await selector.inputValue() !== "planning-fixture") throw new Error("The dashboard did not select the synthetic planning fixture.");

  const recordingStartedAt = Date.now();
  console.log("Recording the actual dashboard workflow at 1920×1080; provider is mock.");

  // 0:00–0:25 — Problem and workspace context.
  await waitUntil(recordingStartedAt, 25_000);

  // 0:25–0:50 — Static repository analysis and dependency evidence.
  await recordingPage.getByRole("button", { name: /Analyze repository/ }).click();
  await recordingPage.getByText("Analysis complete", { exact: false }).waitFor();
  const dependencyDetails = recordingPage.getByText("Imports & dependency manifests", { exact: false });
  await dependencyDetails.click();
  await recordingPage.getByText("requirements.txt", { exact: true }).waitFor();
  await waitUntil(recordingStartedAt, 50_000);

  // 0:50–1:20 — Deterministic mock planning, explicitly disclosed in the UI.
  await recordingPage.locator("#task-description").fill(taskDescription);
  await recordingPage.getByRole("button", { name: /Generate plan/ }).click();
  await recordingPage.getByText("Deterministic mock result — not AI-generated.", { exact: true }).waitFor();
  await recordingPage.getByText("This response was not generated by NVIDIA Nemotron.", { exact: true }).waitFor();
  await recordingPage.getByText("Execution has not started", { exact: true }).waitFor();
  await waitUntil(recordingStartedAt, 80_000);

  // 1:20–1:42 — Verified citations and their repository paths.
  const supportingEvidence = recordingPage.locator(".plan-result .data-section").filter({
    has: recordingPage.getByRole("heading", { name: "Supporting evidence", exact: true }),
  });
  await supportingEvidence.waitFor();
  await supportingEvidence.getByText("package/calculator.py:", { exact: false }).first().waitFor();
  if (!(await supportingEvidence.innerText()).includes("package/calculator.py")) {
    throw new Error("The plan did not show a calculator source citation in supporting evidence.");
  }
  await supportingEvidence.scrollIntoViewIfNeeded();
  await waitUntil(recordingStartedAt, 102_000);

  // 1:42–2:07 — Allowlisted deterministic preview and not-run runtime state.
  await recordingPage.getByRole("button", { name: /Generate code proposal/ }).click();
  await recordingPage.getByRole("heading", { name: "Code change proposal" }).waitFor();
  await recordingPage.getByText("Proposal generator: deterministic allowlist", { exact: false }).waitFor();
  await recordingPage.getByText("Runtime validation: not run", { exact: true }).waitFor();
  await recordingPage.locator(".proposal-diff").scrollIntoViewIfNeeded();
  await waitUntil(recordingStartedAt, 127_000);

  // 2:07–2:30 — Record a local, unverified human decision for consideration.
  const reviewHeading = recordingPage.getByRole("heading", { name: "Human review" });
  await reviewHeading.scrollIntoViewIfNeeded();
  await recordingPage.locator("#reviewer-id").fill("demo_reviewer");
  await recordingPage.locator("#review-justification").fill("Reviewed the deterministic preview and its verified calculator evidence.");
  await recordingPage.getByRole("button", { name: "Approve for consideration" }).click();
  await recordingPage.getByText("Review Completed", { exact: true }).waitFor();
  await recordingPage.getByText("demo_reviewer (unverified)", { exact: false }).waitFor();
  await waitUntil(recordingStartedAt, 150_000);

  // 2:30–2:50 — Generate the actual handoff and end on the safety status.
  await recordingPage.getByRole("button", { name: "Generate report" }).click();
  await recordingPage.getByRole("heading", { name: "Engineering handoff report" }).waitFor();
  const handoff = recordingPage.locator(".handoff-result");
  await handoff.waitFor();
  const handoffText = await handoff.innerText();
  if (!handoffText.includes("demo_reviewer") || !handoffText.includes("not_run")) {
    throw new Error("The handoff report did not show the recorded reviewer and not-run runtime status.");
  }
  await handoff.scrollIntoViewIfNeeded();
  await recordingPage.getByText("Next engineer actions", { exact: true }).scrollIntoViewIfNeeded();
  await waitUntil(recordingStartedAt, 170_000);

  complete = true;
}

try {
  await run();
} catch (error) {
  console.error(`Recording stopped: ${error instanceof Error ? error.message : "an unexpected workflow error occurred"}`);
} finally {
  if (recordingPage) recordingVideo = recordingPage.video();
  if (context) await context.close().catch(() => {});
  if (browser) await browser.close().catch(() => {});
  let sourceVideoPath;
  if (recordingVideo) sourceVideoPath = await recordingVideo.path().catch(() => undefined);
  await stopChildren();

  if (sourceVideoPath) {
    const outputName = complete ? "devrelay-phase-8d2-demo.webm" : "devrelay-phase-8d2-demo.partial.webm";
    const outputPath = path.join(outputDir, outputName);
    await copyFile(sourceVideoPath, outputPath);
    const outputStats = await stat(outputPath);
    const measuredSeconds = complete ? 170 : null;
    console.log(`Recording ${complete ? "completed" : "partial"}: ${outputPath}`);
    console.log(`Video: ${width}x${height} WebM; ${outputStats.size} bytes${measuredSeconds ? `; scripted duration ${measuredSeconds}s` : "; duration not verified"}.`);
  } else {
    console.log("No video file was finalized.");
  }

  if (!complete) process.exitCode = 1;
}
