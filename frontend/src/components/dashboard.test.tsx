import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Dashboard from "@/components/dashboard";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
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
};

const codeProposal = {
  proposal_id: "2b7a47fb-5c38-481a-a35c-b4f4cc0d7047", repository_id: "planning-fixture",
  originating_task_id: "plan-test", task_description: "Fix the division by zero defect",
  target_files: [{ path: "package/calculator.py", original_sha256: "a".repeat(64), source_reference: { path: "package/calculator.py", line: 1, end_line: 2 } }],
  proposed_change_summary: "Raise ValueError when denominator is zero.",
  unified_diff: "--- a/package/calculator.py\n+++ b/package/calculator.py\n@@ -1,2 +1,4 @@\n def divide(numerator, denominator):\n+    if denominator == 0:\n+        raise ValueError('denominator must not be zero')\n     return numerator / denominator\n",
  risk_classification: "low", validation_findings: [
    { check: "python_syntax", status: "passed", detail: "AST parse passed without execution." },
    { check: "runtime_isolation", status: "not_run", detail: "No trusted isolated executor is configured." },
  ], static_validation_status: "passed", runtime_validation_status: "not_run",
  runtime_validation_reason: "No trusted isolated executor is configured; repository code was not executed on the host.",
  provider: "mock", is_mock: true, created_at: "2026-10-21T00:00:00Z",
  lifecycle_state: "awaiting_review", human_approval_required: true,
};

describe("DevRelay dashboard", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ status: "ok" })));
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
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ status: "ok" }))
      .mockResolvedValueOnce(jsonResponse(repositoryAnalysis));
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
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/backend/api/v1/repositories/analyze", expect.objectContaining({ method: "POST" }));
  });

  it("submits a planning task and clearly labels deterministic mock output", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ status: "ok" }))
      .mockResolvedValueOnce(jsonResponse(taskPlan));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<Dashboard />);
    await screen.findByText("FastAPI is responding");
    await user.type(screen.getByLabelText("What needs attention?"), "Fix the division by zero defect");
    await user.click(screen.getByRole("button", { name: /generate plan/i }));
    expect(await screen.findByText("MOCK MODE — Simulated inference for development testing.")).toBeInTheDocument();
    expect(screen.getByText("This response was not generated by NVIDIA Nemotron.")).toBeInTheDocument();
    expect(screen.getByText("Human approval required")).toBeInTheDocument();
    expect(screen.getByText("Execution has not started")).toBeInTheDocument();
    expect(screen.getByText("Inspect division behavior and add a regression test.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/backend/api/v1/tasks/plan", expect.objectContaining({ method: "POST" }));
  });

  it("creates and displays a mock review proposal without apply actions", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ status: "ok" }))
      .mockResolvedValueOnce(jsonResponse(taskPlan))
      .mockResolvedValueOnce(jsonResponse(codeProposal, 201));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<Dashboard />);
    await screen.findByText("FastAPI is responding");
    await user.type(screen.getByLabelText("What needs attention?"), "Fix the division by zero defect");
    await user.click(screen.getByRole("button", { name: /generate plan/i }));
    await user.click(await screen.findByRole("button", { name: /generate code proposal/i }));
    expect(await screen.findByRole("heading", { name: "Code change proposal" })).toBeInTheDocument();
    expect(screen.getByText("Source SHA-256:", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Runtime validation: not run")).toBeInTheDocument();
    expect(screen.getByText(/No files were changed, approved, applied, or executed/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /apply|approve/i })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenNthCalledWith(3, "/api/backend/api/v1/proposals/create", expect.objectContaining({ method: "POST" }));
  });

  it("shows sanitized backend errors and recovers after dismissal", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ status: "ok" }))
      .mockResolvedValueOnce(jsonResponse({ error: { code: "repository_not_found", message: "Repository is not configured for analysis." } }, 404));
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
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ status: "ok" }))
      .mockResolvedValueOnce(new Response("not json", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<Dashboard />);
    await screen.findByText("FastAPI is responding");
    await user.click(screen.getByRole("button", { name: /analyze repository/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("invalid response"));
    expect(screen.getByRole("heading", { name: /repository intelligence/i })).toBeInTheDocument();
  });
});
