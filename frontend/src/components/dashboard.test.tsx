import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Dashboard from "@/components/dashboard";
import { planTask } from "@/lib/api";
import type { SandboxReadiness } from "@/lib/types";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const disabledReviewStatus = { enabled: false, environment: "development", identity_status: "unverified_local_development" };
const enabledReviewStatus = { ...disabledReviewStatus, enabled: true };
const disabledSandboxReadiness = {
  enabled: false, environment: "development", available: false, status: "disabled" as const,
  test_case: "calculator_unit_tests" as const, test_command_id: "calculator_pytest_suite_v1",
  checks: [{ name: "development_feature_flag", status: "failed" as const, detail: "Feature flag is disabled." }],
  limitations: ["No repository test code is run on the host."],
};

function routeFetch(responses: Record<string, unknown | Response>, reviewStatus = disabledReviewStatus, sandboxReadiness: SandboxReadiness = disabledSandboxReadiness) {
  return vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>((input) => {
    const key = String(input).replace("/api/backend/", "");
    const value = key === "health" ? { status: "ok" } : key === "api/v1/reviews/status" ? reviewStatus : key === "api/v1/runtime-validation/readiness" ? sandboxReadiness : responses[key];
    return Promise.resolve(value instanceof Response ? value : jsonResponse(value ?? {}));
  });
}

const repositoryAnalysis = {
  summary: {
    repository_id: "planning-fixture", file_count: 5, python_file_count: 3,
    module_count: 3, function_count: 3, class_count: 0, import_count: 1,
    dependency_count: 1, test_file_count: 1, duration_ms: 3.4,
  },
  files: [{ path: "package/calculator.py", size_bytes: 62, modified_at: "2026-01-01T00:00:00Z", category: "python" }],
  modules: [{ name: "package.calculator", path: "package/calculator.py", imports: 0, functions: 1, classes: 0 }],
  functions: [{ name: "divide", qualified_name: "divide", kind: "function", source: { path: "package/calculator.py", line: 1, end_line: 2 } }],
  classes: [],
  imports: [{ source_path: "tests/test_calculator.py", source_module: "tests.test_calculator", line: 1, imported_module: "package.calculator", imported_names: ["divide"], kind: "from_import" }],
  dependency_manifests: [{ path: "requirements.txt", format: "requirements.txt", dependencies: ["pytest>=8"] }],
  test_files: ["tests/test_calculator.py"], readme_files: [], configuration_files: [], warnings: [],
};

const taskPlan = {
  task_id: "plan-test", repository_id: "planning-fixture", task_description: "Fix the division by zero defect",
  status: "planned", relevant_files: ["package/calculator.py", "tests/test_calculator.py"],
  source_references: [{ path: "package/calculator.py", line: 1, end_line: 2 }],
  implementation_steps: [{ step: 1, description: "Inspect division behavior and add a regression test.", source_references: [{ path: "package/calculator.py", line: 1, end_line: 2 }] }],
  expected_code_changes: [{ path: "package/calculator.py", description: "Guard zero divisor after approval." }],
  risks: ["Confirm expected zero-divisor behavior."], dependencies: [],
  validation_requirements: ["Run tests/test_calculator.py"], human_approval_required: true,
  execution_status: "not_started", assumptions: [], unsupported_references: [], provider: "mock", is_mock: true,
  inference_diagnostics: { provider: "mock", model: "devrelay-mock-v1", is_mock: true, completion_status: "completed", finish_reason: "mock_complete", model_reported_by_provider: true, latency_ms: null, usage: null },
};

const liveTaskPlan = {
  ...taskPlan,
  provider: "nebius" as const,
  is_mock: false,
  inference_diagnostics: {
    provider: "nebius" as const, model: "nvidia/Nemotron-3_5-Lightning", is_mock: false,
    completion_status: "completed" as const, finish_reason: "stop", model_reported_by_provider: true,
    latency_ms: 2431,
    usage: { input_tokens: 280, output_tokens: 192, reasoning_tokens: 72, total_tokens: 472 },
  },
};

