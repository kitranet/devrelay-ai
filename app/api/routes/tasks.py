"""Engineering task planning API."""

from fastapi import APIRouter, Request

from app.models.task import TaskPlan, TaskPlanningRequest
from app.services.task_planning import TaskPlanningService

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.post("/plan", response_model=TaskPlan)
async def plan_task(payload: TaskPlanningRequest, request: Request) -> TaskPlan:
    service = TaskPlanningService(
        request.app.state.settings,
        request.app.state.repository_scanner,
        request.app.state.inference_service,
    )
    return await service.plan(payload)
