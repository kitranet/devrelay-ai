"""Engineering task planning API."""

from fastapi import APIRouter, Request

from app.models.task import TaskPlan, TaskPlanningRequest
from app.services.proposal_generation import capture_plan_source_hashes
from app.services.task_planning import TaskPlanningService

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.post("/plan", response_model=TaskPlan)
async def plan_task(payload: TaskPlanningRequest, request: Request) -> TaskPlan:
    service = TaskPlanningService(
        request.app.state.settings,
        request.app.state.repository_scanner,
        request.app.state.inference_service,
    )
    plan = await service.plan(payload)
    source_hashes = capture_plan_source_hashes(request.app.state.settings, plan)
    request.app.state.task_plan_store.put(plan, source_hashes)
    return plan
