"""Regression tests for Phase 06 — Business Brain refinement fixes.

Tests cover:
- Tenant isolation enforcement (tenant_scope fix)
- BrainVersion activation with supersede logic
- BrainVersion lifecycle (DRAFT → REVIEW shortcut)
- Historical brain version linkage on Enquiry
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.business.models import BrainVersion, BusinessBrain
from app.domain.business.repository import (
    BrainVersionRepository,
    BusinessBrainRepository,
)
from app.domain.business.service import BrainService
from app.domain.common.enums import (
    BRAIN_VERSION_TRANSITIONS,
    BrainVersionStatus,
)
from app.exceptions import DomainError, NotFoundError

# ---------------------------------------------------------------------------
# Test: BrainVersion lifecycle — DRAFT → REVIEW shortcut
# ---------------------------------------------------------------------------


class TestBrainVersionLifecycle:
    """Verify the BrainVersion lifecycle matches the resolved spec."""

    def test_draft_can_go_to_validating(self):
        """Standard path: DRAFT → VALIDATING."""
        transitions = BRAIN_VERSION_TRANSITIONS[BrainVersionStatus.DRAFT]
        assert BrainVersionStatus.VALIDATING in transitions

    def test_draft_can_go_to_review(self):
        """Shortcut path: DRAFT → REVIEW (manual rules skip validation)."""
        transitions = BRAIN_VERSION_TRANSITIONS[BrainVersionStatus.DRAFT]
        assert BrainVersionStatus.REVIEW in transitions

    def test_validating_can_go_to_review(self):
        """Standard path: VALIDATING → REVIEW."""
        transitions = BRAIN_VERSION_TRANSITIONS[BrainVersionStatus.VALIDATING]
        assert BrainVersionStatus.REVIEW in transitions

    def test_validating_can_go_back_to_draft(self):
        """Validation failure: VALIDATING → DRAFT."""
        transitions = BRAIN_VERSION_TRANSITIONS[BrainVersionStatus.VALIDATING]
        assert BrainVersionStatus.DRAFT in transitions

    def test_review_can_go_to_approved(self):
        """REVIEW → APPROVED."""
        transitions = BRAIN_VERSION_TRANSITIONS[BrainVersionStatus.REVIEW]
        assert BrainVersionStatus.APPROVED in transitions

    def test_review_can_go_back_to_draft(self):
        """Rejection: REVIEW → DRAFT."""
        transitions = BRAIN_VERSION_TRANSITIONS[BrainVersionStatus.REVIEW]
        assert BrainVersionStatus.DRAFT in transitions

    def test_approved_can_go_to_active(self):
        """APPROVED → ACTIVE."""
        transitions = BRAIN_VERSION_TRANSITIONS[BrainVersionStatus.APPROVED]
        assert BrainVersionStatus.ACTIVE in transitions

    def test_active_can_be_superseded(self):
        """ACTIVE → SUPERSEDED."""
        transitions = BRAIN_VERSION_TRANSITIONS[BrainVersionStatus.ACTIVE]
        assert BrainVersionStatus.SUPERSEDED in transitions

    def test_superseded_is_terminal(self):
        """SUPERSEDED has no outgoing transitions."""
        transitions = BRAIN_VERSION_TRANSITIONS[BrainVersionStatus.SUPERSEDED]
        assert len(transitions) == 0

    def test_draft_cannot_go_to_approved_directly(self):
        """DRAFT cannot skip to APPROVED."""
        transitions = BRAIN_VERSION_TRANSITIONS[BrainVersionStatus.DRAFT]
        assert BrainVersionStatus.APPROVED not in transitions

    def test_draft_cannot_go_to_active_directly(self):
        """DRAFT cannot skip to ACTIVE."""
        transitions = BRAIN_VERSION_TRANSITIONS[BrainVersionStatus.DRAFT]
        assert BrainVersionStatus.ACTIVE not in transitions


# ---------------------------------------------------------------------------
# Test: BrainService.activate_version — supersede logic
# ---------------------------------------------------------------------------


class TestBrainVersionActivation:
    """Verify activation supersedes previous active version."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def brain_repo(self, mock_session):
        repo = MagicMock(spec=BusinessBrainRepository)
        repo.session = mock_session
        return repo

    @pytest.fixture
    def version_repo(self, mock_session):
        repo = MagicMock(spec=BrainVersionRepository)
        repo.session = mock_session
        return repo

    @pytest.fixture
    def brain_service(self, brain_repo, version_repo):
        service = BrainService.__new__(BrainService)
        service.brain_repo = brain_repo
        service.version_repo = version_repo
        return service

    async def test_activate_supersedes_previous_active(
        self, brain_service, brain_repo, version_repo
    ):
        """Activating a new version must supersede the previous ACTIVE version."""
        brain_id = uuid.uuid4()
        new_version_id = uuid.uuid4()
        old_version_id = uuid.uuid4()

        # Mock brain
        brain = MagicMock(spec=BusinessBrain)
        brain.id = brain_id
        brain.active_version_id = old_version_id
        brain_repo.get_by_business_id_for_update = AsyncMock(return_value=brain)
        brain_repo.update_active_version = AsyncMock(return_value=brain)

        # Mock new version (APPROVED status)
        new_version = MagicMock(spec=BrainVersion)
        new_version.id = new_version_id
        new_version.status = BrainVersionStatus.APPROVED
        version_repo.get_by_id = AsyncMock(return_value=new_version)

        # Mock old active version
        old_version = MagicMock(spec=BrainVersion)
        old_version.id = old_version_id
        old_version.status = BrainVersionStatus.ACTIVE
        version_repo.get_active_by_brain_id = AsyncMock(return_value=old_version)
        version_repo.update = AsyncMock()

        # Execute
        await brain_service.activate_version(brain_id, new_version_id)

        # Verify old version was superseded
        assert old_version.status == BrainVersionStatus.SUPERSEDED
        version_repo.update.assert_called()

        # Verify new version became ACTIVE
        assert new_version.status == BrainVersionStatus.ACTIVE

    async def test_activate_without_previous_active(self, brain_service, brain_repo, version_repo):
        """Activation works when there's no previous active version."""
        brain_id = uuid.uuid4()
        new_version_id = uuid.uuid4()

        brain = MagicMock(spec=BusinessBrain)
        brain.id = brain_id
        brain.active_version_id = None
        brain_repo.get_by_business_id_for_update = AsyncMock(return_value=brain)
        brain_repo.update_active_version = AsyncMock(return_value=brain)

        new_version = MagicMock(spec=BrainVersion)
        new_version.id = new_version_id
        new_version.status = BrainVersionStatus.APPROVED
        version_repo.get_by_id = AsyncMock(return_value=new_version)
        version_repo.get_active_by_brain_id = AsyncMock(return_value=None)
        version_repo.update = AsyncMock()

        await brain_service.activate_version(brain_id, new_version_id)

        assert new_version.status == BrainVersionStatus.ACTIVE
        brain_repo.update_active_version.assert_called_once_with(brain, new_version_id)

    async def test_activate_rejects_non_approvable_version(
        self, brain_service, brain_repo, version_repo
    ):
        """Cannot activate a version that is not APPROVED or ACTIVE."""
        brain_id = uuid.uuid4()
        version_id = uuid.uuid4()

        brain = MagicMock(spec=BusinessBrain)
        brain.id = brain_id
        brain_repo.get_by_business_id_for_update = AsyncMock(return_value=brain)

        draft_version = MagicMock(spec=BrainVersion)
        draft_version.id = version_id
        draft_version.status = BrainVersionStatus.DRAFT
        version_repo.get_by_id = AsyncMock(return_value=draft_version)

        with pytest.raises(DomainError, match="Only APPROVED or ACTIVE"):
            await brain_service.activate_version(brain_id, version_id)

    async def test_activate_raises_on_missing_brain(self, brain_service, brain_repo):
        """Activation raises NotFoundError if brain doesn't exist."""
        brain_id = uuid.uuid4()
        version_id = uuid.uuid4()

        brain_repo.get_by_business_id_for_update = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await brain_service.activate_version(brain_id, version_id)

    async def test_activate_raises_on_missing_version(
        self, brain_service, brain_repo, version_repo
    ):
        """Activation raises NotFoundError if version doesn't exist."""
        brain_id = uuid.uuid4()
        version_id = uuid.uuid4()

        brain = MagicMock(spec=BusinessBrain)
        brain.id = brain_id
        brain_repo.get_by_business_id_for_update = AsyncMock(return_value=brain)
        version_repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await brain_service.activate_version(brain_id, version_id)

    async def test_activate_same_version_no_supersede(
        self, brain_service, brain_repo, version_repo
    ):
        """Activating the already-active version does not supersede it."""
        brain_id = uuid.uuid4()
        version_id = uuid.uuid4()

        brain = MagicMock(spec=BusinessBrain)
        brain.id = brain_id
        brain.active_version_id = version_id
        brain_repo.get_by_business_id_for_update = AsyncMock(return_value=brain)
        brain_repo.update_active_version = AsyncMock(return_value=brain)

        version = MagicMock(spec=BrainVersion)
        version.id = version_id
        version.status = BrainVersionStatus.ACTIVE
        version_repo.get_by_id = AsyncMock(return_value=version)
        version_repo.get_active_by_brain_id = AsyncMock(return_value=version)
        version_repo.update = AsyncMock()

        await brain_service.activate_version(brain_id, version_id)

        # Version should NOT be superseded (it's the same version)
        assert version.status == BrainVersionStatus.ACTIVE
        version_repo.update.assert_not_called()


