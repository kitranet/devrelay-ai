export type HealthResponse = { status: "ok" };
export type InferenceStatus = {
  provider: "nebius" | "mock";
  live_inference_enabled: boolean;
  credentials_configured: boolean;
  quota_status: "not_applicable" | "available" | "exhausted" | "unavailable";
  quota_total: number | null;
  quota_used: number | null;
  quota_remaining: number | null;
};

export type SourceReference = {
  path: string;
  line: number;
  end_line: number | null;
};

export type RepositoryAnalysis = {
  summary: {
    repository_id: string;
    file_count: number;
    python_file_count: number;
    module_count: number;
    function_count: number;
    class_count: number;
    import_count: number;
    dependency_count: number;
    test_file_count: number;
    duration_ms: number;
  };
  files: { path: string; size_bytes: number; modified_at: string; category: string }[];
  modules: { name: string; path: string; imports: number; functions: number; classes: number }[];
  functions: { name: string; qualified_name: string; kind: string; source: SourceReference }[];
  classes: { name: string; qualified_name: string; source: SourceReference }[];
  imports: {
    source_path: string;
    source_module: string;
    line: number;
    imported_module: string;
    imported_names: string[];
    kind: string;
  }[];
  dependency_manifests: { path: string; format: string; dependencies: string[] }[];
  test_files: string[];
  readme_files: string[];
  configuration_files: string[];
  warnings: { code: string; message: string; path: string | null; line: number | null }[];
};

export type TaskPlan = {
  task_id: string;
  repository_id: string;
  task_description: string;
  status: "planned" | "insufficient_context" | "unsupported";
  relevant_files: string[];
  source_references: SourceReference[];
  implementation_steps: {
    step: number;
    description: string;
    source_references: SourceReference[];
  }[];
  expected_code_changes: { path: string; description: string }[];
  risks: string[];
  dependencies: string[];
  validation_requirements: string[];
  human_approval_required: boolean;
  execution_status: "not_started";
  assumptions: string[];
  unsupported_references: string[];
  provider: "nebius" | "mock";
  is_mock: boolean;
  inference_diagnostics?: {
    provider: "nebius" | "mock";
    model: string;
    is_mock: boolean;
    completion_status: "completed";
    finish_reason: string | null;
    model_reported_by_provider: boolean;
    latency_ms: number | null;
    usage: {
      input_tokens: number | null;
      output_tokens: number | null;
      reasoning_tokens: number | null;
      total_tokens: number | null;
    } | null;
  } | null;
};

export type CodeChangeProposal = {
  proposal_id: string;
  repository_id: string;
  originating_task_id: string;
  originating_plan_provider: "nebius" | "mock";
  transformation_id: "calculator-zero-denominator-value-error-v1";
  task_description: string;
  target_files: { path: string; original_sha256: string; source_reference: SourceReference }[];
  proposed_change_summary: string;
  unified_diff: string;
  diff_sha256: string;
  risk_classification: "low" | "medium" | "high";
  validation_findings: { check: string; status: "passed" | "failed" | "not_run"; detail: string }[];
  static_validation_status: "passed" | "failed";
  runtime_validation_status: "not_run";
  runtime_validation_reason: string;
  provider: "mock";
  is_mock: true;
  created_at: string;
  lifecycle_state: ProposalLifecycle;
  human_approval_required: true;
  version: number;
};

export type ProposalLifecycle = "proposed" | "validated" | "awaiting_review" | "review_approved" | "changes_requested" | "rejected";

export type LocalReviewStatus = {
  enabled: boolean;
  environment: string;
  identity_status: "unverified_local_development";
};

export type ReviewDecision = "approve" | "reject" | "request_changes";

export type ReviewRecord = {
  review_id: string;
  proposal_id: string;
  task_id: string;
  repository_id: string;
  decision: ReviewDecision;
  reviewer_identifier: string;
  reviewer_identity_status: "unverified_local_development";
  justification: string;
  timestamp: string;
  proposal_version: number;
  source_sha256: string;
  diff_sha256: string;
  proposal_lifecycle_state: ProposalLifecycle;
  evidence_references: SourceReference[];
  static_validation_status: "passed" | "failed";
  runtime_validation_status: "not_run";
  outstanding_questions: string[];
};

