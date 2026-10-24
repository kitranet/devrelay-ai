// Live-only continuity-pipeline recording. This script makes exactly one plan request.
// Run only after obtaining separate explicit authorization for that paid request.
import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { randomBytes } from "node:crypto";
import { mkdir, copyFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

if (process.env.DEVRELAY_LIVE_DEMO_AUTHORIZED !== "YES") {
  throw new Error("Set DEVRELAY_LIVE_DEMO_AUTHORIZED=YES only after separately authorizing one live planning request.");
}
if (!process.env.NEBIUS_API_KEY) throw new Error("A Nebius credential is not configured in this process; no request was made.");

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.resolve(frontendDir, "..");
const width = 1920;
const height = 1080;
const siteOrigin = "http://127.0.0.1:3000";
const apiOrigin = "http://127.0.0.1:8001";
const taskDescription = "Investigate why the 02:00 ingestion job can publish a successful report with fewer rows than the inbound batch. Trace orchestration, validation, transformation, retry, configuration, and publication behavior across the repository. Propose safe investigation steps, evidence to collect, and regression checks. Do not assume the root cause, change repository files, or execute code.";
const runId = new Date().toISOString().replaceAll(":", "-").replaceAll(".", "-");
const outputDir = path.join(repositoryRoot, "demo-recordings", `continuity-live-${runId}`);
const browserVideoDir = path.join(outputDir, "browser-video");
const quotaPath = path.join(repositoryRoot, ".devrelay-state", `continuity-live-quota-${runId}.sqlite3`);
const children = [];
let browser;
let context;
let page;
let video;
let complete = false;

const fixturePath = path.join(repositoryRoot, "tests", "fixtures", "continuity_pipeline").replaceAll("\\", "/");
const recordingPassword = randomBytes(32).toString("base64url");
const backendEnvironment = {
  ...process.env,
  ENVIRONMENT: "development",
  INFERENCE_PROVIDER: "nebius",
  NEBIUS_LIVE_INFERENCE_ENABLED: "true",
  NEBIUS_MODEL: "nvidia/Nemotron-3_5-Lightning",
  NEBIUS_PLANNING_DISABLE_THINKING: "true",
  NEBIUS_MAX_OUTPUT_TOKENS: "1024",
  NEBIUS_MAX_PROMPT_TOKENS: "6000",
  NEBIUS_TIMEOUT_SECONDS: "30",
  NEBIUS_MAX_IN_FLIGHT_REQUESTS: "1",
  NEBIUS_QUOTA_DB_PATH: quotaPath,
  NEBIUS_TOTAL_INFERENCE_QUOTA: "1",
  AUTHORIZED_REPOSITORIES: JSON.stringify({ "continuity-pipeline-fixture": fixturePath }),
  ENABLE_LOCAL_REVIEWS: "true",
  ENABLE_ISOLATED_RUNTIME_VALIDATION: "false",
  DEMO_AUTH_USERNAME: "continuity-recording",
  DEMO_AUTH_PASSWORD: recordingPassword,
  DEMO_AUTH_ORIGIN: siteOrigin,
  BACKEND_API_URL: apiOrigin,
  NEXT_PUBLIC_REPOSITORY_IDS: "continuity-pipeline-fixture",
  NEXT_PUBLIC_LOCAL_REVIEWER_ID: "demo_reviewer",
  NEXT_PUBLIC_EXECUTION_AUTHORIZER_ID: "local_authorizer",
  NEXT_TELEMETRY_DISABLED: "1",
};
const frontendEnvironment = { ...backendEnvironment };
// Next loads .env.local itself. Set an empty process value so that local
// frontend dotenv files cannot reintroduce the backend-only credential.
frontendEnvironment.NEBIUS_API_KEY = "";
frontendEnvironment.INFERENCE_PROVIDER = "mock";
frontendEnvironment.NEBIUS_LIVE_INFERENCE_ENABLED = "false";
delete frontendEnvironment.AUTHORIZED_REPOSITORIES;
delete frontendEnvironment.NEBIUS_MODEL;
delete frontendEnvironment.NEBIUS_PLANNING_DISABLE_THINKING;
delete frontendEnvironment.NEBIUS_MAX_OUTPUT_TOKENS;
delete frontendEnvironment.NEBIUS_MAX_PROMPT_TOKENS;
delete frontendEnvironment.NEBIUS_TIMEOUT_SECONDS;
delete frontendEnvironment.NEBIUS_MAX_IN_FLIGHT_REQUESTS;
delete frontendEnvironment.NEBIUS_QUOTA_DB_PATH;
delete frontendEnvironment.NEBIUS_TOTAL_INFERENCE_QUOTA;

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function assertPortFree(port) {
  await new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", (error) => error.code === "EADDRINUSE"
      ? reject(new Error(`Loopback port ${port} is already in use; no process was stopped.`))
      : reject(error));
    server.listen(port, "127.0.0.1", () => server.close(resolve));
  });
}