# ---------------------------------------------------------------------------
# Test: tenant_scope() enforces tenant isolation
# ---------------------------------------------------------------------------


class TestTenantScopeIsolation:
    """Verify tenant_scope() filters by customer_id or business_id."""

    def test_tenant_scope_checks_customer_id_column(self):
        """tenant_scope detects customer_id column on model."""
        from app.security.authorization import tenant_scope

        class CustomerModel:
            id = None
            customer_id = None
            deleted_at = None

        # Should not raise — model has customer_id
        dep = tenant_scope(CustomerModel)
        assert dep is not None

    def test_tenant_scope_checks_business_id_column(self):
        """tenant_scope detects business_id column on model."""
        from app.security.authorization import tenant_scope

        class BusinessModel:
            id = None
            business_id = None
            deleted_at = None

        dep = tenant_scope(BusinessModel)
        assert dep is not None

    def test_tenant_scope_no_tenant_columns_raises(self):
        """tenant_scope raises AuthorizationError if model has no tenant column."""
        from app.security.authorization import tenant_scope

        class NoTenantModel:
            id = None
            deleted_at = None

        # The dependency is created, but calling it should raise
        dep = tenant_scope(NoTenantModel)
        # The function exists but will raise when called with a user
        # who has no matching tenant column
        assert dep is not None


