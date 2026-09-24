"""Unit tests for Enquiry lifecycle state machine.

Tests the Phase 05 enquiry transitions, verifying:
- Valid transitions succeed
- Invalid transitions are rejected
- Terminal states are enforced
- Reserved states are unreachable in Phase 05
- All statuses have transition entries
"""

from __future__ import annotations

from app.domain.common.enums import (
    ENQUIRY_TRANSITIONS,
    EnquiryStatus,
)


class TestEnquiryPhase05Lifecycle:
    """Test the Phase 05 Enquiry state machine."""

    # --- Normal flow transitions ---

    def test_draft_can_submit(self):
        allowed = ENQUIRY_TRANSITIONS[EnquiryStatus.DRAFT]
        assert EnquiryStatus.SUBMITTED in allowed

    def test_draft_can_cancel(self):
        allowed = ENQUIRY_TRANSITIONS[EnquiryStatus.DRAFT]
        assert EnquiryStatus.CANCELLED in allowed

    def test_draft_cannot_go_to_received(self):
        allowed = ENQUIRY_TRANSITIONS[EnquiryStatus.DRAFT]
        assert EnquiryStatus.RECEIVED not in allowed

    def test_submitted_can_be_received(self):
        allowed = ENQUIRY_TRANSITIONS[EnquiryStatus.SUBMITTED]
        assert EnquiryStatus.RECEIVED in allowed

    def test_submitted_can_expire(self):
        allowed = ENQUIRY_TRANSITIONS[EnquiryStatus.SUBMITTED]
        assert EnquiryStatus.EXPIRED in allowed

    def test_submitted_can_cancel(self):
        allowed = ENQUIRY_TRANSITIONS[EnquiryStatus.SUBMITTED]
        assert EnquiryStatus.CANCELLED in allowed

    def test_submitted_cannot_go_back_to_draft(self):
        allowed = ENQUIRY_TRANSITIONS[EnquiryStatus.SUBMITTED]
        assert EnquiryStatus.DRAFT not in allowed

    def test_received_can_review(self):
        allowed = ENQUIRY_TRANSITIONS[EnquiryStatus.RECEIVED]
        assert EnquiryStatus.IN_REVIEW in allowed

    def test_received_can_decline(self):
        allowed = ENQUIRY_TRANSITIONS[EnquiryStatus.RECEIVED]
        assert EnquiryStatus.DECLINED in allowed

    def test_in_review_can_request_info(self):
        allowed = ENQUIRY_TRANSITIONS[EnquiryStatus.IN_REVIEW]
        assert EnquiryStatus.NEEDS_INFORMATION in allowed

    def test_in_review_can_decline(self):
        allowed = ENQUIRY_TRANSITIONS[EnquiryStatus.IN_REVIEW]
        assert EnquiryStatus.DECLINED in allowed

    def test_in_review_cannot_go_to_submitted(self):
        allowed = ENQUIRY_TRANSITIONS[EnquiryStatus.IN_REVIEW]
        assert EnquiryStatus.SUBMITTED not in allowed

    def test_needs_information_can_resume_review(self):
        allowed = ENQUIRY_TRANSITIONS[EnquiryStatus.NEEDS_INFORMATION]
        assert EnquiryStatus.IN_REVIEW in allowed

    def test_needs_information_can_decline(self):
        allowed = ENQUIRY_TRANSITIONS[EnquiryStatus.NEEDS_INFORMATION]
        assert EnquiryStatus.DECLINED in allowed

    # --- Terminal states ---

    def test_declined_is_terminal(self):
        assert len(ENQUIRY_TRANSITIONS[EnquiryStatus.DECLINED]) == 0

    def test_cancelled_is_terminal(self):
        assert len(ENQUIRY_TRANSITIONS[EnquiryStatus.CANCELLED]) == 0

    def test_expired_is_terminal(self):
        assert len(ENQUIRY_TRANSITIONS[EnquiryStatus.EXPIRED]) == 0

    def test_rejected_is_terminal(self):
        assert len(ENQUIRY_TRANSITIONS[EnquiryStatus.REJECTED]) == 0

    # --- Phase 12 states (quote/booking flow) ---

    def test_quoted_has_transitions(self):
        """QUOTED can transition to CUSTOMER_ACCEPTED, EXPIRED, CANCELLED."""
        assert EnquiryStatus.CUSTOMER_ACCEPTED in ENQUIRY_TRANSITIONS[EnquiryStatus.QUOTED]
        assert EnquiryStatus.EXPIRED in ENQUIRY_TRANSITIONS[EnquiryStatus.QUOTED]
        assert EnquiryStatus.CANCELLED in ENQUIRY_TRANSITIONS[EnquiryStatus.QUOTED]

    def test_completed_is_reserved_terminal(self):
        assert len(ENQUIRY_TRANSITIONS[EnquiryStatus.COMPLETED]) == 0

    def test_reserved_states_unreachable(self):
        """Phase 05 early states (DRAFT, SUBMITTED, RECEIVED) cannot reach Phase 12 states.

        IN_REVIEW can transition to QUOTED (Phase 12 quote flow).
        """
        phase12_states = {
            EnquiryStatus.QUOTED,
            EnquiryStatus.CUSTOMER_ACCEPTED,
            EnquiryStatus.BOOKING_PROPOSED,
            EnquiryStatus.BOOKED,
            EnquiryStatus.IN_PROGRESS,
            EnquiryStatus.COMPLETED,
        }
        # Early Phase 05 states must not reach Phase 12 states
        early_states = {
            EnquiryStatus.DRAFT,
            EnquiryStatus.SUBMITTED,
            EnquiryStatus.RECEIVED,
        }
        for status in early_states:
            for target in ENQUIRY_TRANSITIONS.get(status, set()):
                assert target not in phase12_states, f"{status.value} -> {target.value} should not be valid"

    # --- Completeness ---

    def test_all_statuses_have_transition_entries(self):
        for status in EnquiryStatus:
            assert status in ENQUIRY_TRANSITIONS

    # --- Full lifecycle paths ---

    def test_happy_path(self):
        """DRAFT -> SUBMITTED -> RECEIVED -> IN_REVIEW -> NEEDS_INFORMATION -> IN_REVIEW"""
        current = EnquiryStatus.DRAFT
        assert EnquiryStatus.SUBMITTED in ENQUIRY_TRANSITIONS[current]
        current = EnquiryStatus.SUBMITTED
        assert EnquiryStatus.RECEIVED in ENQUIRY_TRANSITIONS[current]
        current = EnquiryStatus.RECEIVED
        assert EnquiryStatus.IN_REVIEW in ENQUIRY_TRANSITIONS[current]
        current = EnquiryStatus.IN_REVIEW
        assert EnquiryStatus.NEEDS_INFORMATION in ENQUIRY_TRANSITIONS[current]
        current = EnquiryStatus.NEEDS_INFORMATION
        assert EnquiryStatus.IN_REVIEW in ENQUIRY_TRANSITIONS[current]

    def test_decline_path(self):
        """DRAFT -> SUBMITTED -> RECEIVED -> DECLINED"""
        current = EnquiryStatus.DRAFT
        assert EnquiryStatus.SUBMITTED in ENQUIRY_TRANSITIONS[current]
        current = EnquiryStatus.SUBMITTED
        assert EnquiryStatus.RECEIVED in ENQUIRY_TRANSITIONS[current]
        current = EnquiryStatus.RECEIVED
        assert EnquiryStatus.DECLINED in ENQUIRY_TRANSITIONS[current]

    def test_cancel_path(self):
        """DRAFT -> CANCELLED"""
        current = EnquiryStatus.DRAFT
        assert EnquiryStatus.CANCELLED in ENQUIRY_TRANSITIONS[current]

    def test_expire_path(self):
        """DRAFT -> SUBMITTED -> EXPIRED"""
        current = EnquiryStatus.DRAFT
        assert EnquiryStatus.SUBMITTED in ENQUIRY_TRANSITIONS[current]
        current = EnquiryStatus.SUBMITTED
        assert EnquiryStatus.EXPIRED in ENQUIRY_TRANSITIONS[current]
