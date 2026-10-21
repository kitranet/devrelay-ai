"""Repository intelligence API."""

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from app.models.repository import RepositoryAnalysisRequest, RepositoryAnalysisResponse

router = APIRouter(prefix="/api/v1/repositories", tags=["repositories"])


@router.post("/analyze", response_model=RepositoryAnalysisResponse)
async def analyze_repository(
    payload: RepositoryAnalysisRequest, request: Request
) -> RepositoryAnalysisResponse:
    scanner = request.app.state.repository_scanner
    return await run_in_threadpool(scanner.analyze, payload.repository_id)
