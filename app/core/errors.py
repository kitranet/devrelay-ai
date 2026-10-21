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


class ModelTimeoutError(ApplicationError):
    status_code = 504
    code = "model_timeout"


class ModelProviderError(ApplicationError):
    status_code = 502
    code = "model_provider_error"


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
