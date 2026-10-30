// Local, deterministic continuity-pipeline recording. This script never enables
// Nebius inference and never executes code from the synthetic repository.
import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { createHash, randomBytes } from "node:crypto";
import { access, mkdir, copyFile, readdir, readFile, stat, lstat, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.resolve(frontendDir, "..");
const width = 1920;
const height = 1080;
const siteOrigin = "http://127.0.0.1:3000";
const apiOrigin = "http://127.0.0.1:8001";
const repositoryId = "continuity-pipeline-fixture";
const taskDescription = "Investigate why the 02:00 ingestion job in the nightly continuity pipeline can publish a successful report with fewer rows than the inbound batch. Trace orchestration, validation, transformation, retry, configuration, and publication behavior across the repository. Propose safe investigation steps, evidence to collect, and regression checks. Do not assume the root cause, change repository files, or execute code.";
const runId = new Date().toISOString().replaceAll(":", "-").replaceAll(".", "-");
const outputDir = path.join(repositoryRoot, "demo-recordings", `continuity-mock-${runId}`);
const browserVideoDir = path.join(outputDir, "browser-video");
const fixturePath = path.join(repositoryRoot, "tests", "fixtures", "continuity_pipeline").replaceAll("\\", "/");
const recordingPassword = randomBytes(32).toString("base64url");
const children = [];
let browser;
let context;
let page;
let video;
let complete = false;
let workflowReport = {
  provider: "mock",
  model: "devrelay-mock-v1",
  live_inference_enabled: false,
  repository_id: repositoryId,
  plan_status: null,
  verified_reference_count: 0,
  unsupported_reference_count: 0,
  source_excerpt_count: 0,
  plan_findings_count: 0,
  handoff_review_state: null,
  human_approval_required: true,
  execution_status: "not_started",
  runtime_validation_status: "not_run",
  fixture_unchanged: null,
};

const backendEnvironment = {
  ...process.env,
  ENVIRONMENT: "development",
  INFERENCE_PROVIDER: "mock",
  NEBIUS_LIVE_INFERENCE_ENABLED: "false",
  NEBIUS_API_KEY: "",
  NEBIUS_TIMEOUT_SECONDS: "30",
  TASK_PLANNING_TIMEOUT_SECONDS: "60",
  AUTHORIZED_REPOSITORIES: JSON.stringify({ [repositoryId]: fixturePath }),
  ENABLE_LOCAL_REVIEWS: "true",
  ENABLE_ISOLATED_RUNTIME_VALIDATION: "false",
  INFERENCE_TELEMETRY_DB_PATH: path.join(outputDir, "inference-telemetry.sqlite3"),
  DEMO_AUTH_USERNAME: "continuity-recording",
  DEMO_AUTH_PASSWORD: recordingPassword,
  DEMO_AUTH_ORIGIN: siteOrigin,
  BACKEND_API_URL: apiOrigin,
  NEXT_PUBLIC_REPOSITORY_IDS: repositoryId,
  NEXT_PUBLIC_LOCAL_REVIEWER_ID: "demo_reviewer",
  NEXT_PUBLIC_EXECUTION_AUTHORIZER_ID: "local_authorizer",
  NEXT_TELEMETRY_DISABLED: "1",
};
const frontendEnvironment = {
  ...backendEnvironment,
  INFERENCE_PROVIDER: "mock",
  NEBIUS_LIVE_INFERENCE_ENABLED: "false",
  NEBIUS_API_KEY: "",
};
delete frontendEnvironment.AUTHORIZED_REPOSITORIES;

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function assertPortFree(port) {
  await new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", (error) => error.code === "EADDRINUSE"
      ? reject(new Error(`Loopback port ${port} is already in use; no existing process was stopped.`))
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
    } catch { /* bounded local readiness probe */ }
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
    #devrelay-recording-pointer::before { content: ""; position: absolute; inset: -13px; border: 2px solid rgba(196,125,32,.78);
      border-radius: 50%; }
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
    document.addEventListener("mouseleave", () => { pointer.style.opacity = "0"; }, true);
    document.addEventListener("mouseenter", () => { pointer.style.opacity = "1"; }, true);
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

