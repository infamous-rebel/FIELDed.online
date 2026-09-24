"""Service Execution API endpoints.

Provides service execution creation, listing, retrieval, and lifecycle
transitions.

All ownership is verified server-side.  Only authorized business users
may complete/cancel/no-show a service.  Customers can only view their
own service executions.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.domain.common.enums import ServiceExecutionStatus
from app.domain.identity.models import User
from app.domain.service_execution.schemas import (
    ServiceExecutionCreate,
    ServiceExecutionRead,
    ServiceExecutionTransitionRequest,
)
from app.domain.service_execution.service import ServiceExecutionService
from app.security.authorization import require_business_member, require_customer

router = APIRouter()


def _execution_to_read(execution) -> ServiceExecutionRead:
    """Convert a ServiceExecution model to the read schema."""
    return ServiceExecutionRead.model_validate(execution)


# --- Business endpoints ---


@router.post(
    "/{business_id}/service-executions",
    response_model=ServiceExecutionRead,
    status_code=201,
)
async def create_service_execution(
    business_id: uuid.UUID,
    body: ServiceExecutionCreate,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ServiceExecutionRead:
    """Create a service execution from a confirmed booking."""
    service = ServiceExecutionService(db)
    execution = await service.create_from_booking(
        booking_id=body.booking_id,
        business_id=business_id,
    )
    await db.refresh(execution)
    return _execution_to_read(execution)


@router.get(
    "/{business_id}/service-executions",
    response_model=list[ServiceExecutionRead],
)
async def list_business_service_executions(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[ServiceExecutionRead]:
    """List service executions for a business."""
    service = ServiceExecutionService(db)
    executions = await service.list_business_executions(business_id, status=status, limit=limit, offset=offset)
    return [_execution_to_read(e) for e in executions]


@router.get(
    "/{business_id}/service-executions/{execution_id}",
    response_model=ServiceExecutionRead,
)
async def get_business_service_execution(
    business_id: uuid.UUID,
    execution_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ServiceExecutionRead:
    """Get a specific service execution for a business."""
    service = ServiceExecutionService(db)
    execution = await service.get_business_execution(execution_id, business_id)
    return _execution_to_read(execution)


@router.post(
    "/{business_id}/service-executions/{execution_id}/transition",
    response_model=ServiceExecutionRead,
)
async def transition_service_execution(
    business_id: uuid.UUID,
    execution_id: uuid.UUID,
    body: ServiceExecutionTransitionRequest,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ServiceExecutionRead:
    """Transition a service execution (business actions).

    Supports: start (in_progress), complete, cancel, no_show.
    """
    service = ServiceExecutionService(db)
    execution = await service.get_business_execution(execution_id, business_id)
    target_status = ServiceExecutionStatus(body.target_status)
    execution = await service.transition(
        execution,
        target_status,
        actor_id=user.id,
        notes=body.notes,
        completion_evidence=body.completion_evidence,
    )
    await db.refresh(execution)
    return _execution_to_read(execution)


@router.post(
    "/{business_id}/service-executions/{execution_id}/complete",
    response_model=ServiceExecutionRead,
)
async def complete_service_execution(
    business_id: uuid.UUID,
    execution_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    notes: str | None = Query(None),
) -> ServiceExecutionRead:
    """Mark a service as completed (idempotent).

    This is the primary completion endpoint.  It atomically creates
    the invoice and ledger entry.  Repeated calls do not create
    duplicate records.
    """
    service = ServiceExecutionService(db)
    execution = await service.get_business_execution(execution_id, business_id)
    execution = await service.complete_service(
        execution,
        actor_id=user.id,
        notes=notes,
    )
    await db.refresh(execution)
    return _execution_to_read(execution)


# --- Customer endpoints ---


@router.get(
    "/my-service-executions",
    response_model=list[ServiceExecutionRead],
)
async def list_my_service_executions(
    user: Annotated[User, Depends(require_customer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[ServiceExecutionRead]:
    """List service executions for the authenticated customer."""
    service = ServiceExecutionService(db)
    executions = await service.list_customer_executions(user.id, status=status, limit=limit, offset=offset)
    return [_execution_to_read(e) for e in executions]


@router.get(
    "/my-service-executions/{execution_id}",
    response_model=ServiceExecutionRead,
)
async def get_my_service_execution(
    execution_id: uuid.UUID,
    user: Annotated[User, Depends(require_customer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ServiceExecutionRead:
    """Get a specific service execution for the authenticated customer."""
    service = ServiceExecutionService(db)
    execution = await service.get_customer_execution(execution_id, user.id)
    return _execution_to_read(execution)
