import type { ApiError, CodeChangeProposal, HandoffReport, HealthResponse, InferenceAttemptHistory, InferenceStatus, LocalReviewStatus, PlanOnlyHandoffReport, PlanReviewDecision, PlanReviewHistory, PlanReviewRecord, RepositoryAnalysis, ReviewDecision, ReviewHistory, ReviewRecord, RuntimeValidationEvidence, SandboxReadiness, TaskPlan } from "@/lib/types";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/backend/${path}`, {
      ...init,
      cache: "no-store",
      headers: { ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
    });
  } catch {
    throw new Error("Cannot reach the dashboard API proxy. Check that the frontend is running.");
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new Error(`The backend returned an invalid response (HTTP ${response.status}).`);
  }

  if (!response.ok) {
    const detail = body as ApiError;
    const knownMessages: Record<string, string> = {
      incomplete_model_response: "Nebius stopped before producing a complete plan. No plan was accepted and no automatic retry was made.",
      empty_model_response: "The inference provider returned no final answer. No plan was accepted.",
      invalid_model_response: "Nebius returned an invalid response. No plan was accepted.",
      task_planning_timeout: "Nebius planning timed out. No automatic retry was made; review the request before trying again.",
      invalid_task_plan: "Planning stopped because the response did not pass required plan validation. No plan or citations were accepted, and no handoff was created.",
      inference_limit_exceeded: "This request exceeds a local inference budget or concurrency limit. No paid request was sent.",
      sensitive_inference_content: "Planning stopped because the input or response contains credential-like content. Remove secrets before trying again.",
      missing_credentials: "Nebius inference is not configured with an API key. No mock fallback was used.",
      live_inference_disabled: "Live inference is blocked. Nebius must be explicitly selected and the operator kill switch enabled.",
      inference_quota_exhausted: "The live inference request allowance is exhausted. No request was sent.",
      inference_quota_unavailable: "Live inference is blocked because request accounting is unavailable.",
      model_provider_error: "Nebius could not complete the request. Check provider availability; no mock fallback was used.",
      model_timeout: "Nebius inference timed out. No automatic retry was made.",
    };
    const code = detail.error?.code;
    throw new Error((code && knownMessages[code]) || detail.error?.message || `Backend request failed (HTTP ${response.status}).`);
  }
  return body as T;
}

export const checkBackend = () => requestJson<HealthResponse>("health");
export const getInferenceStatus = () => requestJson<InferenceStatus>("api/v1/inference/status");
export const getInferenceAttempts = () => requestJson<InferenceAttemptHistory>("api/v1/inference/attempts?limit=30");

export const analyzeRepository = (repositoryId: string) =>
  requestJson<RepositoryAnalysis>("api/v1/repositories/analyze", {
    method: "POST",
    body: JSON.stringify({ repository_id: repositoryId }),
  });

export const planTask = (repositoryId: string, taskDescription: string) =>
  requestJson<TaskPlan>("api/v1/tasks/plan", {
    method: "POST",
    body: JSON.stringify({ repository_id: repositoryId, task_description: taskDescription }),
  });

export const createProposal = (repositoryId: string, taskId: string) =>
  requestJson<CodeChangeProposal>("api/v1/proposals/create", {
    method: "POST",
    body: JSON.stringify({
      repository_id: repositoryId,
      task_id: taskId,
      transformation_id: "calculator-zero-denominator-value-error-v1",
    }),
  });

export const getLocalReviewStatus = () => requestJson<LocalReviewStatus>("api/v1/reviews/status");

export const submitReview = (input: {
  proposal_id: string; decision: ReviewDecision; reviewer_identifier: string; justification: string;
  proposal_version: number; source_sha256: string; diff_sha256: string; outstanding_questions: string[];
}) => requestJson<ReviewRecord>("api/v1/reviews", { method: "POST", body: JSON.stringify(input) });

export const getReviewHistory = (proposalId: string) =>
  requestJson<ReviewHistory>(`api/v1/reviews/${encodeURIComponent(proposalId)}`);

export const submitPlanReview = (input: {
  task_id: string; plan_sha256: string; decision: PlanReviewDecision;
  reviewer_identifier: string; justification: string; unresolved_questions: string[];
}) => requestJson<PlanReviewRecord>("api/v1/reviews/plans", { method: "POST", body: JSON.stringify(input) });

export const getPlanReviewHistory = (taskId: string) =>
  requestJson<PlanReviewHistory>(`api/v1/reviews/plans/${encodeURIComponent(taskId)}`);

export const generateHandoff = (proposalId: string) =>
  requestJson<HandoffReport>("api/v1/handoffs", { method: "POST", body: JSON.stringify({ proposal_id: proposalId }) });

export const generatePlanOnlyHandoff = (taskId: string) =>
  requestJson<PlanOnlyHandoffReport>("api/v1/handoffs/plans", { method: "POST", body: JSON.stringify({ task_id: taskId }) });

export const getPlanOnlyHandoff = (reportId: string) =>
  requestJson<PlanOnlyHandoffReport>(`api/v1/handoffs/plans/${encodeURIComponent(reportId)}`);

export const getHandoff = (reportId: string) =>
  requestJson<HandoffReport>(`api/v1/handoffs/${encodeURIComponent(reportId)}`);

export const getSandboxReadiness = () =>
  requestJson<SandboxReadiness>("api/v1/runtime-validation/readiness");

export const requestRuntimeValidation = (input: {
  proposal_id: string; proposal_version: number; source_sha256: string; diff_sha256: string;
  test_case: "calculator_unit_tests"; authorization: { authorizer_identifier: string; purpose: string };
}) => requestJson<RuntimeValidationEvidence>("api/v1/runtime-validation", {
  method: "POST",
  body: JSON.stringify(input),
});

export const getRuntimeValidationEvidence = (evidenceId: string) =>
  requestJson<RuntimeValidationEvidence>(`api/v1/runtime-validation/${encodeURIComponent(evidenceId)}`);
