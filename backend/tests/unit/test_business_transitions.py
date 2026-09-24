"""Unit tests for business and public-profile lifecycle state machines."""

from __future__ import annotations

from app.domain.common.enums import (
    BUSINESS_PROFILE_TRANSITIONS,
    BUSINESS_TRANSITIONS,
    BusinessProfileStatus,
    BusinessStatus,
)


class TestBusinessTransitions:
    """Business account lifecycle transitions."""

    def test_pending_can_activate(self):
        assert BusinessStatus.ACTIVE in BUSINESS_TRANSITIONS[BusinessStatus.PENDING]

    def test_pending_cannot_skip_to_suspended(self):
        assert BusinessStatus.SUSPENDED not in BUSINESS_TRANSITIONS[BusinessStatus.PENDING]

    def test_active_can_suspend_and_deactivate(self):
        allowed = BUSINESS_TRANSITIONS[BusinessStatus.ACTIVE]
        assert BusinessStatus.SUSPENDED in allowed
        assert BusinessStatus.DEACTIVATED in allowed

    def test_suspended_can_reinstate(self):
        assert BusinessStatus.ACTIVE in BUSINESS_TRANSITIONS[BusinessStatus.SUSPENDED]

    def test_deactivated_is_terminal(self):
        assert BUSINESS_TRANSITIONS[BusinessStatus.DEACTIVATED] == set()

    def test_no_transition_to_pending(self):
        for status, targets in BUSINESS_TRANSITIONS.items():
            assert BusinessStatus.PENDING not in targets, f"{status} must not transition back to PENDING"


class TestBusinessProfileTransitions:
    """Public profile visibility transitions."""

    def test_incomplete_can_publish(self):
        assert BusinessProfileStatus.ACTIVE in BUSINESS_PROFILE_TRANSITIONS[BusinessProfileStatus.INCOMPLETE]

    def test_active_cannot_go_back_to_incomplete(self):
        assert BusinessProfileStatus.INCOMPLETE not in BUSINESS_PROFILE_TRANSITIONS[BusinessProfileStatus.ACTIVE]

    def test_active_can_suspend(self):
        assert BusinessProfileStatus.SUSPENDED in BUSINESS_PROFILE_TRANSITIONS[BusinessProfileStatus.ACTIVE]

    def test_suspended_can_republish(self):
        assert BusinessProfileStatus.ACTIVE in BUSINESS_PROFILE_TRANSITIONS[BusinessProfileStatus.SUSPENDED]

    def test_every_status_has_an_entry(self):
        for status in BusinessProfileStatus:
            assert status in BUSINESS_PROFILE_TRANSITIONS