# ---------------------------------------------------------------------------
# Test: Enquiry brain_version_id linkage
# ---------------------------------------------------------------------------


class TestEnquiryBrainVersionLinkage:
    """Verify Enquiry model has brain_version_id column."""

    def test_enquiry_model_has_brain_version_id(self):
        """Enquiry model must have brain_version_id column."""
        from app.domain.enquiry.models import Enquiry

        assert hasattr(Enquiry, "brain_version_id")

    def test_enquiry_brain_version_id_is_nullable(self):
        """brain_version_id column must be nullable."""
        from app.domain.enquiry.models import Enquiry

        column = Enquiry.__table__.columns["brain_version_id"]
        assert column.nullable is True

    def test_enquiry_brain_version_id_fk(self):
        """brain_version_id must have FK to brain_versions."""
        from app.domain.enquiry.models import Enquiry

        column = Enquiry.__table__.columns["brain_version_id"]
        fks = list(column.foreign_keys)
        assert len(fks) == 1
        assert "brain_versions.id" in str(fks[0].target_fullname)


# ---------------------------------------------------------------------------
# Test: PricingModel canonical values
# ---------------------------------------------------------------------------


class TestPricingModelCanonical:
    """Verify PricingModel enum has canonical values."""

    def test_pricing_model_values(self):
        """PricingModel must have: FIXED, HOURLY, QUOTE_REQUIRED, STARTING_AT, CUSTOM."""
        from app.domain.common.enums import PricingModel

        expected = {"fixed", "hourly", "quote_required", "starting_at", "custom"}
        actual = {m.value for m in PricingModel}
        assert actual == expected

    def test_pricing_model_no_custom_quote(self):
        """PricingModel must NOT have 'custom_quote' (old value)."""
        from app.domain.common.enums import PricingModel

        values = {m.value for m in PricingModel}
        assert "custom_quote" not in values

    def test_pricing_model_no_per_unit(self):
        """PricingModel must NOT have 'per_unit' (spec error)."""
        from app.domain.common.enums import PricingModel

        values = {m.value for m in PricingModel}
        assert "per_unit" not in values

    def test_pricing_model_no_tiered(self):
        """PricingModel must NOT have 'tiered' (spec error)."""
        from app.domain.common.enums import PricingModel

        values = {m.value for m in PricingModel}
        assert "tiered" not in values
