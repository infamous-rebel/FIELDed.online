"""Unit tests for agent capability and delegation architecture.

Tests cover:
- Enum completeness and value correctness
- Policy constraint validation logic
- Authorization result semantics
- Authority mode transitions
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.agent.service import (
    AgentAuthorizationResult,
    AgentCapabilityService,
    _validate_policy_constraints,
)
from app.domain.common.enums import (
    AgentAuthorityMode,
    AgentCapabilityType,
    AgentDelegationStatus,
    AgentType,
)

# ── Enum tests ────────────────────────────────────────────────────


class TestAgentEnums:
    """Verify agent architecture enums are complete and correct."""

    def test_agent_types(self):
        """All expected agent types exist."""
        assert AgentType.DISCOVERY == "discovery"
        assert AgentType.BRAIN == "brain"
        assert AgentType.CALL_AGENT == "call_agent"
        assert AgentType.MARKETING == "marketing"

    def test_authority_modes(self):
        """All authority modes exist."""
        assert AgentAuthorityMode.DISABLED == "disabled"
        assert AgentAuthorityMode.ASSIST == "assist"
        assert AgentAuthorityMode.APPROVAL == "approval"
        assert AgentAuthorityMode.DELEGATED == "delegated"

    def test_delegation_statuses(self):
        """All delegation statuses exist."""
        assert AgentDelegationStatus.ACTIVE == "active"
        assert AgentDelegationStatus.REVOKED == "revoked"
        assert AgentDelegationStatus.EXPIRED == "expired"

    def test_capability_types_include_discovery(self):
        """Discovery capabilities exist."""
        assert AgentCapabilityType.INTERPRET_INTENT == "interpret_intent"
        assert AgentCapabilityType.MATCH_BUSINESSES == "match_businesses"

    def test_capability_types_include_brain(self):
        """Brain capabilities exist."""
        assert AgentCapabilityType.READ_BUSINESS_CONTEXT == "read_business_context"
        assert AgentCapabilityType.PROPOSE_CHANGES == "propose_changes"
        assert AgentCapabilityType.ACTIVATE_BRAIN_VERSION == "activate_brain_version"

    def test_capability_types_include_call_agent(self):
        """Call agent capabilities exist."""
        assert AgentCapabilityType.HANDLE_INBOUND_CALL == "handle_inbound_call"
        assert AgentCapabilityType.MAKE_OUTBOUND_CALL == "make_outbound_call"
        assert AgentCapabilityType.ESCALATE_CALL == "escalate_call"

    def test_capability_types_include_marketing(self):
        """Marketing capabilities exist."""
        assert AgentCapabilityType.DRAFT_CONTENT == "draft_content"
        assert AgentCapabilityType.SCHEDULE_CAMPAIGN == "schedule_campaign"
        assert AgentCapabilityType.EXECUTE_CAMPAIGN == "execute_campaign"

    def test_capability_types_include_communication(self):
        """Communication capabilities exist."""
        assert AgentCapabilityType.SEND_MESSAGE == "send_message"
        assert AgentCapabilityType.SEND_NOTIFICATION == "send_notification"


# ── Policy constraint validation ──────────────────────────────────


class TestPolicyConstraintValidation:
    """Test the deterministic policy constraint validator."""

    def test_no_constraints_pass(self):
        """Empty constraints always pass."""
        valid, reason = _validate_policy_constraints({}, {"amount": "100"})
        assert valid is True
        assert reason == ""

    def test_amount_within_limit(self):
        """Amount within max passes."""
        constraints = {"max_amount": "500"}
        context = {"amount": "250"}
        valid, reason = _validate_policy_constraints(constraints, context)
        assert valid is True

    def test_amount_exceeds_limit(self):
        """Amount exceeding max fails."""
        constraints = {"max_amount": "100"}
        context = {"amount": "250"}
        valid, reason = _validate_policy_constraints(constraints, context)
        assert valid is False
        assert "exceeds max" in reason

    def test_amount_at_exact_limit(self):
        """Amount exactly at max passes."""
        constraints = {"max_amount": "100"}
        context = {"amount": "100"}
        valid, reason = _validate_policy_constraints(constraints, context)
        assert valid is True

    def test_currency_match(self):
        """Matching currency passes."""
        constraints = {"currency": "AUD"}
        context = {"currency": "AUD"}
        valid, reason = _validate_policy_constraints(constraints, context)
        assert valid is True

    def test_currency_mismatch(self):
        """Mismatched currency fails."""
        constraints = {"currency": "AUD"}
        context = {"currency": "USD"}
        valid, reason = _validate_policy_constraints(constraints, context)
        assert valid is False
        assert "not allowed" in reason

    def test_currency_case_insensitive(self):
        """Currency check is case-insensitive."""
        constraints = {"currency": "aud"}
        context = {"currency": "AUD"}
        valid, reason = _validate_policy_constraints(constraints, context)
        assert valid is True

    def test_requires_enquiry_with_enquiry(self):
        """Action with enquiry_id passes requires_enquiry."""
        constraints = {"requires_enquiry": True}
        context = {"enquiry_id": str(uuid.uuid4())}
        valid, reason = _validate_policy_constraints(constraints, context)
        assert valid is True

    def test_requires_enquiry_without_enquiry(self):
        """Action without enquiry_id fails requires_enquiry."""
        constraints = {"requires_enquiry": True}
        context = {}
        valid, reason = _validate_policy_constraints(constraints, context)
        assert valid is False
        assert "requires an associated enquiry" in reason

    def test_combined_constraints_all_pass(self):
        """Multiple constraints all passing."""
        constraints = {"max_amount": "1000", "currency": "AUD"}
        context = {"amount": "500", "currency": "AUD"}
        valid, reason = _validate_policy_constraints(constraints, context)
        assert valid is True

    def test_combined_constraints_amount_fails(self):
        """Multiple constraints where amount fails."""
        constraints = {"max_amount": "100", "currency": "AUD"}
        context = {"amount": "500", "currency": "AUD"}
        valid, reason = _validate_policy_constraints(constraints, context)
        assert valid is False

    def test_no_amount_in_context_skips_amount_check(self):
        """If context has no amount, max_amount constraint is skipped."""
        constraints = {"max_amount": "100"}
        context = {"currency": "AUD"}
        valid, reason = _validate_policy_constraints(constraints, context)
        assert valid is True


# ── Authorization result ──────────────────────────────────────────


class TestAuthorizationResult:
    """Test the AgentAuthorizationResult dataclass."""

    def test_authorized_is_truthy(self):
        """Authorized result evaluates to True."""
        result = AgentAuthorizationResult(
            authorized=True,
            authority_mode=AgentAuthorityMode.DELEGATED,
            delegation=None,
            reason="OK",
        )
        assert bool(result) is True

    def test_unauthorized_is_falsy(self):
        """Unauthorized result evaluates to False."""
        result = AgentAuthorizationResult(
            authorized=False,
            authority_mode=AgentAuthorityMode.DISABLED,
            delegation=None,
            reason="Denied",
        )
        assert bool(result) is False

    def test_result_preserves_mode(self):
        """Result preserves the authority mode."""
        for mode in AgentAuthorityMode:
            result = AgentAuthorizationResult(
                authorized=True,
                authority_mode=mode,
                delegation=None,
                reason="test",
            )
            assert result.authority_mode == mode

    def test_result_preserves_reason(self):
        """Result preserves the reason string."""
        result = AgentAuthorizationResult(
            authorized=False,
            authority_mode=AgentAuthorityMode.DISABLED,
            delegation=None,
            reason="Capability is disabled",
        )
        assert result.reason == "Capability is disabled"


# ── Service unit tests (mock session) ─────────────────────────────


class TestAgentCapabilityServiceUnit:
    """Test service methods with mock sessions."""

    @pytest.mark.asyncio
    async def test_check_authorization_no_capability(self):
        """Authorization check returns denied when no capability exists."""
        session = AsyncMock()
        # Mock the query result to return None (no capability found)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        service = AgentCapabilityService(session)
        biz_id = uuid.uuid4()
        result = await service.check_authorization(
            biz_id,
            AgentType.BRAIN,
            AgentCapabilityType.PROPOSE_CHANGES,
        )

        assert result.authorized is False
        assert result.authority_mode == AgentAuthorityMode.DISABLED
        assert "No capability configured" in result.reason

    @pytest.mark.asyncio
    async def test_check_authorization_disabled(self):
        """Authorization check returns denied for disabled capability."""
        session = AsyncMock()
        mock_capability = MagicMock()
        mock_capability.authority_mode = "disabled"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_capability
        session.execute.return_value = mock_result

        service = AgentCapabilityService(session)
        biz_id = uuid.uuid4()
        result = await service.check_authorization(
            biz_id,
            AgentType.BRAIN,
            AgentCapabilityType.PROPOSE_CHANGES,
        )

        assert result.authorized is False
        assert result.authority_mode == AgentAuthorityMode.DISABLED
        assert "disabled" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_check_authorization_assist_mode(self):
        """Assist mode allows reading/proposing but not executing."""
        session = AsyncMock()
        mock_capability = MagicMock()
        mock_capability.authority_mode = "assist"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_capability
        session.execute.return_value = mock_result

        service = AgentCapabilityService(session)
        biz_id = uuid.uuid4()
        result = await service.check_authorization(
            biz_id,
            AgentType.BRAIN,
            AgentCapabilityType.PROPOSE_CHANGES,
        )

        assert result.authorized is True
        assert result.authority_mode == AgentAuthorityMode.ASSIST

    @pytest.mark.asyncio
    async def test_check_authorization_approval_mode(self):
        """Approval mode allows with explicit approval requirement."""
        session = AsyncMock()
        mock_capability = MagicMock()
        mock_capability.authority_mode = "approval"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_capability
        session.execute.return_value = mock_result

        service = AgentCapabilityService(session)
        biz_id = uuid.uuid4()
        result = await service.check_authorization(
            biz_id,
            AgentType.CALL_AGENT,
            AgentCapabilityType.HANDLE_INBOUND_CALL,
        )

        assert result.authorized is True
        assert result.authority_mode == AgentAuthorityMode.APPROVAL

    @pytest.mark.asyncio
    async def test_check_authorization_delegated_no_delegation(self):
        """Delegated mode without active delegation is denied."""
        session = AsyncMock()
        mock_capability = MagicMock()
        mock_capability.authority_mode = "delegated"
        mock_capability.policy_constraints = None

        # First call returns capability, subsequent calls for delegation return None
        mock_result_cap = MagicMock()
        mock_result_cap.scalar_one_or_none.return_value = mock_capability

        mock_result_del = MagicMock()
        mock_result_del.scalars.return_value.all.return_value = []

        session.execute.side_effect = [mock_result_cap, mock_result_del]

        service = AgentCapabilityService(session)
        biz_id = uuid.uuid4()
        result = await service.check_authorization(
            biz_id,
            AgentType.CALL_AGENT,
            AgentCapabilityType.MAKE_OUTBOUND_CALL,
        )

        assert result.authorized is False
        assert "no active delegation" in result.reason.lower()
