"""Application exceptions and consistent HTTP error responses."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class ApplicationError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class MissingCredentialsError(ApplicationError):
    status_code = 503
    code = "missing_credentials"


class LiveInferenceDisabledError(ApplicationError):
    status_code = 403
    code = "live_inference_disabled"

    def __init__(self) -> None:
        super().__init__("Live Nebius inference is disabled by the operator kill switch.")


class InferenceQuotaExceededError(ApplicationError):
    status_code = 429
    code = "inference_quota_exhausted"

    def __init__(self) -> None:
        super().__init__("The configured live inference request allowance is exhausted.")


class InferenceQuotaUnavailableError(ApplicationError):
    status_code = 503
    code = "inference_quota_unavailable"

    def __init__(self) -> None:
        super().__init__("Live inference is unavailable because request accounting could not be verified.")


class ModelTimeoutError(ApplicationError):
    status_code = 504
    code = "model_timeout"


class ModelProviderError(ApplicationError):
    status_code = 502
    code = "model_provider_error"


class ModelIncompleteResponseError(ApplicationError):
    status_code = 502
    code = "incomplete_model_response"

    def __init__(self) -> None:
        super().__init__("The model response was truncated before a complete answer was produced.")


class ModelEmptyResponseError(ApplicationError):
    status_code = 502
    code = "empty_model_response"

    def __init__(self) -> None:
        super().__init__("The inference provider returned an empty answer.")


class MalformedModelResponseError(ApplicationError):
    status_code = 502
    code = "invalid_model_response"

    def __init__(self) -> None:
        super().__init__("The inference provider returned a malformed response.")


class InferenceLimitError(ApplicationError):
    status_code = 429
    code = "inference_limit_exceeded"

    def __init__(self, message: str = "The inference request exceeds a configured application limit.") -> None:
        super().__init__(message)


class SensitiveInferenceContentError(ApplicationError):
    status_code = 422
    code = "sensitive_inference_content"

    def __init__(self) -> None:
        super().__init__("Planning input or provider output contains credential-like content and was rejected.")


class RepositoryNotAuthorizedError(ApplicationError):
    status_code = 404
    code = "repository_not_found"

    def __init__(self) -> None:
        super().__init__("Repository is not configured for analysis.")


class RepositoryLimitError(ApplicationError):
    status_code = 413
    code = "repository_limit_exceeded"

    def __init__(self, message: str) -> None:
        super().__init__(message)


class RepositoryAnalysisTimeoutError(ApplicationError):
    status_code = 504
    code = "repository_analysis_timeout"

    def __init__(self) -> None:
        super().__init__("Repository analysis exceeded its processing time limit.")


class TaskPlanningTimeoutError(ApplicationError):
    status_code = 504
    code = "task_planning_timeout"

    def __init__(self) -> None:
        super().__init__("Engineering task planning exceeded its processing time limit.")


class TaskPlanValidationError(ApplicationError):
    status_code = 502
    code = "invalid_task_plan"

    def __init__(self) -> None:
        super().__init__("The configured inference provider returned an invalid task plan.")


class TaskPlanningContextLimitError(ApplicationError):
    status_code = 413
    code = "task_context_limit_exceeded"

    def __init__(self) -> None:
        super().__init__("Repository context exceeds the configured planning limit.")


class TaskPlanNotFoundError(ApplicationError):
    status_code = 404
    code = "task_plan_not_found"

    def __init__(self) -> None:
        super().__init__("The task plan is not available in this application session.")


class TaskPlanSourceConflictError(ApplicationError):
    status_code = 409
    code = "task_plan_source_stale"

    def __init__(self) -> None:
        super().__init__("The authorized repository changed after this task plan was validated.")


class PlanReviewConflictError(ApplicationError):
    status_code = 409
    code = "plan_review_conflict"

    def __init__(self) -> None:
        super().__init__("The plan changed or already has a human review decision.")


class ProposalNotFoundError(ApplicationError):
    status_code = 404
    code = "proposal_not_found"

    def __init__(self) -> None:
        super().__init__("The proposal is not available in this application session.")


class ProposalSourceConflictError(ApplicationError):
    status_code = 409
    code = "proposal_source_stale"

    def __init__(self) -> None:
        super().__init__("The target source changed after the task plan was created.")


class ProposalValidationError(ApplicationError):
    status_code = 422
    code = "proposal_validation_failed"


class LocalReviewDisabledError(ApplicationError):
    status_code = 404
    code = "local_reviews_disabled"

    def __init__(self) -> None:
        super().__init__("Local review is disabled. Enable it only for loopback development use.")


class LocalReviewLoopbackError(ApplicationError):
    status_code = 403
    code = "local_review_loopback_only"

    def __init__(self) -> None:
        super().__init__("Local review and handoff routes accept loopback requests only.")


class ProposalVersionConflictError(ApplicationError):
    status_code = 409
    code = "proposal_version_conflict"

    def __init__(self) -> None:
        super().__init__("The proposal version or reviewed hashes are stale. Refresh the proposal before reviewing.")


class ReviewTransitionConflictError(ApplicationError):
    status_code = 409
    code = "review_transition_conflict"

    def __init__(self) -> None:
        super().__init__("This proposal has already received a review decision and cannot be reviewed again.")


class HandoffReportNotFoundError(ApplicationError):
    status_code = 404
    code = "handoff_report_not_found"

    def __init__(self) -> None:
        super().__init__("The handoff report is not available in this application session.")


class ReviewPayloadTooLargeError(ApplicationError):
    status_code = 413
    code = "review_payload_too_large"

    def __init__(self) -> None:
        super().__init__("The review request exceeds the local size limit.")


class RuntimeValidationDisabledError(ApplicationError):
    status_code = 404
    code = "runtime_validation_disabled"

    def __init__(self) -> None:
        super().__init__("Isolated runtime validation is disabled outside opted-in loopback development use.")


class RuntimeValidationNotFoundError(ApplicationError):
    status_code = 404
    code = "runtime_validation_not_found"

    def __init__(self) -> None:
        super().__init__("Runtime validation evidence is not available in this application session.")


class RuntimeAuthorizationConflictError(ApplicationError):
    status_code = 409
    code = "runtime_authorization_conflict"

    def __init__(self) -> None:
        super().__init__("This proposal revision already has a runtime-validation authorization attempt.")


class RuntimeValidationPayloadTooLargeError(ApplicationError):
    status_code = 413
    code = "runtime_validation_payload_too_large"

    def __init__(self) -> None:
        super().__init__("The runtime-validation request exceeds the local size limit.")


def register_exception_handlers(application: FastAPI) -> None:
    @application.exception_handler(ApplicationError)
    async def application_error_handler(_: Request, exc: ApplicationError) -> JSONResponse:
        logger.warning("Application error: %s", exc.code)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @application.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled application error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "An unexpected error occurred."}},
        )