async function guidedClick(page, locator, { circle = false } = {}) {
  await locator.scrollIntoViewIfNeeded();
  if (circle) await circleTarget(page, locator);
  await locator.click();
}

async function stopChildren() {
  for (const child of [...children].reverse()) {
    if (child.exitCode === null && child.signalCode === null) child.kill();
  }
  await Promise.all(children.map((child) => new Promise((resolve) => {
    if (child.exitCode !== null || child.signalCode !== null) return resolve();
    const timer = setTimeout(resolve, 4_000);
    child.once("exit", () => { clearTimeout(timer); resolve(); });
  })));
}

async function hashFixture(root) {
  const files = [];
  async function visit(directory) {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const absolute = path.join(directory, entry.name);
      const info = await lstat(absolute);
      if (info.isSymbolicLink()) continue;
      if (info.isDirectory()) await visit(absolute);
      else if (info.isFile()) {
        const relative = path.relative(root, absolute).replaceAll("\\", "/");
        const bytes = await readFile(absolute);
        files.push([relative, createHash("sha256").update(bytes).digest("hex")]);
      }
    }
  }
  await visit(root);
  files.sort(([left], [right]) => left.localeCompare(right));
  return createHash("sha256").update(JSON.stringify(files)).digest("hex");
}

async function responseJson(response, label) {
  let body;
  try { body = await response.json(); } catch { throw new Error(`${label} returned a non-JSON response (HTTP ${response.status}).`); }
  if (!response.ok) {
    const code = typeof body?.error?.code === "string" ? body.error.code : "unknown_error";
    throw new Error(`${label} failed (HTTP ${response.status}, ${code}).`);
  }
  return body;
}

