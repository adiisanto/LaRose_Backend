from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from src.core.pagination import APIResponse, PaginatedData, PaginationParams
from src.modules.assembly.dependencies import get_assembly_service
from src.modules.assembly.schemas import (
    AssemblyTaskDetailResponse,
    AssemblyTaskQueueItem,
    ScrapReportInput,
)
from src.modules.assembly.service import AssemblyService
from src.modules.iam.dependencies import get_current_user
from src.modules.iam.models import User
from src.modules.orders.models import TaskStatus

router = APIRouter(prefix="/assembly", tags=["Assembly & Fulfillment"])


@router.get(
    "/queue",
    response_model=APIResponse[PaginatedData[AssemblyTaskQueueItem]],
    summary="Get prioritized staff packing task queue",
)
async def list_queue(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    task_status: TaskStatus | None = Query(None, alias="status", description="Filter by status"),
    service: AssemblyService = Depends(get_assembly_service),
    _: User = Depends(get_current_user),
) -> APIResponse[PaginatedData[AssemblyTaskQueueItem]]:
    """Tablet queue sorted by delivery_date ASC, created_at ASC."""
    params = PaginationParams(page=page, page_size=page_size)
    paginated = await service.list_queue(params=params, status=task_status)
    return APIResponse(
        success=True,
        data=paginated,
        message="Assembly task queue retrieved successfully.",
    )


@router.get(
    "/{task_id}",
    response_model=APIResponse[AssemblyTaskDetailResponse],
    summary="Get assembly task detail and BOM material checklist",
)
async def get_task_by_id(
    task_id: UUID,
    service: AssemblyService = Depends(get_assembly_service),
    _: User = Depends(get_current_user),
) -> APIResponse[AssemblyTaskDetailResponse]:
    """Retrieve assembly task details including raw material checklist from BOM recipes."""
    task = await service.get_by_id(task_id)
    return APIResponse(
        success=True,
        data=task,
        message="Assembly task details retrieved successfully.",
    )


@router.patch(
    "/{task_id}/start",
    response_model=APIResponse[AssemblyTaskDetailResponse],
    summary="Staff Packing claims and starts assembling a bouquet task",
)
async def start_assembly(
    task_id: UUID,
    service: AssemblyService = Depends(get_assembly_service),
    current_user: User = Depends(get_current_user),
) -> APIResponse[AssemblyTaskDetailResponse]:
    """Claim task and transition to IN_PROGRESS (Order status -> PROCESSING)."""
    task = await service.start_assembly(task_id, staff_user_id=current_user.id)
    return APIResponse(
        success=True,
        data=task,
        message="Assembly task started successfully.",
    )


@router.patch(
    "/{task_id}/finish",
    response_model=APIResponse[AssemblyTaskDetailResponse],
    summary="Finish assembly task and deduct physical inventory stock",
)
async def finish_assembly(
    task_id: UUID,
    service: AssemblyService = Depends(get_assembly_service),
    _: User = Depends(get_current_user),
) -> APIResponse[AssemblyTaskDetailResponse]:
    """Complete packing: deduct stock, transition task to PACKED, order to READY_FOR_DELIVERY."""
    task = await service.finish_assembly(task_id)
    return APIResponse(
        success=True,
        data=task,
        message="Assembly task completed and stock deducted successfully.",
    )


@router.post(
    "/{task_id}/scrap",
    response_model=APIResponse[AssemblyTaskDetailResponse],
    status_code=status.HTTP_200_OK,
    summary="Report damaged raw material and allocate replacement",
)
async def report_scrap(
    task_id: UUID,
    payload: ScrapReportInput,
    service: AssemblyService = Depends(get_assembly_service),
    current_user: User = Depends(get_current_user),
) -> APIResponse[AssemblyTaskDetailResponse]:
    """Report scrap: deduct damaged unit and allocate replacement from free warehouse inventory."""
    task = await service.report_scrap(
        task_id=task_id,
        dto=payload,
        staff_user_id=current_user.id,
    )
    return APIResponse(
        success=True,
        data=task,
        message="Scrap reported and replacement material allocated successfully.",
    )
