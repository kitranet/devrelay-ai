import { describe, expect, it } from "vitest";
import { handoffToMarkdown } from "@/lib/handoff-markdown";
import type { HandoffReport } from "@/lib/types";

describe("handoff markdown export", () => {
  it("exports evidence, unverified review identity, mock provenance and unrun runtime validation", () => {
    const report = {
      report_id: "report-id", generated_at: "2026-10-21T00:00:00Z", repository_id: "planning-fixture",
      task: {
        task_id: "task-id", objective: "Fix division by zero", current_progress: "Review recorded; no changes applied.",
        task_status: "planned", proposal_lifecycle_state: "review_approved", proposal_version: 2,
        relevant_files: ["package/calculator.py"], source_references: [{ path: "package/calculator.py", line: 1, end_line: 2 }], planned_steps: ["1. Inspect division", "Add a regression test"], planned_validation_requirements: ["Run tests", "Review the test report"],
      },
      technical_understanding: {
        analysis_summary: { repository_id: "planning-fixture", file_count: 1, python_file_count: 1, module_count: 1, function_count: 1, class_count: 0, import_count: 0, dependency_count: 0, test_file_count: 0, duration_ms: 1 },
        relevant_modules: [{ name: "package.calculator", path: "package/calculator.py", imports: 0, functions: 1, classes: 0 }],
        relevant_functions: ["divide (package/calculator.py:1)"], relevant_classes: [], relevant_imports: [], dependency_manifests: [],
        verified_context: ["Static AST found one function."], analysis_warnings: [],
      },
      proposed_change: {
        summary: "Guard a zero denominator", target_files: [{ path: "package/calculator.py", original_sha256: "a".repeat(64), source_reference: { path: "package/calculator.py", line: 1, end_line: 2 } }], diff_sha256: "b".repeat(64),
        static_validation_status: "passed", validation_findings: [], provider: "mock", is_mock: true, source_revision_status: "current",
      },
      human_decisions: [{
        review_id: "review-id", proposal_id: "proposal-id", task_id: "task-id", repository_id: "planning-fixture",
        decision: "approve", reviewer_identifier: "demo_reviewer", reviewer_identity_status: "unverified_local_development",
        justification: "Reviewed the static diff and test evidence.", timestamp: "2026-10-21T00:00:00Z", proposal_version: 1,
        source_sha256: "a".repeat(64), diff_sha256: "b".repeat(64), proposal_lifecycle_state: "review_approved",
        evidence_references: [{ path: "package/calculator.py", line: 1, end_line: 2 }], static_validation_status: "passed",
        runtime_validation_status: "not_run", outstanding_questions: ["Run tests in an isolated environment."],
      }],
      outstanding_questions: ["Run tests in an isolated environment."],
      validation_and_risks: {
        static_checks: [], runtime_tests_status: "not_run", runtime_tests_reason: "No sandbox configured.", risks: [], assumptions: [], unresolved_dependencies: [], unsupported_evidence: [],
      },
      runtime_execution: {
        status: "sandbox_unavailable", sandbox_summary: "No verified sandbox is configured.", evidence_id: "evidence-1",
        test_case: "calculator_unit_tests", test_command_id: "calculator_pytest_suite_v1", exit_code: null, duration_ms: null,
        test_results: [], source_sha256: "a".repeat(64), diff_sha256: "b".repeat(64), remaining_work: ["Configure a trusted sandbox."],
      },
      next_engineer_actions: [{ action: "Run the required tests.", required_approval: true, status: "pending" }],
      provenance_note: "Mock-generated proposal; identity unverified.", provider: "mock", is_mock: true,
    } as HandoffReport;
    const markdown = handoffToMarkdown(report);
    expect(markdown).toContain("## Technical understanding — verified static analysis");
    expect(markdown).toContain("demo_reviewer` (unverified local-development identity)");
    expect(markdown).toContain("- Justification: Reviewed the static diff and test evidence.");
    expect(markdown).toContain("- Outstanding questions:\n  - Run tests in an isolated environment.");
    expect(markdown).toContain("### Planned implementation steps\n\n1. Inspect division\n2. Add a regression test");
    expect(markdown).toContain("### Planned validation\n\n- Run tests\n- Review the test report");
    expect(markdown).toContain("### Static checks");
    expect(markdown).toContain("### Runtime validation");
    expect(markdown).toContain("## Isolated runtime validation");
    expect(markdown).toContain("Status: **sandbox_unavailable**");
    expect(markdown).toContain("Evidence ID: `evidence-1`");
    expect(markdown).toContain("Configure a trusted sandbox.");
    expect(markdown).toContain("- Status: **not_run**");
    expect(markdown).toContain("Provider: **mock** (mock output)");
    expect(markdown).toContain("package/calculator.py:1");
  });
});