async function run() {
  await assertPortFree(8001);
  await assertPortFree(3000);
  await access(fixturePath);
  await mkdir(browserVideoDir, { recursive: true });
  const beforeFixtureHash = await hashFixture(fixturePath);
  const python = path.join(repositoryRoot, ".venv", "Scripts", "python.exe");
  const nextBin = path.join(frontendDir, "node_modules", "next", "dist", "bin", "next");
  const node = process.execPath;

  console.log("Building the production dashboard with mock inference, an empty API-key override, and the synthetic fixture only.");
  await runCommand(node, [nextBin, "build", "--webpack"], frontendDir, frontendEnvironment, "Frontend production build");
  console.log("Starting FastAPI and Next.js on loopback with live inference disabled.");
  launch(python, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001", "--workers", "1"], repositoryRoot, backendEnvironment);
  await waitFor(`${apiOrigin}/health`, "FastAPI health endpoint");
  const statusResponse = await fetch(`${apiOrigin}/api/v1/inference/status`);
  const status = await responseJson(statusResponse, "Mock-provider status check");
  if (status.provider !== "mock" || status.live_inference_enabled !== false || status.credentials_configured !== false) {
    throw new Error("Offline provider preflight failed; recording stopped before browser workflow.");
  }
  workflowReport.live_inference_enabled = status.live_inference_enabled;

  launch(node, [nextBin, "start", "--hostname", "127.0.0.1", "--port", "3000"], frontendDir, frontendEnvironment);
  const authorization = Buffer.from(`continuity-recording:${recordingPassword}`).toString("base64");
  await waitFor(`${siteOrigin}/`, "Authenticated dashboard", { Authorization: `Basic ${authorization}` });

  const chromiumPath = process.env.DEVRELAY_CHROMIUM_EXECUTABLE;
  if (chromiumPath) await access(chromiumPath);
  browser = await chromium.launch(chromiumPath ? { headless: true, executablePath: chromiumPath } : { headless: true });
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
  if (await page.getByRole("combobox", { name: "Select configured repository" }).inputValue() !== repositoryId) {
    throw new Error("The dashboard did not select the synthetic continuity fixture.");
  }
  // The fixture preloads a suggested incident description. Clear it before
  // recording so the audience sees the request entered live, character by character.
  const taskInput = page.locator("#task-description");
  await taskInput.fill("");
  await page.waitForFunction(() => {
    const input = document.querySelector("#task-description");
    return input instanceof HTMLTextAreaElement && input.value === "";
  });
  await addRecordingPointer(page);

  const startedAt = Date.now();
  console.log("Recording the authenticated dashboard at 1920x1080; inference provider is mock.");
  await waitUntil(startedAt, 20_000);

  // 0:20–0:45 — Static analysis of the authorized synthetic repository.
  const analysisResponsePromise = page.waitForResponse((response) =>
    response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/api/backend/api/v1/repositories/analyze"),
    { timeout: 20_000 },
  );
  await guidedClick(page, page.getByRole("button", { name: /Analyze repository/ }), { circle: true });
  const analysisResponse = await analysisResponsePromise;
  const analysis = await responseJson(analysisResponse, "Repository analysis");
  if (analysis.summary.repository_id !== repositoryId || analysis.files.length === 0) {
    throw new Error("Repository analysis did not return the expected synthetic source inventory.");
  }
  await page.getByText("Analysis complete", { exact: false }).waitFor();
  await guidedClick(page, page.getByText("Imports & dependency manifests", { exact: false }), { circle: true });
  await page.getByText("requirements.txt", { exact: true }).waitFor();
  await waitUntil(startedAt, 45_000);

  // 0:45–1:15 — A deterministic mock plan for the continuity investigation.
  await taskInput.scrollIntoViewIfNeeded();
  await circleTarget(page, taskInput, 48);
  await taskInput.click({ position: { x: 12, y: 12 } });
  await taskInput.pressSequentially(taskDescription, { delay: 12 });
  const planResponsePromise = page.waitForResponse((response) =>
    response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/api/backend/api/v1/tasks/plan"),
    { timeout: 25_000 },
  );
  await guidedClick(page, page.getByRole("button", { name: /Generate plan/ }), { circle: true });
  const planResponse = await planResponsePromise;
  const plan = await responseJson(planResponse, "Mock planning request");
  workflowReport.plan_status = plan.status;
  workflowReport.verified_reference_count = plan.source_references.length;
  workflowReport.unsupported_reference_count = plan.unsupported_references.length;
  workflowReport.source_excerpt_count = plan.source_excerpts.length;
  workflowReport.plan_findings_count = plan.findings.length;
  if (plan.status !== "planned" || plan.provider !== "mock" || plan.is_mock !== true ||
      plan.inference_diagnostics?.model !== "devrelay-mock-v1" || plan.unsupported_references.length !== 0 ||
      plan.source_references.length === 0 || plan.source_excerpts.length === 0 ||
      plan.human_approval_required !== true || plan.execution_status !== "not_started") {
    throw new Error("The deterministic plan did not meet the expected mock, evidence, and safety checks.");
  }
  await page.getByText("Deterministic mock result — not AI-generated.", { exact: true }).waitFor();
  await page.getByText("This response was not generated by NVIDIA Nemotron.", { exact: true }).waitFor();
  await page.getByText("Execution has not started", { exact: true }).waitFor();
  await circleTarget(page, page.getByText("Deterministic mock result — not AI-generated.", { exact: true }));
  await waitUntil(startedAt, 75_000);

  // 1:15–1:45 — Show validated citations and a real source excerpt.
  const evidence = page.locator(".plan-result .data-section").filter({
    has: page.getByRole("heading", { name: "Supporting evidence", exact: true }),
  });
  await evidence.waitFor();
  await circleTarget(page, evidence.getByRole("heading", { name: "Supporting evidence", exact: true }));
  const excerpt = page.locator(".plan-result details.inspect-details").first();
  await excerpt.waitFor();
  await guidedClick(page, excerpt.locator("summary"), { circle: true });
  await excerpt.locator("pre code").waitFor();
  await waitUntil(startedAt, 105_000);

  // 1:45–2:05 — Show the local plan-review boundary without inventing a decision.
  await circleTarget(page, page.getByRole("heading", { name: "Plan review", exact: true }));
  await page.getByText("This records review of the investigation plan only.", { exact: true }).waitFor();
  await page.getByText("Reviewer labels are unverified local-development labels.", { exact: false }).waitFor();
  await waitUntil(startedAt, 125_000);

  // 2:05–2:35 — Create an accurate, explicitly unreviewed plan-only handoff.
  const handoffResponsePromise = page.waitForResponse((response) =>
    response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/api/backend/api/v1/handoffs/plans"),
    { timeout: 20_000 },
  );
  await guidedClick(page, page.getByRole("button", { name: "Create plan-only handoff" }), { circle: true });
  const handoffResponse = await handoffResponsePromise;
  const handoff = await responseJson(handoffResponse, "Plan-only handoff");
  workflowReport.handoff_review_state = handoff.review_state;
  if (handoff.handoff_type !== "plan_only" || handoff.planning_is_mock !== true ||
      handoff.review_state !== "awaiting_review" || handoff.human_approval_required !== true ||
      handoff.execution_status !== "not_started" || handoff.runtime_validation_status !== "not_run") {
    throw new Error("The handoff response did not preserve mock provenance, review, and execution boundaries.");
  }
  await page.getByText("Unreviewed handoff · awaiting human review", { exact: true }).waitFor();
  await page.getByText("No findings were supplied by the plan.", { exact: true }).waitFor();
  await circleTarget(page, page.getByText("Human review required:", { exact: false }));
  await waitUntil(startedAt, 155_000);

  // 2:35–2:50 — End on the honest limitations and no-execution status.
  const mockDisclosure = page.locator(".handoff-result [role='note']");
  await mockDisclosure.waitFor();
  await circleTarget(page, mockDisclosure);
  const runtimeStatus = page.getByText("Runtime validation:", { exact: false });
  await circleTarget(page, runtimeStatus);
  await waitUntil(startedAt, 170_000);

  workflowReport.fixture_unchanged = beforeFixtureHash === await hashFixture(fixturePath);
  if (!workflowReport.fixture_unchanged) throw new Error("Synthetic fixture file hashes changed during the read-only workflow.");
  complete = true;
}

try {
  await run();
} catch (error) {
  console.error(`Mock continuity recording stopped: ${error instanceof Error ? error.message : "an unexpected workflow error occurred"}`);
} finally {
  if (page) video = page.video();
  if (context) await context.close().catch(() => {});
  if (browser) await browser.close().catch(() => {});
  const sourcePath = video ? await video.path().catch(() => undefined) : undefined;
  await stopChildren();
  if (sourcePath) {
    const output = path.join(outputDir, complete ? "devrelay-continuity-mock.webm" : "devrelay-continuity-mock.partial.webm");
    await copyFile(sourcePath, output);
    const file = await stat(output);
    workflowReport.recording_complete = complete;
    workflowReport.file_bytes = file.size;
    workflowReport.resolution = `${width}x${height}`;
    workflowReport.scripted_duration_seconds = complete ? 170 : null;
    await writeFile(path.join(outputDir, "recording-report.json"), `${JSON.stringify(workflowReport, null, 2)}\n`, { flag: "w" });
    console.log(`Recording ${complete ? "completed" : "partial"}: ${output}`);
    console.log(`Mock workflow summary: ${JSON.stringify(workflowReport)}`);
  } else console.log("No video file was finalized.");
  if (!complete) process.exitCode = 1;
}
