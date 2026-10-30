// Live-only continuity-pipeline recording. This script makes exactly one plan request.
// Run only after obtaining separate explicit authorization for that paid request.
import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { randomBytes } from "node:crypto";
import { access, mkdir, copyFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

if (process.env.DEVRELAY_LIVE_DEMO_AUTHORIZED !== "YES") {
  throw new Error("Set DEVRELAY_LIVE_DEMO_AUTHORIZED=YES only after separately authorizing one live planning request.");
}
// The backend loads the credential from its local .env when it starts from the
// repository root. Keep it out of the Node/Next process and verify presence via
// the backend's sanitized inference-status response before any planning call.

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.resolve(frontendDir, "..");
const width = 1920;
const height = 1080;
const siteOrigin = "http://127.0.0.1:3000";
const apiOrigin = "http://127.0.0.1:8001";
const taskDescription = "Investigate why Northstar's 02:00 ingestion job can report success while publishing fewer rows than arrived when an inbound record has a malformed amount. Trace accepted and rejected counts through orchestration to the publish decision; verify whether the configured validity threshold and run status are enforced. Distinguish directly observed behavior from assumptions. Provide no more than 3 investigation steps, 3 regression tests, and citations to the strongest source excerpts. Do not invent a partial-batch policy, modify repository files, or execute code.";
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
  NEBIUS_MAX_OUTPUT_TOKENS: "2048",
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

async function addRecordingPointer(page) {
  await page.addStyleTag({ content: `
    html, body, body * { cursor: none !important; }
    #devrelay-recording-pointer { position: fixed; left: 0; top: 0; z-index: 2147483647;
      width: 15px; height: 15px; border: 2px solid #fff; border-radius: 50%;
      background: #c47d20; box-shadow: 0 0 0 3px rgba(28,48,42,.88), 0 2px 8px rgba(0,0,0,.45);
      transform: translate(-50%,-50%); pointer-events: none; transition: width 100ms, height 100ms; }
    #devrelay-recording-pointer::before { content: ""; position: absolute; inset: -13px; border: 2px solid rgba(196,125,32,.78); border-radius: 50%; }
    #devrelay-recording-pointer.is-clicking { width: 21px; height: 21px; background: #16765f; }
    #devrelay-recording-pointer.is-clicking::before { inset: -19px; border-color: #16765f; }
  ` });
  await page.evaluate(() => {
    const pointer = document.createElement("div");
    pointer.id = "devrelay-recording-pointer";
    document.body.append(pointer);
    document.addEventListener("mousemove", (event) => {
      pointer.style.left = `${event.clientX}px`;
      pointer.style.top = `${event.clientY}px`;
    }, true);
    document.addEventListener("mousedown", () => {
      pointer.classList.add("is-clicking");
      window.setTimeout(() => pointer.classList.remove("is-clicking"), 240);
    }, true);
  });
  await page.mouse.move(960, 100);
}

async function circleTarget(page, locator, radius = 34) {
  await locator.scrollIntoViewIfNeeded();
  const bounds = await locator.boundingBox();
  if (!bounds) throw new Error("A visible demo target could not be located.");
  const centerX = bounds.x + bounds.width / 2;
  const centerY = bounds.y + bounds.height / 2;
  for (let index = 0; index <= 12; index += 1) {
    const angle = (index / 12) * Math.PI * 2;
    await page.mouse.move(centerX + Math.cos(angle) * radius, centerY + Math.sin(angle) * radius, { steps: 2 });
    await delay(45);
  }
  await page.mouse.move(centerX, centerY, { steps: 4 });
  await delay(180);
}

async function guidedClick(page, locator) {
  await circleTarget(page, locator);
  await locator.click();
}

async function readJsonResponse(response, label) {
  let body;
  try { body = await response.json(); }
  catch { throw new Error(`${label} returned non-JSON content (HTTP ${response.status}).`); }
  if (!response.ok) {
    const code = typeof body?.error?.code === "string" ? body.error.code : "unknown_error";
    throw new Error(`${label} failed (HTTP ${response.status}, ${code}).`);
  }
  return body;
}

async function showRejectedAttempt() {
  const attempt = await page.evaluate(async () => {
    const response = await fetch("/api/backend/api/v1/inference/attempts?limit=1&repository_id=continuity-pipeline-fixture", { cache: "no-store" });
    if (!response.ok) return null;
    const history = await response.json();
    return history.records?.[0] ?? null;
  }).catch(() => null);
  const safeAttempt = attempt && {
    provider: attempt.provider,
    model: attempt.model,
    request_status: attempt.request_status,
    provider_http_status: attempt.provider_http_status,
    finish_reason: attempt.finish_reason,
    plan_validation_status: attempt.plan_validation_status,
    plan_validation_failure_category: attempt.plan_validation_failure_category,
    citation_validation_status: attempt.citation_validation_status,
    input_tokens: attempt.input_tokens,
    output_tokens: attempt.output_tokens,
    duration_ms: attempt.duration_ms,
    estimated_cost_usd: attempt.estimated_cost_usd,
  };
  if (safeAttempt) console.log(JSON.stringify({ stage: "plan_rejected_or_unverified", ...safeAttempt }));
  const failureBanner = page.locator(".error-banner[role=alert]");
  if (await failureBanner.count()) await failureBanner.scrollIntoViewIfNeeded();
  const historyHeading = page.getByRole("heading", { name: "Inference runs and estimated cost", exact: true });
  if (safeAttempt) {
    await historyHeading.scrollIntoViewIfNeeded();
    const runRow = page.locator(".usage-table tbody tr").first();
    await runRow.waitFor({ timeout: 8_000 }).catch(() => {});
    await runRow.scrollIntoViewIfNeeded().catch(() => {});
    const visibleCategory = safeAttempt.plan_validation_failure_category?.replaceAll("_", " ");
    if (safeAttempt.plan_validation_status === "failed" && visibleCategory) {
      await page.getByText(`Rejected: ${visibleCategory}`, { exact: true }).waitFor({ timeout: 5_000 }).catch(() => {});
    }
  }
  await delay(8_000);
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

  const chromiumPath = process.env.DEVRELAY_CHROMIUM_EXECUTABLE;
  if (chromiumPath) await access(chromiumPath);
  browser = await chromium.launch(chromiumPath
    ? { headless: true, executablePath: chromiumPath }
    : { headless: true });
  context = await browser.newContext({
    viewport: { width, height }, screen: { width, height }, deviceScaleFactor: 1,
    httpCredentials: { username: "continuity-recording", password: recordingPassword },
    recordVideo: { dir: browserVideoDir, size: { width, height } },
  });
  page = await context.newPage();
  page.setDefaultTimeout(20_000);
  await page.goto(siteOrigin, { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.getByRole("heading", { name: /Carry the investigation forward/i }).waitFor();
  await page.getByText("FastAPI is responding", { exact: true }).waitFor();
  if (await page.getByRole("combobox", { name: "Select configured repository" }).inputValue() !== "continuity-pipeline-fixture") {
    throw new Error("The dashboard did not select the authorized synthetic continuity fixture.");
  }
  await addRecordingPointer(page);

  const startedAt = Date.now();
  // 0:00–0:25 — Set up the handoff problem and authorized workspace.
  await circleTarget(page, page.getByRole("heading", { name: "Successful runs are publishing fewer rows than arrived." }));
  await waitUntil(startedAt, 25_000);
  // 0:25–0:50 — Static repository analysis and module/import discovery.
  await guidedClick(page, page.getByRole("button", { name: /Analyze repository/ }));
  await page.getByText("Analysis complete", { exact: false }).waitFor();
  await guidedClick(page, page.getByText("Imports & dependency manifests", { exact: false }));
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
  const taskInput = page.locator("#task-description");
  await taskInput.fill("");
  await taskInput.click({ position: { x: 12, y: 12 } });
  await circleTarget(page, taskInput, 48);
  await taskInput.pressSequentially(taskDescription, { delay: 4, timeout: 45_000 });
  const planResponsePromise = page.waitForResponse((response) =>
    response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/api/backend/api/v1/tasks/plan"),
    { timeout: 90_000 },
  );
  await guidedClick(page, page.getByRole("button", { name: /Generate plan/ }));
  let planResponse;
  try {
    planResponse = await planResponsePromise;
  } catch {
    await showRejectedAttempt();
    throw new Error("The single planning request did not produce a browser response within 90 seconds; no retry was made.");
  }
  let plan;
  try {
    plan = await readJsonResponse(planResponse, "Planning request");
  } catch (error) {
    await page.getByRole("alert").waitFor({ timeout: 5_000 }).catch(() => {});
    await showRejectedAttempt();
    throw error;
  }
  if (planRequestCount !== 1) throw new Error("The live plan request count was not exactly one; recording stopped without another request.");
  const submittedPlan = JSON.parse(planRequestBody ?? "{}");
  if (submittedPlan.repository_id !== "continuity-pipeline-fixture" || submittedPlan.task_description !== taskDescription) {
    throw new Error("The submitted planning request did not match the configured synthetic scenario.");
  }
  const diagnostics = plan.inference_diagnostics;
  if (plan.provider !== "nebius" || plan.is_mock !== false || diagnostics?.model !== "nvidia/Nemotron-3_5-Lightning") {
    await showRejectedAttempt();
    throw new Error("The returned plan did not confirm the authorized provider and model; recording stopped.");
  }
  await page.locator(".plan-result").waitFor();
  await page.getByText("nvidia/Nemotron-3_5-Lightning", { exact: true }).waitFor();
  if (plan.status !== "planned" || plan.unsupported_references.length !== 0 ||
      plan.source_references.length === 0 || plan.source_excerpts.length === 0) {
    await delay(12_000);
    throw new Error(`The one live response was not an evidence-complete plan (status=${plan.status}, verified=${plan.source_references.length}, unsupported=${plan.unsupported_references.length}); no retry was made.`);
  }
  if (plan.human_approval_required !== true || plan.execution_status !== "not_started") {
    throw new Error("The plan did not preserve the human-review and not-started execution boundaries.");
  }
  console.log(JSON.stringify({
    stage: "validated_live_plan",
    provider: plan.provider,
    model: diagnostics.model,
    status: plan.status,
    finish_reason: diagnostics.finish_reason,
    latency_ms: diagnostics.latency_ms,
    usage: diagnostics.usage,
    verified_references: plan.source_references.length,
    unsupported_references: plan.unsupported_references.length,
    findings: plan.findings.length,
    steps: plan.implementation_steps.length,
    human_approval_required: plan.human_approval_required,
    execution_status: plan.execution_status,
  }));
  const renderedDiagnostics = page.locator(".inference-diagnostics").filter({ hasText: diagnostics.model });
  await renderedDiagnostics.waitFor();
  await circleTarget(page, renderedDiagnostics);
  if (await page.getByText("MOCK MODE", { exact: false }).count() > 0) throw new Error("A mock response appeared in the live recording; recording stopped.");
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
  await circleTarget(page, evidence);
  const firstExcerpt = page.locator(".plan-result details.inspect-details").first();
  await firstExcerpt.waitFor();
  await guidedClick(page, firstExcerpt.locator("summary"));
  await firstExcerpt.locator("pre code").waitFor();
  await page.getByText("Findings", { exact: true }).scrollIntoViewIfNeeded();
  await circleTarget(page, page.getByText("Findings", { exact: true }));
  await waitUntil(startedAt, 110_000);
  // 1:50–2:15 — Keep plan review distinct from code approval.
  await page.getByRole("heading", { name: "Plan review" }).scrollIntoViewIfNeeded();
  await page.getByText("This records review of the investigation plan only.", { exact: false }).waitFor();
  await waitUntil(startedAt, 135_000);
  // 2:15–2:40 — Create and show a plan-only handoff, explicitly still unreviewed.
  await guidedClick(page, page.getByRole("button", { name: "Create plan-only handoff" }));
  await page.getByText("Unreviewed handoff · awaiting human review", { exact: true }).waitFor();
  await page.getByText("Runtime validation:", { exact: false }).scrollIntoViewIfNeeded();
  await waitUntil(startedAt, 160_000);
  // 2:40–2:50 — Show this real run's locally recorded token/cost estimate.
  await page.getByRole("link", { name: "Run history", exact: true }).click();
  await page.getByRole("button", { name: "Refresh history", exact: true }).click();
  const recordedRun = page.locator(".usage-table tbody tr").filter({ hasText: plan.task_id.slice(0, 8) });
  await recordedRun.waitFor();
  await recordedRun.getByText("Nebius Token Factory", { exact: true }).waitFor();
  await recordedRun.scrollIntoViewIfNeeded();
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
