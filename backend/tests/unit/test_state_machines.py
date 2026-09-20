"""Unit tests for state machine transitions."""

from __future__ import annotations

import pytest

from app.domain.common.enums import (
    BOOKING_TRANSITIONS,
    BRAIN_VERSION_TRANSITIONS,
    ENQUIRY_TRANSITIONS,
    BookingStatus,
    BrainVersionStatus,
    EnquiryStatus,
)


class TestEnquiryStateMachine:
    """Test enquiry lifecycle state transitions."""

    def test_draft_can_submit(self):
        """DRAFT -> SUBMITTED is valid."""
        assert EnquiryStatus.SUBMITTED in ENQUIRY_TRANSITIONS[EnquiryStatus.DRAFT]

    def test_draft_can_cancel(self):
        """DRAFT -> CANCELLED is valid."""
        assert EnquiryStatus.CANCELLED in ENQUIRY_TRANSITIONS[EnquiryStatus.DRAFT]

    def test_submitted_cannot_go_back_to_draft(self):
        """SUBMITTED -> DRAFT is not valid."""
        assert EnquiryStatus.DRAFT not in ENQUIRY_TRANSITIONS[EnquiryStatus.SUBMITTED]

    def test_completed_is_terminal(self):
        """COMPLETED has no valid transitions."""
        assert len(ENQUIRY_TRANSITIONS[EnquiryStatus.COMPLETED]) == 0

    def test_declined_is_terminal(self):
        """DECLINED has no valid transitions."""
        assert len(ENQUIRY_TRANSITIONS[EnquiryStatus.DECLINED]) == 0

    def test_cancelled_is_terminal(self):
        """CANCELLED has no valid transitions."""
        assert len(ENQUIRY_TRANSITIONS[EnquiryStatus.CANCELLED]) == 0

    def test_full_happy_path(self):
        """Verify the Phase 05 happy path is valid."""
        path = [
            (EnquiryStatus.DRAFT, EnquiryStatus.SUBMITTED),
            (EnquiryStatus.SUBMITTED, EnquiryStatus.RECEIVED),
            (EnquiryStatus.RECEIVED, EnquiryStatus.IN_REVIEW),
            (EnquiryStatus.IN_REVIEW, EnquiryStatus.NEEDS_INFORMATION),
            (EnquiryStatus.NEEDS_INFORMATION, EnquiryStatus.IN_REVIEW),
        ]
        for from_status, to_status in path:
            assert to_status in ENQUIRY_TRANSITIONS[from_status], (
                f"{from_status} -> {to_status} should be valid"
            )

    def test_reserved_states_unreachable(self):
        """Phase 12 states are only reachable from IN_REVIEW (via QUOTED).
        
        Early Phase 05 states (DRAFT, SUBMITTED, RECEIVED) cannot reach
        Phase 12 states directly.
        """
        phase12_states = {
            EnquiryStatus.QUOTED,
            EnquiryStatus.CUSTOMER_ACCEPTED,
            EnquiryStatus.BOOKING_PROPOSED,
            EnquiryStatus.BOOKED,
            EnquiryStatus.IN_PROGRESS,
            EnquiryStatus.COMPLETED,
        }
        early_states = {
            EnquiryStatus.DRAFT,
            EnquiryStatus.SUBMITTED,
            EnquiryStatus.RECEIVED,
        }
        for status in early_states:
            for target in ENQUIRY_TRANSITIONS.get(status, set()):
                assert target not in phase12_states, (
                    f"{status} -> {target} should not be valid"
                )

    def test_all_statuses_have_transition_entries(self):
        """Every EnquiryStatus has an entry in the transitions map."""
        for status in EnquiryStatus:
            assert status in ENQUIRY_TRANSITIONS


class TestBookingStateMachine:
    """Test booking lifecycle state transitions."""

    def test_requested_can_propose(self):
        """REQUESTED -> PROPOSED is valid."""
        assert BookingStatus.PROPOSED in BOOKING_TRANSITIONS[BookingStatus.REQUESTED]

    def test_confirmed_can_go_in_progress(self):
        """CONFIRMED -> IN_PROGRESS is valid."""
        assert BookingStatus.IN_PROGRESS in BOOKING_TRANSITIONS[BookingStatus.CONFIRMED]

    def test_completed_is_terminal(self):
        """COMPLETED has no valid transitions."""
        assert len(BOOKING_TRANSITIONS[BookingStatus.COMPLETED]) == 0

    def test_no_show_is_terminal(self):
        """NO_SHOW has no valid transitions."""
        assert len(BOOKING_TRANSITIONS[BookingStatus.NO_SHOW]) == 0

    def test_all_statuses_have_transition_entries(self):
        """Every BookingStatus has an entry in the transitions map."""
        for status in BookingStatus:
            assert status in BOOKING_TRANSITIONS


class TestBrainVersionStateMachine:
    """Test Business Brain version lifecycle."""

    def test_draft_can_validate(self):
        """DRAFT -> VALIDATING is valid."""
        assert BrainVersionStatus.VALIDATING in BRAIN_VERSION_TRANSITIONS[BrainVersionStatus.DRAFT]

    def test_active_can_be_superseded(self):
        """ACTIVE -> SUPERSEDED is valid."""
        assert BrainVersionStatus.SUPERSEDED in BRAIN_VERSION_TRANSITIONS[BrainVersionStatus.ACTIVE]

    def test_superseded_is_terminal(self):
        """SUPERSEDED has no valid transitions."""
        assert len(BRAIN_VERSION_TRANSITIONS[BrainVersionStatus.SUPERSEDED]) == 0

    def test_all_statuses_have_transition_entries(self):
        """Every BrainVersionStatus has an entry in the transitions map."""
        for status in BrainVersionStatus:
            assert status in BRAIN_VERSION_TRANSITIONS