const codeProposal = {
  proposal_id: "2b7a47fb-5c38-481a-a35c-b4f4cc0d7047", repository_id: "planning-fixture",
  originating_task_id: "plan-test", task_description: "Fix the division by zero defect",
  originating_plan_provider: "nebius", transformation_id: "calculator-zero-denominator-value-error-v1",
  target_files: [{ path: "package/calculator.py", original_sha256: "a".repeat(64), source_reference: { path: "package/calculator.py", line: 1, end_line: 2 } }],
  proposed_change_summary: "Raise ValueError when denominator is zero.",
  unified_diff: "--- a/package/calculator.py\n+++ b/package/calculator.py\n@@ -1,2 +1,4 @@\n def divide(numerator, denominator):\n+    if denominator == 0:\n+        raise ValueError('denominator must not be zero')\n     return numerator / denominator\n",
  diff_sha256: "b".repeat(64),
  risk_classification: "low", validation_findings: [
    { check: "python_syntax", status: "passed", detail: "AST parse passed without execution." },
    { check: "runtime_isolation", status: "not_run", detail: "No trusted isolated executor is configured." },
  ], static_validation_status: "passed", runtime_validation_status: "not_run",
  runtime_validation_reason: "No trusted isolated executor is configured; repository code was not executed on the host.",
  provider: "mock", is_mock: true, created_at: "2026-10-21T00:00:00Z",
  lifecycle_state: "awaiting_review", human_approval_required: true, version: 1,
};

const handoffReport = {
  report_id: "550e8400-e29b-41d4-a716-446655440000", generated_at: "2026-10-21T00:00:00Z", repository_id: "planning-fixture",
  task: { task_id: "plan-test", objective: taskPlan.task_description, current_progress: "A plan and static proposal are available; no review decision has been recorded.", task_status: "planned", planning_provider: "nebius", proposal_lifecycle_state: "awaiting_review", proposal_version: 1, relevant_files: taskPlan.relevant_files, source_references: taskPlan.source_references, planned_steps: ["1. Inspect division"], planned_validation_requirements: ["Run tests"] },
  technical_understanding: { analysis_summary: repositoryAnalysis.summary, relevant_modules: repositoryAnalysis.modules, relevant_functions: ["divide (package/calculator.py:1)"], relevant_classes: [], relevant_imports: [], dependency_manifests: ["requirements.txt: pytest>=8"], verified_context: ["Current static scan found one Python module."], analysis_warnings: [] },
  proposed_change: { summary: codeProposal.proposed_change_summary, target_files: codeProposal.target_files, diff_sha256: codeProposal.diff_sha256, static_validation_status: "passed", validation_findings: codeProposal.validation_findings, provider: "mock", is_mock: true, originating_plan_provider: "nebius", transformation_id: "calculator-zero-denominator-value-error-v1", source_revision_status: "current" },
  human_decisions: [], outstanding_questions: [],
  validation_and_risks: { static_checks: codeProposal.validation_findings, runtime_tests_status: "not_run", runtime_tests_reason: codeProposal.runtime_validation_reason, risks: taskPlan.risks, assumptions: [], unresolved_dependencies: [], unsupported_evidence: [] },
  runtime_execution: { status: "not_run", sandbox_summary: "No trusted sandbox configured.", evidence_id: null, test_case: "calculator_unit_tests", test_command_id: "calculator_pytest_suite_v1", exit_code: null, duration_ms: null, test_results: [], source_sha256: codeProposal.target_files[0].original_sha256, diff_sha256: codeProposal.diff_sha256, remaining_work: ["Configure a trusted sandbox."] },
  next_engineer_actions: [{ action: "A local reviewer should inspect the proposal.", required_approval: true, status: "pending" }],
  provenance_note: "Static evidence and mock-generated proposal. No code executed.", provider: "mock", is_mock: true,
};

