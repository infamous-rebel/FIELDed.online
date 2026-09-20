"""Unit tests for Service Offer lifecycle state machine."""

from app.domain.common.enums import (
    SERVICE_OFFER_TRANSITIONS,
    ServiceOfferStatus,
)


class TestServiceOfferLifecycle:
    """Test the ServiceOffer state machine."""

    def test_draft_can_activate(self):
        allowed = SERVICE_OFFER_TRANSITIONS[ServiceOfferStatus.DRAFT]
        assert ServiceOfferStatus.ACTIVE in allowed

    def test_draft_can_archive(self):
        allowed = SERVICE_OFFER_TRANSITIONS[ServiceOfferStatus.DRAFT]
        assert ServiceOfferStatus.ARCHIVED in allowed

    def test_draft_cannot_pause(self):
        allowed = SERVICE_OFFER_TRANSITIONS[ServiceOfferStatus.DRAFT]
        assert ServiceOfferStatus.PAUSED not in allowed

    def test_active_can_pause(self):
        allowed = SERVICE_OFFER_TRANSITIONS[ServiceOfferStatus.ACTIVE]
        assert ServiceOfferStatus.PAUSED in allowed

    def test_active_can_archive(self):
        allowed = SERVICE_OFFER_TRANSITIONS[ServiceOfferStatus.ACTIVE]
        assert ServiceOfferStatus.ARCHIVED in allowed

    def test_active_cannot_go_back_to_draft(self):
        allowed = SERVICE_OFFER_TRANSITIONS[ServiceOfferStatus.ACTIVE]
        assert ServiceOfferStatus.DRAFT not in allowed

    def test_paused_can_resume(self):
        allowed = SERVICE_OFFER_TRANSITIONS[ServiceOfferStatus.PAUSED]
        assert ServiceOfferStatus.ACTIVE in allowed

    def test_paused_can_archive(self):
        allowed = SERVICE_OFFER_TRANSITIONS[ServiceOfferStatus.PAUSED]
        assert ServiceOfferStatus.ARCHIVED in allowed

    def test_archived_is_terminal(self):
        allowed = SERVICE_OFFER_TRANSITIONS[ServiceOfferStatus.ARCHIVED]
        assert len(allowed) == 0

    def test_all_statuses_have_transition_entries(self):
        for status in ServiceOfferStatus:
            assert status in SERVICE_OFFER_TRANSITIONS

    def test_full_lifecycle_path(self):
        """DRAFT -> ACTIVE -> PAUSED -> ACTIVE -> ARCHIVED"""
        current = ServiceOfferStatus.DRAFT
        assert ServiceOfferStatus.ACTIVE in SERVICE_OFFER_TRANSITIONS[current]
        current = ServiceOfferStatus.ACTIVE
        assert ServiceOfferStatus.PAUSED in SERVICE_OFFER_TRANSITIONS[current]
        current = ServiceOfferStatus.PAUSED
        assert ServiceOfferStatus.ACTIVE in SERVICE_OFFER_TRANSITIONS[current]
        current = ServiceOfferStatus.ACTIVE
        assert ServiceOfferStatus.ARCHIVED in SERVICE_OFFER_TRANSITIONS[current]