function launch(executable, args, cwd, env) {
  const child = spawn(executable, args, { cwd, env, windowsHide: true, stdio: "ignore" });
  children.push(child);
  child.once("error", () => {});
  return child;
}

async function runCommand(executable, args, cwd, env, label) {
  await new Promise((resolve, reject) => {
    const child = spawn(executable, args, { cwd, env, windowsHide: true, stdio: "ignore" });
    child.once("error", () => reject(new Error(`${label} could not start.`)));
    child.once("exit", (code) => code === 0 ? resolve() : reject(new Error(`${label} failed (exit ${code ?? "unknown"}).`)));
  });
}

async function waitFor(url, label, headers = {}, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { headers, signal: AbortSignal.timeout(3_000) });
      if (response.ok) return response;
    } catch { /* bounded readiness probe only */ }
    await delay(400);
  }
  throw new Error(`${label} did not become ready within the bounded startup window.`);
}

async function waitUntil(startedAt, elapsedMs) {
  const remaining = startedAt + elapsedMs - Date.now();
  if (remaining > 0) await delay(remaining);
}

async function stopChildren() {
  for (const child of [...children].reverse()) if (child.exitCode === null && child.signalCode === null) child.kill();
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

  // Build the browser app without passing the model credential into Node/Next.
  await runCommand(node, [nextBin, "build", "--webpack"], frontendDir, frontendEnvironment, "Frontend production build");
  await runCommand(python, ["-m", "scripts.inference_quota_admin", "set-total", "1"], repositoryRoot, backendEnvironment, "One-request quota initialization");
  launch(python, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001", "--workers", "1"], repositoryRoot, backendEnvironment);
  await waitFor(`${apiOrigin}/health`, "FastAPI health endpoint");
  const status = await (await fetch(`${apiOrigin}/api/v1/inference/status`)).json();
  if (status.provider !== "nebius" || status.live_inference_enabled !== true || status.credentials_configured !== true || status.quota_status !== "available" || status.quota_remaining !== 1) {
    throw new Error("Live provider preflight did not show Nebius enabled with one available request; no planning request was made.");
  }
  launch(node, [nextBin, "start", "--hostname", "127.0.0.1", "--port", "3000"], frontendDir, frontendEnvironment);
  const authorization = Buffer.from(`continuity-recording:${recordingPassword}`).toString("base64");
  await waitFor(`${siteOrigin}/`, "Authenticated dashboard", { Authorization: `Basic ${authorization}` });

  browser = await chromium.launch({ headless: true });
  context = await browser.newContext({
    viewport: { width, height }, screen: { width, height }, deviceScaleFactor: 1,
    httpCredentials: { username: "continuity-recording", password: recordingPassword },
    recordVideo: { dir: browserVideoDir, size: { width, height } },
  });
  page = await context.newPage();
  page.setDefaultTimeout(20_000);
  await page.goto(siteOrigin, { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.getByRole("heading", { name: /Good work starts with context/i }).waitFor();
  await page.getByText("FastAPI is responding", { exact: true }).waitFor();
  if (await page.getByRole("combobox", { name: "Select configured repository" }).inputValue() !== "continuity-pipeline-fixture") {
    throw new Error("The dashboard did not select the authorized synthetic continuity fixture.");
  }

  const startedAt = Date.now();
  // 0:00–0:25 — Set up the handoff problem and authorized workspace.
  await waitUntil(startedAt, 25_000);
  // 0:25–0:50 — Static repository analysis and module/import discovery.
  await page.getByRole("button", { name: /Analyze repository/ }).click();
  await page.getByText("Analysis complete", { exact: false }).waitFor();
  await page.getByText("Imports & dependency manifests", { exact: false }).click();
  await page.getByText("requirements.txt", { exact: true }).waitFor();
  await waitUntil(startedAt, 50_000);
  // 0:50–1:25 — This is the sole live paid planning request in the script.
  let planRequestCount = 0;
  let planRequestBody;
  page.on("request", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname.endsWith("/api/backend/api/v1/tasks/plan")) {
      planRequestCount += 1;
      planRequestBody = request.postData();
    }
  });
  await page.locator("#task-description").fill(taskDescription);
  await page.getByRole("button", { name: /Generate plan/ }).click();
  await page.getByText("AI-generated planning result; source evidence was validated locally.", { exact: true }).waitFor({ timeout: 70_000 });
  await page.getByText("nvidia/Nemotron-3_5-Lightning", { exact: true }).waitFor();
  if (await page.getByText("Provider: nebius", { exact: false }).count() === 0) throw new Error("The displayed plan did not identify Nebius; recording aborted without a retry.");
  if (await page.getByText("MOCK MODE", { exact: false }).count() > 0) throw new Error("A mock response appeared in the live recording; recording stopped.");
  if (planRequestCount !== 1) throw new Error("The live plan request count was not exactly one; recording stopped without another request.");
  const submittedPlan = JSON.parse(planRequestBody ?? "{}");
  if (submittedPlan.repository_id !== "continuity-pipeline-fixture" || submittedPlan.task_description !== taskDescription) {
    throw new Error("The submitted planning request did not match the configured synthetic scenario.");
  }
  if (await page.getByText("Unverified citations — rejected by source validation", { exact: true }).count() > 0) {
    throw new Error("The plan included rejected source citations; recording stopped.");
  }
  const evidenceSection = page.locator(".plan-result .data-section").filter({
    has: page.getByRole("heading", { name: "Supporting evidence", exact: true }),
  });
  if (await evidenceSection.locator("code").count() === 0) throw new Error("The plan did not show verified source citations; recording stopped.");
  await page.getByText("Supplied source excerpts", { exact: true }).waitFor();
  await page.getByText("Execution has not started", { exact: true }).waitFor();
  await waitUntil(startedAt, 85_000);
  // 1:25–1:50 — Show the actually returned evidence and its observed/suspected labels.
  const evidence = page.getByText("Supporting evidence", { exact: true });
  await evidence.scrollIntoViewIfNeeded();
  await page.getByText("Findings", { exact: true }).scrollIntoViewIfNeeded();
  await waitUntil(startedAt, 110_000);
  // 1:50–2:15 — Keep plan review distinct from code approval.
  await page.getByRole("heading", { name: "Plan review" }).scrollIntoViewIfNeeded();
  await page.getByText("This records review of the investigation plan only.", { exact: false }).waitFor();
  await waitUntil(startedAt, 135_000);
  // 2:15–2:40 — Create and show a plan-only handoff, explicitly still unreviewed.
  await page.getByRole("button", { name: "Create plan-only handoff" }).click();
  await page.getByText("Unreviewed handoff · awaiting human review", { exact: true }).waitFor();
  await page.getByText("Runtime validation:", { exact: false }).scrollIntoViewIfNeeded();
  await waitUntil(startedAt, 160_000);
  // 2:40–2:50 — End on the no-patch/no-execution boundary.
  await page.getByText("No patch was proposed", { exact: false }).scrollIntoViewIfNeeded();
  await waitUntil(startedAt, 170_000);
  complete = true;
}

try {
  await run();
} catch (error) {
  console.error(`Continuity recording stopped: ${error instanceof Error ? error.message : "an unexpected workflow error occurred"}`);
} finally {
  if (page) video = page.video();
  if (context) await context.close().catch(() => {});
  if (browser) await browser.close().catch(() => {});
  const sourcePath = video ? await video.path().catch(() => undefined) : undefined;
  await stopChildren();
  if (sourcePath) {
    const output = path.join(outputDir, complete ? "devrelay-continuity-live.webm" : "devrelay-continuity-live.partial.webm");
    await copyFile(sourcePath, output);
    const file = await stat(output);
    console.log(`Recording ${complete ? "completed" : "partial"}: ${output}`);
    console.log(`Captured at ${width}x${height} WebM; ${file.size} bytes. Duration must be measured with an available media tool.`);
  } else console.log("No video file was finalized.");
  if (!complete) process.exitCode = 1;
}