export type ReviewHistory = {
  proposal_id: string;
  current_lifecycle_state: string;
  current_proposal_version: number;
  reviews: ReviewRecord[];
  audit_events: {
    event_id: string;
    timestamp: string;
    event_type: string;
    outcome: string;
    reviewer_identifier: string;
    reviewer_identity_status: "unverified_local_development";
    previous_state: string;
    new_state: string;
    decision: ReviewDecision | null;
    justification: string;
    source_sha256: string;
    diff_sha256: string;
    failure_reason: string | null;
  }[];
};

export type RuntimeValidationStatus = "authorized" | "running" | "passed" | "failed" | "timed_out" | "sandbox_unavailable";

export type SandboxReadiness = {
  enabled: boolean;
  environment: string;
  available: boolean;
  status: "disabled" | "ready" | "sandbox_unavailable";
  test_case: "calculator_unit_tests";
  test_command_id: string;
  checks: { name: string; status: "passed" | "failed" | "not_checked"; detail: string }[];
  limitations: string[];
};

export type RuntimeValidationEvidence = {
  evidence_id: string;
  proposal_id: string;
  repository_id: string;
  status: RuntimeValidationStatus;
  requested_at: string;
  completed_at: string | null;
  proposal_version: number;
  source_sha256: string;
  diff_sha256: string;
  test_case: "calculator_unit_tests";
  test_command_id: string;
  authorizer_identifier: string;
  authorizer_identity_status: "unverified_local_development";
  authorization_purpose: string;
  sandbox_summary: string;
  readiness_checks: SandboxReadiness["checks"];
  exit_code: number | null;
  duration_ms: number | null;
  stdout: string;
  stderr: string;
  test_results: string[];
  failure_reason: string | null;
  original_repository_modified: false;
  code_applied_to_original: false;
};

export type HandoffReport = {
  report_id: string;
  generated_at: string;
  repository_id: string;
  task: {
    task_id: string; objective: string; current_progress: string; task_status: string;
    planning_provider: "nebius" | "mock";
    proposal_lifecycle_state: string; proposal_version: number; relevant_files: string[]; source_references: SourceReference[];
    planned_steps: string[]; planned_validation_requirements: string[];
  };
  technical_understanding: {
    analysis_summary: RepositoryAnalysis["summary"];
    relevant_modules: RepositoryAnalysis["modules"];
    relevant_functions: string[]; relevant_classes: string[]; relevant_imports: string[];
    dependency_manifests: string[]; verified_context: string[]; analysis_warnings: string[];
  };
  proposed_change: {
    summary: string; target_files: CodeChangeProposal["target_files"]; diff_sha256: string;
    static_validation_status: "passed" | "failed";
    validation_findings: CodeChangeProposal["validation_findings"];
    provider: "mock"; is_mock: true; source_revision_status: "current" | "stale";
    originating_plan_provider: "nebius" | "mock";
    transformation_id: "calculator-zero-denominator-value-error-v1";
  };
  human_decisions: ReviewRecord[];
  outstanding_questions: string[];
  validation_and_risks: {
    static_checks: CodeChangeProposal["validation_findings"];
    runtime_tests_status: RuntimeValidationStatus | "not_run"; runtime_tests_reason: string;
    risks: string[]; assumptions: string[]; unresolved_dependencies: string[]; unsupported_evidence: string[];
  };
  runtime_execution: {
    status: RuntimeValidationStatus | "not_run";
    sandbox_summary: string;
    evidence_id: string | null;
    test_case: string;
    test_command_id: string;
    exit_code: number | null;
    duration_ms: number | null;
    test_results: string[];
    source_sha256: string;
    diff_sha256: string;
    remaining_work: string[];
  };
  next_engineer_actions: { action: string; required_approval: boolean; status: "pending" }[];
  provenance_note: string;
  provider: "mock"; is_mock: true;
};

export type ApiError = { error?: { code?: string; message?: string } };
