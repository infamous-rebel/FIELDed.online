"""Agent Capability & Delegation API endpoints.

Provides business-owner control over agent authority:
- List / configure capabilities per agent type
- Set authority modes (DISABLED, ASSIST, APPROVAL, DELEGATED)
- Create / revoke explicit delegations
- Check authorization for an agent action
- View execution audit logs

All endpoints are tenant-scoped. AI may READ capabilities and logs
but must NEVER change authority modes or create delegations through
AI-driven paths — these are owner-only operations.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_business_member
from app.database import get_db_session
from app.domain.agent.service import AgentCapabilityService
from app.domain.common.enums import (
    AgentAuthorityMode,
    AgentCapabilityType,
    AgentType,
)
from app.domain.identity.models import User

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────


class CapabilityRead(BaseModel):
    """Single capability record."""

    id: str
    business_id: str
    agent_type: str
    capability_type: str
    authority_mode: str
    is_active: bool
    policy_constraints: dict | None = None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class CapabilitySetRequest(BaseModel):
    """Request to set authority mode for a capability."""

    authority_mode: AgentAuthorityMode
    policy_constraints: dict | None = None


class DelegationRead(BaseModel):
    """Single delegation record."""

    id: str
    capability_id: str
    business_id: str
    agent_type: str
    capability_type: str
    status: str
    granted_by: str
    granted_at: str
    expires_at: str | None = None
    revoked_at: str | None = None
    revoked_by: str | None = None
    reason: str | None = None
    created_at: str

    model_config = {"from_attributes": True}


class DelegationCreateRequest(BaseModel):
    """Request to create a delegation."""

    agent_type: AgentType
    capability_type: AgentCapabilityType
    expires_at: datetime | None = None
    reason: str | None = None


class DelegationRevokeRequest(BaseModel):
    """Request to revoke a delegation."""

    reason: str | None = None


class AuthorizationCheckRequest(BaseModel):
    """Request to check agent authorization."""

    agent_type: AgentType
    capability_type: AgentCapabilityType
    action_context: dict | None = None


class AuthorizationCheckRead(BaseModel):
    """Result of an authorization check."""

    authorized: bool
    authority_mode: str
    delegation_id: str | None = None
    reason: str


class ExecutionLogRead(BaseModel):
    """Single execution log entry."""

    id: str
    business_id: str
    delegation_id: str | None = None
    agent_type: str
    capability_type: str
    authority_mode: str
    action_type: str
    status: str
    validation_passed: bool
    correlation_id: str | None = None
    created_at: str

    model_config = {"from_attributes": True}


# ── Capability endpoints ──────────────────────────────────────────


@router.get(
    "/businesses/{business_id}/agent-capabilities",
    response_model=list[CapabilityRead],
)
async def list_capabilities(
    business_id: uuid.UUID,
    agent_type: str | None = Query(None, description="Filter by agent type"),
    session: AsyncSession = Depends(get_db_session),
    _user: User = Depends(require_business_member),
):
    """List all active capabilities for a business."""
    service = AgentCapabilityService(session)
    caps = await service.list_capabilities(business_id, agent_type=agent_type)
    return caps


@router.put(
    "/businesses/{business_id}/agent-capabilities",
    response_model=CapabilityRead,
)
async def set_capability_authority(
    business_id: uuid.UUID,
    body: CapabilitySetRequest,
    agent_type: AgentType = Query(..., description="Agent type"),
    capability_type: AgentCapabilityType = Query(..., description="Capability type"),
    session: AsyncSession = Depends(get_db_session),
    _user: User = Depends(require_business_member),
):
    """Set the authority mode for a capability (owner-only)."""
    service = AgentCapabilityService(session)
    cap = await service.set_authority_mode(
        business_id,
        agent_type,
        capability_type,
        body.authority_mode,
        policy_constraints=body.policy_constraints,
    )
    return cap


# ── Delegation endpoints ──────────────────────────────────────────


@router.get(
    "/businesses/{business_id}/agent-delegations",
    response_model=list[DelegationRead],
)
async def list_delegations(
    business_id: uuid.UUID,
    status: str | None = Query(None, description="Filter by status"),
    session: AsyncSession = Depends(get_db_session),
    _user: User = Depends(require_business_member),
):
    """List delegations for a business."""
    service = AgentCapabilityService(session)
    delegations = await service.list_delegations(business_id, status=status)
    return delegations


@router.post(
    "/businesses/{business_id}/agent-delegations",
    response_model=DelegationRead,
    status_code=201,
)
async def create_delegation(
    business_id: uuid.UUID,
    body: DelegationCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_business_member),
):
    """Create an explicit owner delegation for a capability."""
    service = AgentCapabilityService(session)
    delegation = await service.create_delegation(
        business_id,
        body.agent_type,
        body.capability_type,
        granted_by=user.id,
        expires_at=body.expires_at,
        reason=body.reason,
    )
    return delegation


@router.post(
    "/businesses/{business_id}/agent-delegations/{delegation_id}/revoke",
    response_model=DelegationRead,
)
async def revoke_delegation(
    business_id: uuid.UUID,
    delegation_id: uuid.UUID,
    body: DelegationRevokeRequest | None = None,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_business_member),
):
    """Revoke an active delegation."""
    service = AgentCapabilityService(session)
    delegation = await service.revoke_delegation(
        delegation_id,
        revoked_by=user.id,
        reason=body.reason if body else None,
    )
    return delegation


# ── Authorization check ───────────────────────────────────────────


@router.post(
    "/businesses/{business_id}/agent-authorization/check",
    response_model=AuthorizationCheckRead,
)
async def check_authorization(
    business_id: uuid.UUID,
    body: AuthorizationCheckRequest,
    session: AsyncSession = Depends(get_db_session),
    _user: User = Depends(require_business_member),
):
    """Check whether an agent is authorized for a capability."""
    service = AgentCapabilityService(session)
    result = await service.check_authorization(
        business_id,
        body.agent_type,
        body.capability_type,
        action_context=body.action_context,
    )
    return AuthorizationCheckRead(
        authorized=result.authorized,
        authority_mode=str(result.authority_mode),
        delegation_id=str(result.delegation.id) if result.delegation else None,
        reason=result.reason,
    )


# ── Execution logs ────────────────────────────────────────────────


@router.get(
    "/businesses/{business_id}/agent-execution-logs",
    response_model=list[ExecutionLogRead],
)
async def list_execution_logs(
    business_id: uuid.UUID,
    agent_type: str | None = Query(None, description="Filter by agent type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    _user: User = Depends(require_business_member),
):
    """List agent execution audit logs for a business."""
    from sqlalchemy import select

    from app.domain.agent.models import AgentExecutionLog

    query = select(AgentExecutionLog).where(
        AgentExecutionLog.business_id == business_id,
        AgentExecutionLog.deleted_at.is_(None),
    )
    if agent_type:
        query = query.where(AgentExecutionLog.agent_type == agent_type)
    query = query.order_by(AgentExecutionLog.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())