describe("DevRelay dashboard", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", routeFetch({}));
  });

  it("renders the dashboard identity, tools, and unavailable roadmap", async () => {
    render(<Dashboard />);
    expect(screen.getByRole("heading", { name: /good work starts with context/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /repository intelligence/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /engineering task planner/i })).toBeInTheDocument();
    expect(await screen.findByText("FastAPI is responding")).toBeInTheDocument();
    expect(screen.getByText("Safe code proposals")).toBeInTheDocument();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
  });

  it("shows backend connectivity failure and prevents unavailable actions", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<Dashboard />);
    expect(await screen.findByText("Cannot reach the dashboard API proxy. Check that the frontend is running.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /analyze repository/i })).toBeDisabled();
  });

  it("runs repository analysis and displays modules, symbols, imports, and warnings", async () => {
    const fetchMock = routeFetch({ "api/v1/repositories/analyze": repositoryAnalysis });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<Dashboard />);
    await screen.findByText("FastAPI is responding");
    await user.click(screen.getByRole("button", { name: /analyze repository/i }));
    expect(await screen.findByText("package.calculator")).toBeInTheDocument();
    expect(screen.getByText("3.4 ms")).toBeInTheDocument();
    const symbols = screen.getByText(/Functions, classes & source references/).closest("details");
    if (!symbols) throw new Error("Symbols detail section was not rendered");
    await user.click(within(symbols).getByText(/Functions, classes/));
    expect(await within(symbols).findByText("divide")).toBeInTheDocument();
    const imports = screen.getByText(/Imports & dependency manifests/).closest("details");
    if (!imports) throw new Error("Imports detail section was not rendered");
    await user.click(within(imports).getByText(/Imports & dependency manifests/));
    expect(await within(imports).findByText(/package\.calculator/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/backend/api/v1/repositories/analyze", expect.objectContaining({ method: "POST" }));
  });

  it("submits a planning task and clearly labels deterministic mock output", async () => {
    const fetchMock = routeFetch({ "api/v1/tasks/plan": taskPlan });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<Dashboard />);
    await screen.findByText("FastAPI is responding");
    await user.type(screen.getByLabelText("What needs attention?"), "Fix the division by zero defect");
    await user.click(screen.getByRole("button", { name: /generate plan/i }));
    expect(await screen.findByText("MOCK MODE — Simulated inference for development testing.")).toBeInTheDocument();
    expect(screen.getByText("This response was not generated by NVIDIA Nemotron.")).toBeInTheDocument();
    expect(screen.getByText("Deterministic mock result — not AI-generated.")).toBeInTheDocument();
    expect(screen.getByText("Human approval required")).toBeInTheDocument();
    expect(screen.getByText("Execution has not started")).toBeInTheDocument();
    expect(screen.getByText("Inspect division behavior and add a regression test.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/backend/api/v1/tasks/plan", expect.objectContaining({ method: "POST" }));
  });

  it("shows genuine provider identity and safe planning diagnostics for a completed live plan", async () => {
    vi.stubGlobal("fetch", routeFetch({ "api/v1/tasks/plan": liveTaskPlan }));
    const user = userEvent.setup();
    render(<Dashboard />);
    await screen.findByText("FastAPI is responding");
    await user.type(screen.getByLabelText("What needs attention?"), "Fix the division by zero defect");
    await user.click(screen.getByRole("button", { name: /generate plan/i }));
    expect(await screen.findByText("AI-generated planning result; source evidence was validated locally.")).toBeInTheDocument();
    expect(screen.getByText("nvidia/Nemotron-3_5-Lightning")).toBeInTheDocument();
    expect(screen.getByText(/Latency: 2431 ms/)).toBeInTheDocument();
    expect(screen.getByText(/reasoning 72/)).toBeInTheDocument();
    expect(screen.queryByText(/chain of thought|internal reasoning/i)).not.toBeInTheDocument();
  });

  it("labels rejected source citations as unverified instead of supporting evidence", async () => {
    const partiallyGroundedPlan = {
      ...liveTaskPlan,
      status: "insufficient_context" as const,
      unsupported_references: ["package/api.py:1", "package/calculator.py:1"],
    };
    vi.stubGlobal("fetch", routeFetch({ "api/v1/tasks/plan": partiallyGroundedPlan }));
    const user = userEvent.setup();
    render(<Dashboard />);
    await screen.findByText("FastAPI is responding");
    await user.type(screen.getByLabelText("What needs attention?"), "Fix the division by zero defect");
    await user.click(screen.getByRole("button", { name: /generate plan/i }));
    expect(await screen.findByText("AI-generated plan; verified evidence is listed separately. Rejected citations are unverified.")).toBeInTheDocument();
    expect(screen.getByText("Unverified citations — rejected by source validation")).toBeInTheDocument();
    expect(screen.getByText("package/api.py:1")).toBeInTheDocument();
    expect(screen.getByText("package/calculator.py:1")).toBeInTheDocument();
    expect(screen.getAllByText("package/calculator.py").length).toBeGreaterThan(0);
  });

  it("continues a Nemotron plan into the deterministic review proposal without apply actions", async () => {
    const fetchMock = routeFetch({ "api/v1/tasks/plan": liveTaskPlan, "api/v1/proposals/create": jsonResponse(codeProposal, 201) });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<Dashboard />);
    await screen.findByText("FastAPI is responding");
    await user.type(screen.getByLabelText("What needs attention?"), "Fix the division by zero defect");
    await user.click(screen.getByRole("button", { name: /generate plan/i }));
    await user.click(await screen.findByRole("button", { name: /generate code proposal/i }));
    expect(await screen.findByRole("heading", { name: "Code change proposal" })).toBeInTheDocument();
    expect(screen.getByText("Review Unavailable")).toBeInTheDocument();
    expect(screen.getByText("Execution disabled")).toBeInTheDocument();
    expect(screen.getByText(/repository tests are never run directly on Windows/i)).toBeInTheDocument();
    expect(screen.getAllByText("Source SHA-256:", { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getByText("Plan provider: nebius")).toBeInTheDocument();
    expect(screen.getByText("Proposal generator: deterministic allowlist")).toBeInTheDocument();
    expect(screen.getByText("Runtime validation: not run")).toBeInTheDocument();
    expect(screen.getByText(/No files were changed, approved, applied, or executed/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /apply|approve/i })).not.toBeInTheDocument();
    const proposalRequest = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/api/v1/proposals/create"));
    expect(JSON.parse(String(proposalRequest?.[1]?.body))).toMatchObject({
      transformation_id: "calculator-zero-denominator-value-error-v1",
    });
  });

  it("renders the generated handoff and exposes Markdown export controls", async () => {
    const completedReport = {
      ...handoffReport,
      task: { ...handoffReport.task, proposal_lifecycle_state: "review_approved", current_progress: "A review decision is recorded; the proposal remains unapplied and unexecuted." },
      human_decisions: [{
        review_id: "review-1", proposal_id: codeProposal.proposal_id, task_id: taskPlan.task_id,
        repository_id: "planning-fixture", decision: "approve", reviewer_identifier: "demo_reviewer",
        reviewer_identity_status: "unverified_local_development", justification: "Reviewed the static diff.",
        timestamp: "2026-10-21T00:00:00Z", proposal_version: 1,
        source_sha256: codeProposal.target_files[0].original_sha256, diff_sha256: codeProposal.diff_sha256,
        proposal_lifecycle_state: "review_approved", evidence_references: codeProposal.target_files.map((item) => item.source_reference),
        static_validation_status: "passed", runtime_validation_status: "not_run", outstanding_questions: [],
      }],
    };
    const fetchMock = routeFetch({
      "api/v1/tasks/plan": taskPlan,
      "api/v1/proposals/create": jsonResponse(codeProposal, 201),
      "api/v1/handoffs": jsonResponse(completedReport, 201),
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<Dashboard />);
    await screen.findByText("FastAPI is responding");
    await user.type(screen.getByLabelText("What needs attention?"), "Fix the division by zero defect");
    await user.click(screen.getByRole("button", { name: /generate plan/i }));
    await user.click(await screen.findByRole("button", { name: /generate code proposal/i }));
    await user.click(await screen.findByRole("button", { name: /generate report/i }));
    expect(await screen.findByText("Engineering handoff report")).toBeInTheDocument();
    expect(screen.getByText("Runtime tests:", { exact: false })).toBeInTheDocument();
    const formattedTimestamp = new Date("2026-10-21T00:00:00Z").toLocaleString();
    expect(screen.getByText(`demo_reviewer (unverified local-development label) · ${formattedTimestamp}`)).toBeInTheDocument();
    expect(screen.getByText("Reviewed the static diff.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy Markdown" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download Markdown" })).toBeInTheDocument();
  });

  it("shows local review controls only when the backend reports the flag enabled", async () => {
    const reviewHistory = {
      proposal_id: codeProposal.proposal_id, current_lifecycle_state: "awaiting_review", current_proposal_version: 1,
      reviews: [], audit_events: [],
    };
    const reviewRecord = {
      review_id: "review-id", proposal_id: codeProposal.proposal_id, task_id: taskPlan.task_id,
      repository_id: "planning-fixture", decision: "approve", reviewer_identifier: "local-reviewer",
      reviewer_identity_status: "unverified_local_development", justification: "Static diff reviewed.",
      timestamp: "2026-10-21T00:00:00Z", proposal_version: 1,
      source_sha256: codeProposal.target_files[0].original_sha256, diff_sha256: codeProposal.diff_sha256,
      proposal_lifecycle_state: "review_approved", evidence_references: codeProposal.target_files.map((item) => item.source_reference),
      static_validation_status: "passed", runtime_validation_status: "not_run", outstanding_questions: [],
    };
    const fetchMock = routeFetch({
      "api/v1/tasks/plan": taskPlan,
      "api/v1/proposals/create": jsonResponse(codeProposal, 201),
      [`api/v1/reviews/${codeProposal.proposal_id}`]: reviewHistory,
      "api/v1/reviews": jsonResponse(reviewRecord, 201),
    }, enabledReviewStatus);
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<Dashboard />);
    await screen.findByText("FastAPI is responding");
    await user.type(screen.getByLabelText("What needs attention?"), "Fix the division by zero defect");
    await user.click(screen.getByRole("button", { name: /generate plan/i }));
    await user.click(await screen.findByRole("button", { name: /generate code proposal/i }));
    expect(await screen.findByText("Local development only.")).toBeInTheDocument();
    const justification = await screen.findByLabelText(/decision justification/i);
    const reviewer = screen.getByLabelText("Local reviewer label");
    await user.clear(reviewer);
    await user.type(reviewer, "demo_reviewer");
    await user.type(justification, "Static diff reviewed.");
    await user.click(screen.getByRole("button", { name: /approve for consideration/i }));
    expect(fetchMock).toHaveBeenCalledWith("/api/backend/api/v1/reviews", expect.objectContaining({ method: "POST" }));
    const submittedReview = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/api/v1/reviews"));
    expect(JSON.parse(String(submittedReview?.[1]?.body))).toMatchObject({ reviewer_identifier: "demo_reviewer" });
    expect(await screen.findByText(/does not apply or execute code/i)).toBeInTheDocument();
    expect(screen.getByText("Review Completed")).toBeInTheDocument();
  });

  it("explains and rejects unsupported reviewer labels before submitting", async () => {
    const fetchMock = routeFetch({
      "api/v1/tasks/plan": taskPlan,
      "api/v1/proposals/create": jsonResponse(codeProposal, 201),
    }, enabledReviewStatus);
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<Dashboard />);
    await screen.findByText("FastAPI is responding");
    await user.type(screen.getByLabelText("What needs attention?"), "Fix the division by zero defect");
    await user.click(screen.getByRole("button", { name: /generate plan/i }));
    await user.click(await screen.findByRole("button", { name: /generate code proposal/i }));

    expect(screen.getByText((_, element) => element?.tagName === "SMALL" && Boolean(element.textContent?.includes("Example: demo_reviewer")))).toBeInTheDocument();
    const reviewer = screen.getByLabelText("Local reviewer label");
    await user.clear(reviewer);
    await user.type(reviewer, "Demo Reviewer");
    expect(await screen.findByRole("alert")).toHaveTextContent("Spaces are not allowed.");
    expect(screen.getByRole("button", { name: /approve for consideration/i })).toBeDisabled();
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/api/v1/reviews"))).toBe(false);
  });

  it("shows a sanitized explanation when the backend rejects a review payload", async () => {
    const fetchMock = routeFetch({
      "api/v1/tasks/plan": taskPlan,
      "api/v1/proposals/create": jsonResponse(codeProposal, 201),
      "api/v1/reviews": jsonResponse({ error: { code: "proposal_validation_failed", message: "Review request validation failed. Check the decision, identity label, hashes, and justification." } }, 422),
    }, enabledReviewStatus);
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<Dashboard />);
    await screen.findByText("FastAPI is responding");
    await user.type(screen.getByLabelText("What needs attention?"), "Fix the division by zero defect");
    await user.click(screen.getByRole("button", { name: /generate plan/i }));
    await user.click(await screen.findByRole("button", { name: /generate code proposal/i }));
    await user.type(screen.getByLabelText(/decision justification/i), "Reviewed the change.");
    await user.click(screen.getByRole("button", { name: /approve for consideration/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("The review was not recorded. Check the reviewer label format and required review fields; no decision was saved.");
    expect(screen.getByRole("alert")).not.toHaveTextContent("proposal_validation_failed");
  });

  it("requires a separate execution purpose and reports unavailable sandbox without claiming a test run", async () => {
    const executionEvidence = {
      evidence_id: "runtime-evidence-1", proposal_id: codeProposal.proposal_id, repository_id: "planning-fixture",
      status: "sandbox_unavailable", requested_at: "2026-10-22T00:00:00Z", completed_at: "2026-10-22T00:00:00Z",
      proposal_version: 2, source_sha256: codeProposal.target_files[0].original_sha256, diff_sha256: codeProposal.diff_sha256,
      test_case: "calculator_unit_tests", test_command_id: "calculator_pytest_suite_v1", authorizer_identifier: "local_authorizer",
      authorizer_identity_status: "unverified_local_development", authorization_purpose: "Check if isolated validation is ready.",
      sandbox_summary: "Runtime execution refused because one or more sandbox readiness checks failed.",
      readiness_checks: [{ name: "docker_cli", status: "failed", detail: "Docker CLI is unavailable." }],
      exit_code: null, duration_ms: null, stdout: "", stderr: "", test_results: [],
      failure_reason: "No trusted isolated sandbox is available; no test code was run.",
      original_repository_modified: false, code_applied_to_original: false,
    };
    const reviewRecord = {
      review_id: "review-1", proposal_id: codeProposal.proposal_id, task_id: taskPlan.task_id,
      repository_id: "planning-fixture", decision: "approve", reviewer_identifier: "demo_reviewer",
      reviewer_identity_status: "unverified_local_development", justification: "Reviewed the static diff.",
      timestamp: "2026-10-22T00:00:00Z", proposal_version: 1,
      source_sha256: codeProposal.target_files[0].original_sha256, diff_sha256: codeProposal.diff_sha256,
      proposal_lifecycle_state: "review_approved", evidence_references: codeProposal.target_files.map((item) => item.source_reference),
      static_validation_status: "passed", runtime_validation_status: "not_run", outstanding_questions: [],
    };
    const readyFeatureUnavailable: SandboxReadiness = { ...disabledSandboxReadiness, enabled: true, status: "sandbox_unavailable" };
    const fetchMock = routeFetch({
      "api/v1/tasks/plan": taskPlan,
      "api/v1/proposals/create": jsonResponse(codeProposal, 201),
      "api/v1/reviews": jsonResponse(reviewRecord, 201),
      "api/v1/runtime-validation": jsonResponse(executionEvidence, 202),
    }, enabledReviewStatus, readyFeatureUnavailable);
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<Dashboard />);
    await screen.findByText("FastAPI is responding");
    await user.type(screen.getByLabelText("What needs attention?"), "Fix the division by zero defect");
    await user.click(screen.getByRole("button", { name: /generate plan/i }));
    await user.click(await screen.findByRole("button", { name: /generate code proposal/i }));
    await user.type(screen.getByLabelText(/decision justification/i), "Reviewed the static diff.");
    await user.click(screen.getByRole("button", { name: /approve for consideration/i }));

    expect(await screen.findByText("Review Completed")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Purpose for this one-time validation"), "Check if isolated validation is ready.");
    await user.click(screen.getByRole("button", { name: "Authorize one validation request" }));
    expect(await screen.findByText("Outcome:", { exact: false })).toBeInTheDocument();
    expect(screen.getAllByText("sandbox_unavailable").length).toBeGreaterThan(0);
    expect(screen.getByText(/no test code was run/i)).toBeInTheDocument();
    expect(screen.getByText(/Patch applied to original:/)).toBeInTheDocument();
    const runtimeCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/api/v1/runtime-validation"));
    expect(JSON.parse(String(runtimeCall?.[1]?.body))).toMatchObject({
      test_case: "calculator_unit_tests",
      authorization: { authorizer_identifier: "local_authorizer", purpose: "Check if isolated validation is ready." },
    });
  });

  it("shows sanitized backend errors and recovers after dismissal", async () => {
    const fetchMock = routeFetch({ "api/v1/repositories/analyze": jsonResponse({ error: { code: "repository_not_found", message: "Repository is not configured for analysis." } }, 404) });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<Dashboard />);
    await screen.findByText("FastAPI is responding");
    await user.click(screen.getByRole("button", { name: /analyze repository/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Repository is not configured for analysis.");
    await user.click(screen.getByRole("button", { name: "Dismiss error" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("reports malformed backend JSON without crashing the page", async () => {
    const fetchMock = routeFetch({ "api/v1/repositories/analyze": new Response("not json", { status: 200 }) });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<Dashboard />);
    await screen.findByText("FastAPI is responding");
    await user.click(screen.getByRole("button", { name: /analyze repository/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("invalid response"));
    expect(screen.getByRole("heading", { name: /repository intelligence/i })).toBeInTheDocument();
  });
});

describe("task-planning provider error messages", () => {
  it.each([
    ["incomplete_model_response", /stopped before producing a complete plan/],
    ["task_planning_timeout", /timed out.*No automatic retry/],
    ["invalid_task_plan", /did not match the required plan format/],
    ["inference_limit_exceeded", /exceeds a local inference budget or concurrency limit/],
    ["model_provider_error", /could not complete the request.*no mock fallback/i],
    ["invalid_model_response", /invalid response/i],
    ["sensitive_inference_content", /contains credential-like content/i],
  ])("shows a sanitized explanation for %s", async (code, expected) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({
      error: { code, message: "provider body must never reach the UI" },
    }, 502)));

    await expect(planTask("planning-fixture", "Investigate service behavior")).rejects.toThrow(expected);
    await expect(planTask("planning-fixture", "Investigate service behavior")).rejects.not.toThrow("provider body");
  });
});
