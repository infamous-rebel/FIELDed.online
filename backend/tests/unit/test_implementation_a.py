"""Tests for Implementation A — Proposal decisions + Structured responses.

Covers:
- Proposal approve/reject with brain_id ownership verification
- Conflict handling (already decided, stale)
- Cross-tenant isolation
- Structured response validation (all block types, malformed, unknown)
- Safe fallback for historical messages
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.business.brain_response import (
    safe_parse_brain_response,
    validate_brain_response,
)
from app.domain.common.enums import BrainProposalStatus

# ---------------------------------------------------------------------------
# Proposal decision tests (unit-level, mock repository)
# ---------------------------------------------------------------------------


class TestApproveProposalOwnership:
    """Verify approve_proposal enforces brain_id ownership."""

    @pytest.fixture()
    def mock_service(self):
        """Create a BrainConversationService with mocked dependencies."""
        from app.domain.business.conversation_service import BrainConversationService

        session = MagicMock()
        ai_provider = MagicMock()
        service = BrainConversationService(session, ai_provider)
        service.proposal_repo = AsyncMock()
        service.brain_repo = AsyncMock()
        service.version_repo = AsyncMock()
        service.rule_repo = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_approve_proposal_not_found(self, mock_service):
        """Approving a non-existent proposal raises NotFoundError."""
        from app.exceptions import NotFoundError

        mock_service.proposal_repo.get_by_id.return_value = None

        with pytest.raises(NotFoundError):
            await mock_service.approve_proposal(uuid.uuid4(), brain_id=uuid.uuid4())

    @pytest.mark.asyncio
    async def test_approve_proposal_cross_tenant_blocked(self, mock_service):
        """Approving a proposal from a different brain is blocked."""
        from app.exceptions import TenantIsolationError

        proposal = MagicMock()
        proposal.brain_id = uuid.uuid4()
        proposal.status = BrainProposalStatus.PENDING
        mock_service.proposal_repo.get_by_id.return_value = proposal

        different_brain_id = uuid.uuid4()
        with pytest.raises(TenantIsolationError):
            await mock_service.approve_proposal(uuid.uuid4(), brain_id=different_brain_id)

    @pytest.mark.asyncio
    async def test_approve_already_approved_raises_conflict(self, mock_service):
        """Approving an already-approved proposal raises ConflictError."""
        from app.exceptions import ConflictError

        proposal = MagicMock()
        proposal.brain_id = uuid.uuid4()
        proposal.status = BrainProposalStatus.APPROVED
        mock_service.proposal_repo.get_by_id.return_value = proposal

        with pytest.raises(ConflictError) as exc_info:
            await mock_service.approve_proposal(uuid.uuid4(), brain_id=proposal.brain_id)
        assert "approved" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_approve_already_rejected_raises_conflict(self, mock_service):
        """Approving a rejected proposal raises ConflictError."""
        from app.exceptions import ConflictError

        proposal = MagicMock()
        proposal.brain_id = uuid.uuid4()
        proposal.status = BrainProposalStatus.REJECTED
        mock_service.proposal_repo.get_by_id.return_value = proposal

        with pytest.raises(ConflictError):
            await mock_service.approve_proposal(uuid.uuid4(), brain_id=proposal.brain_id)

    @pytest.mark.asyncio
    async def test_reject_proposal_cross_tenant_blocked(self, mock_service):
        """Rejecting a proposal from a different brain is blocked."""
        from app.exceptions import TenantIsolationError

        proposal = MagicMock()
        proposal.brain_id = uuid.uuid4()
        proposal.status = BrainProposalStatus.PENDING
        mock_service.proposal_repo.get_by_id.return_value = proposal

        with pytest.raises(TenantIsolationError):
            await mock_service.reject_proposal(uuid.uuid4(), brain_id=uuid.uuid4())

    @pytest.mark.asyncio
    async def test_reject_already_rejected_raises_conflict(self, mock_service):
        """Rejecting an already-rejected proposal raises ConflictError."""
        from app.exceptions import ConflictError

        proposal = MagicMock()
        proposal.brain_id = uuid.uuid4()
        proposal.status = BrainProposalStatus.REJECTED
        mock_service.proposal_repo.get_by_id.return_value = proposal

        with pytest.raises(ConflictError):
            await mock_service.reject_proposal(uuid.uuid4(), brain_id=proposal.brain_id)

    @pytest.mark.asyncio
    async def test_approve_without_brain_id_still_works(self, mock_service):
        """Backward compatibility: approve without brain_id skips ownership check."""

        proposal = MagicMock()
        proposal.brain_id = uuid.uuid4()
        proposal.status = BrainProposalStatus.PENDING
        proposal.proposed_change = {"summary": "test"}
        proposal.id = uuid.uuid4()
        mock_service.proposal_repo.get_by_id.return_value = proposal
        mock_service.proposal_repo.update.return_value = proposal

        # Mock _apply_proposal_to_brain to avoid actual brain operations
        mock_service._apply_proposal_to_brain = AsyncMock()

        result = await mock_service.approve_proposal(uuid.uuid4())
        assert result.status in (
            BrainProposalStatus.APPROVED,
            BrainProposalStatus.APPLIED,
        )


# ---------------------------------------------------------------------------
# Structured response validation tests
# ---------------------------------------------------------------------------


class TestStructuredResponseValidation:
    """Test the structured response validation contract."""

    def test_valid_text_block(self):
        """A valid text block passes validation."""
        data = {"version": 1, "blocks": [{"type": "text", "content": "Hello"}]}
        result = validate_brain_response(data)
        assert result is not None
        assert len(result.blocks) == 1
        assert result.blocks[0].type == "text"
        assert result.blocks[0].content == "Hello"

    def test_valid_observation_block(self):
        """A valid observation block passes validation."""
        data = {
            "version": 1,
            "blocks": [
                {
                    "type": "observation",
                    "title": "Pricing gap",
                    "content": "No base pricing configured",
                    "evidence": ["services_config is empty"],
                }
            ],
        }
        result = validate_brain_response(data)
        assert result is not None
        assert len(result.blocks) == 1
        assert result.blocks[0].type == "observation"

    def test_valid_reasoning_block(self):
        data = {
            "version": 1,
            "blocks": [
                {
                    "type": "reasoning",
                    "title": "Why this matters",
                    "content": "Without pricing, quotes cannot be generated",
                }
            ],
        }
        result = validate_brain_response(data)
        assert result is not None
        assert result.blocks[0].type == "reasoning"

    def test_valid_recommendation_block(self):
        data = {
            "version": 1,
            "blocks": [
                {
                    "type": "recommendation",
                    "title": "Set base pricing",
                    "content": "Configure base pricing for your services",
                    "actions": ["Define hourly rate", "Define fixed-price options"],
                }
            ],
        }
        result = validate_brain_response(data)
        assert result is not None
        assert result.blocks[0].type == "recommendation"
        assert len(result.blocks[0].actions) == 2

    def test_valid_question_block(self):
        data = {
            "version": 1,
            "blocks": [
                {
                    "type": "question",
                    "question": "What is your hourly rate?",
                    "options": ["$50-100", "$100-200", "$200+"],
                    "allow_custom": True,
                }
            ],
        }
        result = validate_brain_response(data)
        assert result is not None
        assert result.blocks[0].type == "question"
        assert result.blocks[0].allow_custom is True

    def test_valid_missing_information_block(self):
        data = {
            "version": 1,
            "blocks": [
                {
                    "type": "missing_information",
                    "title": "Cancellation policy",
                    "content": "No cancellation policy defined",
                    "field": "cancellation_policy",
                    "options": ["Full refund", "Partial refund", "No refund"],
                }
            ],
        }
        result = validate_brain_response(data)
        assert result is not None
        assert result.blocks[0].type == "missing_information"

    def test_valid_proposal_block(self):
        proposal_id = str(uuid.uuid4())
        data = {
            "version": 1,
            "blocks": [
                {
                    "type": "proposal",
                    "proposal_id": proposal_id,
                    "title": "New consulting service",
                    "summary": "Add business consulting at $150/hr",
                    "why": "High demand from enquiries",
                    "change": "Add service_definition rule",
                    "scope": "services",
                    "expected_effect": "Enable quoting for consulting",
                    "evidence": ["5 enquiries this month"],
                    "status": "pending",
                }
            ],
        }
        result = validate_brain_response(data)
        assert result is not None
        assert result.blocks[0].type == "proposal"
        assert result.has_proposal
        assert result.proposal_ids == [proposal_id]

    def test_valid_navigation_block(self):
        data = {
            "version": 1,
            "blocks": [
                {
                    "type": "navigation",
                    "label": "View services",
                    "destination": "business.services",
                    "context": {},
                }
            ],
        }
        result = validate_brain_response(data)
        assert result is not None
        assert result.blocks[0].type == "navigation"

    def test_invalid_navigation_destination_rejected(self):
        """Navigation to an unknown destination is dropped."""
        data = {
            "version": 1,
            "blocks": [
                {
                    "type": "navigation",
                    "label": "Go somewhere",
                    "destination": "evil.external.site",
                }
            ],
        }
        result = validate_brain_response(data)
        assert result is not None
        assert len(result.blocks) == 0  # Block dropped

    def test_unknown_block_type_dropped(self):
        """Unknown block types are silently dropped, not crashing."""
        data = {
            "version": 1,
            "blocks": [
                {"type": "unknown_type", "content": "something"},
                {"type": "text", "content": "valid"},
            ],
        }
        result = validate_brain_response(data)
        assert result is not None
        assert len(result.blocks) == 1
        assert result.blocks[0].type == "text"

    def test_missing_required_fields_drops_block(self):
        """Blocks missing required fields are dropped."""
        data = {
            "version": 1,
            "blocks": [
                {"type": "observation"},  # Missing title and content
                {"type": "text", "content": "valid"},
            ],
        }
        result = validate_brain_response(data)
        assert result is not None
        assert len(result.blocks) == 1  # observation dropped, text kept

    def test_malformed_payload_returns_none(self):
        """safe_parse_brain_response returns None for completely malformed data."""
        assert safe_parse_brain_response(None) is None
        assert safe_parse_brain_response("not a dict") is None
        assert safe_parse_brain_response(42) is None

    def test_empty_blocks(self):
        """Empty blocks list is valid."""
        data = {"version": 1, "blocks": []}
        result = validate_brain_response(data)
        assert result is not None
        assert len(result.blocks) == 0

    def test_blocks_bounded(self):
        """More than MAX_BLOCKS_PER_RESPONSE blocks are truncated."""
        from app.domain.business.brain_response import MAX_BLOCKS_PER_RESPONSE

        blocks = [{"type": "text", "content": f"msg {i}"} for i in range(60)]
        data = {"version": 1, "blocks": blocks}
        result = validate_brain_response(data)
        assert result is not None
        assert len(result.blocks) == MAX_BLOCKS_PER_RESPONSE

    def test_invalid_proposal_id_rejected(self):
        """Proposal block with non-UUID proposal_id is dropped."""
        data = {
            "version": 1,
            "blocks": [
                {
                    "type": "proposal",
                    "proposal_id": "not-a-uuid",
                    "title": "Bad proposal",
                    "summary": "Should be dropped",
                }
            ],
        }
        result = validate_brain_response(data)
        assert result is not None
        assert len(result.blocks) == 0

    def test_multiple_block_types(self):
        """A response with multiple block types validates correctly."""
        data = {
            "version": 1,
            "blocks": [
                {"type": "text", "content": "Here's what I found"},
                {
                    "type": "observation",
                    "title": "Gap",
                    "content": "No pricing configured",
                    "evidence": [],
                },
                {
                    "type": "recommendation",
                    "title": "Action",
                    "content": "Set up pricing",
                    "actions": ["Define rates"],
                },
            ],
        }
        result = validate_brain_response(data)
        assert result is not None
        assert len(result.blocks) == 3

    def test_structured_output_cannot_mutate_brain_state(self):
        """Structured response is data only — it has no methods to mutate state."""
        data = {"version": 1, "blocks": [{"type": "text", "content": "test"}]}
        result = validate_brain_response(data)
        assert result is not None
        # BrainStructuredResponse is a Pydantic model with no side effects
        # It has no methods to activate versions, modify rules, etc.
        assert not hasattr(result, "activate_version")
        assert not hasattr(result, "modify_rules")
        assert not hasattr(result, "execute")


class TestBuildStructuredResponse:
    """Test the service's _build_structured_response method."""

    def test_build_from_plain_text(self):
        """Plain text response gets wrapped in a text block."""
        from app.domain.business.conversation_service import BrainConversationService

        result = BrainConversationService._build_structured_response("Hello, owner!", None)
        assert result is not None
        assert len(result.blocks) == 1
        assert result.blocks[0].type == "text"
        assert result.blocks[0].content == "Hello, owner!"

    def test_build_from_empty_text_returns_none(self):
        """Empty text returns None (fallback to plain rendering)."""
        from app.domain.business.conversation_service import BrainConversationService

        result = BrainConversationService._build_structured_response("", None)
        assert result is None

    def test_build_from_whitespace_only_returns_none(self):
        from app.domain.business.conversation_service import BrainConversationService

        result = BrainConversationService._build_structured_response("   ", None)
        assert result is None
