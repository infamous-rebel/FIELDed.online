"""Shared domain enumerations.

These enums define the canonical state machines and categorical values
used across the FIELDed platform.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """System-level user roles."""

    CUSTOMER = "customer"
    BUSINESS_OWNER = "business_owner"
    BUSINESS_ADMIN = "business_admin"
    BUSINESS_STAFF = "business_staff"
    PLATFORM_ADMIN = "platform_admin"


class BusinessMemberRole(StrEnum):
    """Roles within a business."""

    OWNER = "owner"
    ADMIN = "admin"
    STAFF = "staff"


class EnquiryStatus(StrEnum):
    """Enquiry lifecycle state machine.

    Phase 05 active states:
        DRAFT -> SUBMITTED -> RECEIVED -> IN_REVIEW -> NEEDS_INFORMATION

    Phase 05 terminal/exception states:
        DECLINED, CANCELLED, EXPIRED, REJECTED

    Reserved for later phases (not reachable in Phase 05):
        QUOTED, CUSTOMER_ACCEPTED, BOOKING_PROPOSED, BOOKED,
        IN_PROGRESS, COMPLETED
    """

    # Phase 05 active states
    DRAFT = "draft"
    SUBMITTED = "submitted"
    RECEIVED = "received"
    IN_REVIEW = "in_review"
    NEEDS_INFORMATION = "needs_information"

    # Reserved for later phases (quote/booking/completion)
    QUOTED = "quoted"
    CUSTOMER_ACCEPTED = "customer_accepted"
    BOOKING_PROPOSED = "booking_proposed"
    BOOKED = "booked"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

    # Terminal/exception states
    DECLINED = "declined"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REJECTED = "rejected"


# Phase 05 enquiry state transitions.
# Reserved states (QUOTED+) have empty transition sets — they exist
# in the enum for schema forward-compatibility but are unreachable.
ENQUIRY_TRANSITIONS: dict[EnquiryStatus, set[EnquiryStatus]] = {
    EnquiryStatus.DRAFT: {EnquiryStatus.SUBMITTED, EnquiryStatus.CANCELLED},
    EnquiryStatus.SUBMITTED: {
        EnquiryStatus.RECEIVED,
        EnquiryStatus.EXPIRED,
        EnquiryStatus.CANCELLED,
    },
    EnquiryStatus.RECEIVED: {
        EnquiryStatus.IN_REVIEW,
        EnquiryStatus.DECLINED,
        EnquiryStatus.EXPIRED,
    },
    EnquiryStatus.IN_REVIEW: {
        EnquiryStatus.NEEDS_INFORMATION,
        EnquiryStatus.QUOTED,
        EnquiryStatus.DECLINED,
        EnquiryStatus.EXPIRED,
    },
    EnquiryStatus.NEEDS_INFORMATION: {
        EnquiryStatus.IN_REVIEW,
        EnquiryStatus.DECLINED,
        EnquiryStatus.EXPIRED,
    },
    # Terminal states — no transitions allowed
    EnquiryStatus.DECLINED: set(),
    EnquiryStatus.CANCELLED: set(),
    EnquiryStatus.EXPIRED: set(),
    EnquiryStatus.REJECTED: set(),
    # Phase 12 states (reachable via quote/booking flow)
    EnquiryStatus.QUOTED: {
        EnquiryStatus.CUSTOMER_ACCEPTED,
        EnquiryStatus.EXPIRED,
        EnquiryStatus.CANCELLED,
    },
    EnquiryStatus.CUSTOMER_ACCEPTED: {EnquiryStatus.BOOKING_PROPOSED, EnquiryStatus.CANCELLED},
    EnquiryStatus.BOOKING_PROPOSED: {EnquiryStatus.BOOKED, EnquiryStatus.CANCELLED},
    EnquiryStatus.BOOKED: {EnquiryStatus.IN_PROGRESS, EnquiryStatus.CANCELLED},
    EnquiryStatus.IN_PROGRESS: {EnquiryStatus.COMPLETED, EnquiryStatus.CANCELLED},
    EnquiryStatus.COMPLETED: set(),
}


class QuoteStatus(StrEnum):
    """Quote lifecycle state machine.

    DRAFT -> ISSUED -> ACCEPTED / DECLINED / EXPIRED
    """

    DRAFT = "draft"
    ISSUED = "issued"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"


QUOTE_TRANSITIONS: dict[QuoteStatus, set[QuoteStatus]] = {
    QuoteStatus.DRAFT: {QuoteStatus.ISSUED},
    QuoteStatus.ISSUED: {QuoteStatus.ACCEPTED, QuoteStatus.DECLINED, QuoteStatus.EXPIRED},
    # Terminal states
    QuoteStatus.ACCEPTED: set(),
    QuoteStatus.DECLINED: set(),
    QuoteStatus.EXPIRED: set(),
}


class BookingStatus(StrEnum):
    """Booking lifecycle state machine.

    Normal flow:
        REQUESTED -> PROPOSED -> ACCEPTED -> CONFIRMED -> IN_PROGRESS -> COMPLETED

    Terminal/exception states:
        DECLINED, CANCELLED, EXPIRED, RESCHEDULED, NO_SHOW
    """

    REQUESTED = "requested"
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    RESCHEDULED = "rescheduled"
    NO_SHOW = "no_show"


# Valid booking state transitions
BOOKING_TRANSITIONS: dict[BookingStatus, set[BookingStatus]] = {
    BookingStatus.REQUESTED: {
        BookingStatus.PROPOSED,
        BookingStatus.DECLINED,
        BookingStatus.CANCELLED,
        BookingStatus.EXPIRED,
    },
    BookingStatus.PROPOSED: {
        BookingStatus.ACCEPTED,
        BookingStatus.DECLINED,
        BookingStatus.CANCELLED,
        BookingStatus.EXPIRED,
    },
    BookingStatus.ACCEPTED: {
        BookingStatus.CONFIRMED,
        BookingStatus.CANCELLED,
        BookingStatus.EXPIRED,
    },
    BookingStatus.CONFIRMED: {
        BookingStatus.IN_PROGRESS,
        BookingStatus.COMPLETED,
        BookingStatus.CANCELLED,
        BookingStatus.NO_SHOW,
    },
    # COMPLETED is allowed from CONFIRMED: the service-execution completion
    # cascade completes a confirmed booking whose service was delivered
    # without a separate business "Start" action.
    # NOTE: RESCHEDULED is NOT a direct transition.  Rescheduling is
    # implemented as: cancel old booking (→ CANCELLED) + create new booking.
    # This preserves a clean audit trail per booking instance.
    BookingStatus.IN_PROGRESS: {
        BookingStatus.COMPLETED,
        BookingStatus.CANCELLED,
    },
    # Terminal states
    BookingStatus.COMPLETED: set(),
    BookingStatus.DECLINED: set(),
    BookingStatus.CANCELLED: set(),
    BookingStatus.EXPIRED: set(),
    BookingStatus.RESCHEDULED: set(),
    BookingStatus.NO_SHOW: set(),
}


class BrainVersionStatus(StrEnum):
    """Business Brain version lifecycle.

    DRAFT -> VALIDATING -> REVIEW -> APPROVED -> ACTIVE -> SUPERSEDED
    """

    DRAFT = "draft"
    VALIDATING = "validating"
    REVIEW = "review"
    APPROVED = "approved"
    ACTIVE = "active"
    SUPERSEDED = "superseded"


BRAIN_VERSION_TRANSITIONS: dict[BrainVersionStatus, set[BrainVersionStatus]] = {
    # DRAFT can go to VALIDATING (standard path) or directly to REVIEW
    # (manual rules that don't need system validation).
    BrainVersionStatus.DRAFT: {BrainVersionStatus.VALIDATING, BrainVersionStatus.REVIEW},
    BrainVersionStatus.VALIDATING: {BrainVersionStatus.REVIEW, BrainVersionStatus.DRAFT},
    BrainVersionStatus.REVIEW: {BrainVersionStatus.APPROVED, BrainVersionStatus.DRAFT},
    BrainVersionStatus.APPROVED: {BrainVersionStatus.ACTIVE},
    BrainVersionStatus.ACTIVE: {BrainVersionStatus.SUPERSEDED},
    BrainVersionStatus.SUPERSEDED: set(),
}


class ServiceOfferStatus(StrEnum):
    """Service Offer lifecycle status.

    DRAFT -> ACTIVE -> PAUSED -> ARCHIVED
    """

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


SERVICE_OFFER_TRANSITIONS: dict[ServiceOfferStatus, set[ServiceOfferStatus]] = {
    ServiceOfferStatus.DRAFT: {ServiceOfferStatus.ACTIVE, ServiceOfferStatus.ARCHIVED},
    ServiceOfferStatus.ACTIVE: {ServiceOfferStatus.PAUSED, ServiceOfferStatus.ARCHIVED},
    ServiceOfferStatus.PAUSED: {ServiceOfferStatus.ACTIVE, ServiceOfferStatus.ARCHIVED},
    # Terminal state
    ServiceOfferStatus.ARCHIVED: set(),
}


class DeliveryMode(StrEnum):
    """How a service is delivered."""

    ON_SITE = "on_site"
    REMOTE = "remote"
    IN_STORE = "in_store"
    HYBRID = "hybrid"


class PricingModel(StrEnum):
    """How pricing is determined for a service offer."""

    FIXED = "fixed"
    HOURLY = "hourly"
    QUOTE_REQUIRED = "quote_required"
    STARTING_AT = "starting_at"
    CUSTOM = "custom"


class CustomerProfileStatus(StrEnum):
    """Customer profile lifecycle status."""

    INCOMPLETE = "incomplete"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class BusinessStatus(StrEnum):
    """Business account lifecycle status."""

    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"


class BusinessProfileStatus(StrEnum):
    """Public business profile visibility status.

    Controls whether the public profile is discoverable.
    """

    INCOMPLETE = "incomplete"
    ACTIVE = "active"
    SUSPENDED = "suspended"


# Business account lifecycle transitions.
# PENDING businesses must be explicitly activated (by an owner/admin) before
# they can receive enquiries or appear in discovery.
BUSINESS_TRANSITIONS: dict[BusinessStatus, set[BusinessStatus]] = {
    BusinessStatus.PENDING: {BusinessStatus.ACTIVE, BusinessStatus.DEACTIVATED},
    BusinessStatus.ACTIVE: {BusinessStatus.SUSPENDED, BusinessStatus.DEACTIVATED},
    BusinessStatus.SUSPENDED: {BusinessStatus.ACTIVE, BusinessStatus.DEACTIVATED},
    # Terminal state
    BusinessStatus.DEACTIVATED: set(),
}


# Public profile visibility transitions.
BUSINESS_PROFILE_TRANSITIONS: dict[BusinessProfileStatus, set[BusinessProfileStatus]] = {
    BusinessProfileStatus.INCOMPLETE: {BusinessProfileStatus.ACTIVE},
    BusinessProfileStatus.ACTIVE: {BusinessProfileStatus.SUSPENDED},
    BusinessProfileStatus.SUSPENDED: {BusinessProfileStatus.ACTIVE},
}


# ──────────────────────────────────────────────────────────────────────────────
# Phase 13 — Service Execution, Invoice, Ledger
# ──────────────────────────────────────────────────────────────────────────────


class ServiceExecutionStatus(StrEnum):
    """Service execution lifecycle state machine.

    Normal flow:
        SCHEDULED -> IN_PROGRESS -> COMPLETED

    Exception states:
        CANCELLED, NO_SHOW
    """

    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


SERVICE_EXECUTION_TRANSITIONS: dict[ServiceExecutionStatus, set[ServiceExecutionStatus]] = {
    ServiceExecutionStatus.SCHEDULED: {
        ServiceExecutionStatus.IN_PROGRESS,
        ServiceExecutionStatus.CANCELLED,
        ServiceExecutionStatus.NO_SHOW,
    },
    ServiceExecutionStatus.IN_PROGRESS: {
        ServiceExecutionStatus.COMPLETED,
        ServiceExecutionStatus.CANCELLED,
    },
    # Terminal states
    ServiceExecutionStatus.COMPLETED: set(),
    ServiceExecutionStatus.CANCELLED: set(),
    ServiceExecutionStatus.NO_SHOW: set(),
}


class InvoicePaymentStatus(StrEnum):
    """Invoice payment status.

    Represents the business's recorded transaction state.
    Updated deterministically from Payment domain events.
    """

    UNPAID = "unpaid"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    VOID = "void"


class InvoiceStatus(StrEnum):
    """Invoice document lifecycle."""

    DRAFT = "draft"
    ISSUED = "issued"
    VOID = "void"


INVOICE_TRANSITIONS: dict[InvoiceStatus, set[InvoiceStatus]] = {
    InvoiceStatus.DRAFT: {InvoiceStatus.ISSUED, InvoiceStatus.VOID},
    InvoiceStatus.ISSUED: {InvoiceStatus.VOID},
    InvoiceStatus.VOID: set(),
}


# ──────────────────────────────────────────────────────────────────────────────
# Phase 14A — Communication, Notification, Outbox
# ──────────────────────────────────────────────────────────────────────────────


class CommunicationChannel(StrEnum):
    """Supported communication channels."""

    EMAIL = "EMAIL"
    SMS = "SMS"
    WHATSAPP = "WHATSAPP"
    PUSH = "PUSH"
    IN_APP = "IN_APP"
    VOICE = "VOICE"


class CommunicationPurpose(StrEnum):
    """Supported communication purposes."""

    TRANSACTIONAL = "TRANSACTIONAL"
    SERVICE_NOTIFICATION = "SERVICE_NOTIFICATION"
    REMINDER = "REMINDER"
    FOLLOW_UP = "FOLLOW_UP"
    AUTHENTICATION = "AUTHENTICATION"
    PAYMENT = "PAYMENT"
    INVOICE = "INVOICE"
    MARKETING = "MARKETING"
    CAMPAIGN = "CAMPAIGN"


class CommunicationStatus(StrEnum):
    """Communication delivery lifecycle."""

    PENDING = "PENDING"
    QUEUED = "QUEUED"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    BOUNCED = "BOUNCED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class RecipientType(StrEnum):
    """Communication recipient classification."""

    CUSTOMER = "CUSTOMER"
    STAFF = "STAFF"
    EXTERNAL = "EXTERNAL"
    OTHER = "OTHER"


class RecipientStatus(StrEnum):
    """Recipient delivery status."""

    PENDING = "PENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


class AttemptStatus(StrEnum):
    """Provider attempt status."""

    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRYABLE = "RETRYABLE"


class TemplateStatus(StrEnum):
    """Communication template lifecycle."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class TemplateApprovalState(StrEnum):
    """Template approval workflow."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class OutboxStatus(StrEnum):
    """Outbox event processing lifecycle."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    RETRYABLE = "RETRYABLE"
    FAILED = "FAILED"


class WebhookProcessingStatus(StrEnum):
    """Webhook processing status."""

    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class NotificationPriority(StrEnum):
    """Notification priority levels."""

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class PolicyDecisionType(StrEnum):
    """Communication policy decision outcomes."""

    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DEFER = "DEFER"
    ESCALATE = "ESCALATE"


class AuditEventType(StrEnum):
    """Communication audit event types."""

    COMMUNICATION_REQUESTED = "COMMUNICATION_REQUESTED"
    COMMUNICATION_ALLOWED = "COMMUNICATION_ALLOWED"
    COMMUNICATION_DENIED = "COMMUNICATION_DENIED"
    COMMUNICATION_DEFERRED = "COMMUNICATION_DEFERRED"
    COMMUNICATION_SENT = "COMMUNICATION_SENT"
    COMMUNICATION_DELIVERED = "COMMUNICATION_DELIVERED"
    COMMUNICATION_FAILED = "COMMUNICATION_FAILED"
    NOTIFICATION_CREATED = "NOTIFICATION_CREATED"
    NOTIFICATION_READ = "NOTIFICATION_READ"
    CONSENT_GRANTED = "CONSENT_GRANTED"
    CONSENT_REVOKED = "CONSENT_REVOKED"
    SUPPRESSION_ADDED = "SUPPRESSION_ADDED"
    SUPPRESSION_REMOVED = "SUPPRESSION_REMOVED"
    # Phase 14B — Voice / Call Agent lifecycle
    CALL_REQUESTED = "CALL_REQUESTED"
    CALL_AUTHORIZED = "CALL_AUTHORIZED"
    CALL_QUEUED = "CALL_QUEUED"
    CALL_INITIATED = "CALL_INITIATED"
    CALL_RINGING = "CALL_RINGING"
    CALL_CONNECTED = "CALL_CONNECTED"
    CALL_SESSION_STARTED = "CALL_SESSION_STARTED"
    CALL_IN_PROGRESS = "CALL_IN_PROGRESS"
    CALL_COMPLETED = "CALL_COMPLETED"
    CALL_FAILED = "CALL_FAILED"
    CALL_NO_ANSWER = "CALL_NO_ANSWER"
    CALL_BUSY = "CALL_BUSY"
    CALL_DECLINED = "CALL_DECLINED"
    CALL_CANCELLED = "CALL_CANCELLED"
    CALL_EXPIRED = "CALL_EXPIRED"
    CALL_ESCALATED = "CALL_ESCALATED"
    CALL_ESCALATION_ASSIGNED = "CALL_ESCALATION_ASSIGNED"
    CALL_ESCALATION_ACCEPTED = "CALL_ESCALATION_ACCEPTED"
    CALL_ESCALATION_RESOLVED = "CALL_ESCALATION_RESOLVED"
    CALL_ESCALATION_CANCELLED = "CALL_ESCALATION_CANCELLED"
    CALL_PROVIDER_STATE_SYNC = "CALL_PROVIDER_STATE_SYNC"
    CALL_AGENT_TURN = "CALL_AGENT_TURN"
    CALL_AGENT_ACTION_EXECUTED = "CALL_AGENT_ACTION_EXECUTED"
    CALL_AGENT_HANDOFF_REQUESTED = "CALL_AGENT_HANDOFF_REQUESTED"
    CAMPAIGN_PROCESSING_STARTED = "CAMPAIGN_PROCESSING_STARTED"
    CAMPAIGN_RECIPIENT_SUPPRESSED = "CAMPAIGN_RECIPIENT_SUPPRESSED"
    CAMPAIGN_RECIPIENT_SKIPPED = "CAMPAIGN_RECIPIENT_SKIPPED"
    # Phase 15 — Payments & Financial Operations
    PAYMENT_INITIATED = "PAYMENT_INITIATED"
    PAYMENT_PROCESSING = "PAYMENT_PROCESSING"
    PAYMENT_SUCCEEDED = "PAYMENT_SUCCEEDED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    PAYMENT_EXPIRED = "PAYMENT_EXPIRED"
    PAYMENT_CANCELLED = "PAYMENT_CANCELLED"
    PAYMENT_REFUND_REQUESTED = "PAYMENT_REFUND_REQUESTED"
    PAYMENT_REFUNDED = "PAYMENT_REFUNDED"
    PAYMENT_PARTIALLY_REFUNDED = "PAYMENT_PARTIALLY_REFUNDED"
    PAYMENT_WEBHOOK_RECEIVED = "PAYMENT_WEBHOOK_RECEIVED"
    PAYMENT_WEBHOOK_PROCESSED = "PAYMENT_WEBHOOK_PROCESSED"
    INVOICE_BALANCE_UPDATED = "INVOICE_BALANCE_UPDATED"
    # Phase 17 — Reviews & Trust
    REVIEW_SUBMITTED = "REVIEW_SUBMITTED"
    REVIEW_RESPONDED = "REVIEW_RESPONDED"
    # Phase 17 — Members
    MEMBER_INVITED = "MEMBER_INVITED"
    MEMBER_ACCEPTED = "MEMBER_ACCEPTED"
    MEMBER_ROLE_CHANGED = "MEMBER_ROLE_CHANGED"
    MEMBER_REMOVED = "MEMBER_REMOVED"
    # Phase 17 — Settings
    BUSINESS_SETTINGS_UPDATED = "BUSINESS_SETTINGS_UPDATED"
    COMMUNICATION_CONFIG_UPDATED = "COMMUNICATION_CONFIG_UPDATED"
    # Phase 18 — Business lifecycle
    BUSINESS_STATUS_CHANGED = "BUSINESS_STATUS_CHANGED"
    BUSINESS_PROFILE_STATUS_CHANGED = "BUSINESS_PROFILE_STATUS_CHANGED"


# ──────────────────────────────────────────────────────────────────────────────
# Phase 14B — Voice / Call Agent
# ──────────────────────────────────────────────────────────────────────────────


class CallType(StrEnum):
    """Calling classification.

    The distinction is explicit and authoritative: a marketing call never
    enters the transactional path merely because the recipient happens to
    be an existing customer.  The purpose determines the type (see
    CALL_PURPOSE_TYPE) — the two must never contradict each other.
    """

    TRANSACTIONAL = "TRANSACTIONAL"
    MARKETING = "MARKETING"


class CallPurpose(StrEnum):
    """Call purpose classification.

    Transactional purposes relate to an active or recent service
    relationship (enquiry, quote, booking, execution, invoice).
    Marketing purposes are promotional in nature regardless of the
    recipient's customer status.
    """

    # Transactional purposes
    SERVICE_CONFIRMATION = "SERVICE_CONFIRMATION"
    BOOKING_CONFIRMATION = "BOOKING_CONFIRMATION"
    BOOKING_REMINDER = "BOOKING_REMINDER"
    QUOTE_FOLLOW_UP = "QUOTE_FOLLOW_UP"
    RESCHEDULE = "RESCHEDULE"
    CANCELLATION = "CANCELLATION"
    INVOICE_REMINDER = "INVOICE_REMINDER"
    PAYMENT_REMINDER = "PAYMENT_REMINDER"
    SERVICE_COMPLETION_FOLLOW_UP = "SERVICE_COMPLETION_FOLLOW_UP"
    INFORMATION_COLLECTION = "INFORMATION_COLLECTION"
    MISSED_CALL_FOLLOW_UP = "MISSED_CALL_FOLLOW_UP"
    HUMAN_ESCALATION = "HUMAN_ESCALATION"
    # Marketing purposes
    SERVICE_PROMOTION = "SERVICE_PROMOTION"
    EXISTING_CUSTOMER_CAMPAIGN = "EXISTING_CUSTOMER_CAMPAIGN"
    LEAD_FOLLOW_UP = "LEAD_FOLLOW_UP"
    REACTIVATION = "REACTIVATION"
    RENEWAL_REMINDER = "RENEWAL_REMINDER"
    MARKETING_CAMPAIGN = "MARKETING_CAMPAIGN"


# Authoritative purpose → type mapping.
# A call's declared type must match the type derived from its purpose.
CALL_PURPOSE_TYPE: dict[CallPurpose, CallType] = {
    # Transactional
    CallPurpose.SERVICE_CONFIRMATION: CallType.TRANSACTIONAL,
    CallPurpose.BOOKING_CONFIRMATION: CallType.TRANSACTIONAL,
    CallPurpose.BOOKING_REMINDER: CallType.TRANSACTIONAL,
    CallPurpose.QUOTE_FOLLOW_UP: CallType.TRANSACTIONAL,
    CallPurpose.RESCHEDULE: CallType.TRANSACTIONAL,
    CallPurpose.CANCELLATION: CallType.TRANSACTIONAL,
    CallPurpose.INVOICE_REMINDER: CallType.TRANSACTIONAL,
    CallPurpose.PAYMENT_REMINDER: CallType.TRANSACTIONAL,
    CallPurpose.SERVICE_COMPLETION_FOLLOW_UP: CallType.TRANSACTIONAL,
    CallPurpose.INFORMATION_COLLECTION: CallType.TRANSACTIONAL,
    CallPurpose.MISSED_CALL_FOLLOW_UP: CallType.TRANSACTIONAL,
    CallPurpose.HUMAN_ESCALATION: CallType.TRANSACTIONAL,
    # Marketing
    CallPurpose.SERVICE_PROMOTION: CallType.MARKETING,
    CallPurpose.EXISTING_CUSTOMER_CAMPAIGN: CallType.MARKETING,
    CallPurpose.LEAD_FOLLOW_UP: CallType.MARKETING,
    CallPurpose.REACTIVATION: CallType.MARKETING,
    CallPurpose.RENEWAL_REMINDER: CallType.MARKETING,
    CallPurpose.MARKETING_CAMPAIGN: CallType.MARKETING,
}


class CallStatus(StrEnum):
    """Call lifecycle state machine.

    Normal flow:
        REQUESTED -> AUTHORIZED -> QUEUED -> INITIATING -> RINGING
            -> CONNECTED -> IN_PROGRESS -> COMPLETED

    Exception/terminal states:
        FAILED, NO_ANSWER, BUSY, DECLINED, CANCELLED, EXPIRED, ESCALATED

    The AI agent never mutates call state directly — all transitions
    flow through the deterministic lifecycle service.
    """

    # Active states
    REQUESTED = "REQUESTED"
    AUTHORIZED = "AUTHORIZED"
    QUEUED = "QUEUED"
    INITIATING = "INITIATING"
    RINGING = "RINGING"
    CONNECTED = "CONNECTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    # Exception/terminal states
    FAILED = "FAILED"
    NO_ANSWER = "NO_ANSWER"
    BUSY = "BUSY"
    DECLINED = "DECLINED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    ESCALATED = "ESCALATED"


# Valid call state transitions.
# Terminal states have empty transition sets.
CALL_TRANSITIONS: dict[CallStatus, set[CallStatus]] = {
    CallStatus.REQUESTED: {
        CallStatus.AUTHORIZED,
        CallStatus.CANCELLED,
        CallStatus.FAILED,
        CallStatus.EXPIRED,
    },
    CallStatus.AUTHORIZED: {
        CallStatus.QUEUED,
        CallStatus.CANCELLED,
        CallStatus.FAILED,
        CallStatus.EXPIRED,
    },
    CallStatus.QUEUED: {
        CallStatus.INITIATING,
        CallStatus.CANCELLED,
        CallStatus.FAILED,
        CallStatus.EXPIRED,
    },
    CallStatus.INITIATING: {
        CallStatus.RINGING,
        CallStatus.CANCELLED,
        CallStatus.FAILED,
        CallStatus.EXPIRED,
    },
    CallStatus.RINGING: {
        CallStatus.CONNECTED,
        CallStatus.NO_ANSWER,
        CallStatus.BUSY,
        CallStatus.DECLINED,
        CallStatus.FAILED,
        CallStatus.CANCELLED,
        CallStatus.EXPIRED,
    },
    CallStatus.CONNECTED: {
        CallStatus.IN_PROGRESS,
        CallStatus.COMPLETED,
        CallStatus.FAILED,
        CallStatus.ESCALATED,
    },
    CallStatus.IN_PROGRESS: {
        CallStatus.COMPLETED,
        CallStatus.FAILED,
        CallStatus.ESCALATED,
    },
    # Terminal states — no transitions allowed
    CallStatus.COMPLETED: set(),
    CallStatus.FAILED: set(),
    CallStatus.NO_ANSWER: set(),
    CallStatus.BUSY: set(),
    CallStatus.DECLINED: set(),
    CallStatus.CANCELLED: set(),
    CallStatus.EXPIRED: set(),
    CallStatus.ESCALATED: set(),
}


class CallParticipantType(StrEnum):
    """Call participant classification.

    A phone number alone is sufficient for legitimate external
    participants — not every participant has a FIELDed user account.
    """

    CUSTOMER = "CUSTOMER"
    BUSINESS_MEMBER = "BUSINESS_MEMBER"
    AGENT = "AGENT"
    HUMAN_AGENT = "HUMAN_AGENT"
    EXTERNAL = "EXTERNAL"


class CallAttemptStatus(StrEnum):
    """Provider call attempt lifecycle.

    A single logical call may have multiple provider attempts.
    Attempts are append-oriented — historical attempts are never
    overwritten to make a later attempt appear as the original.
    """

    REQUESTED = "REQUESTED"
    RINGING = "RINGING"
    CONNECTED = "CONNECTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    NO_ANSWER = "NO_ANSWER"
    BUSY = "BUSY"
    DECLINED = "DECLINED"
    CANCELLED = "CANCELLED"


class CallSessionStatus(StrEnum):
    """Conversational call session lifecycle.

    A session exists only while a call is connected.
    ESCALATED marks a session handed off to a human.
    """

    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"


CALL_SESSION_TRANSITIONS: dict[CallSessionStatus, set[CallSessionStatus]] = {
    CallSessionStatus.ACTIVE: {
        CallSessionStatus.COMPLETED,
        CallSessionStatus.FAILED,
        CallSessionStatus.ESCALATED,
    },
    # Terminal states — no transitions allowed
    CallSessionStatus.COMPLETED: set(),
    CallSessionStatus.FAILED: set(),
    CallSessionStatus.ESCALATED: set(),
}


class EscalationStatus(StrEnum):
    """Human escalation lifecycle.

    Supports: Call Agent → human escalation requested → business
    member assigned → human accepts → agent hands off.
    """

    NONE = "NONE"
    REQUESTED = "REQUESTED"
    ASSIGNED = "ASSIGNED"
    ACCEPTED = "ACCEPTED"
    RESOLVED = "RESOLVED"
    CANCELLED = "CANCELLED"


ESCALATION_TRANSITIONS: dict[EscalationStatus, set[EscalationStatus]] = {
    EscalationStatus.NONE: {EscalationStatus.REQUESTED},
    EscalationStatus.REQUESTED: {
        EscalationStatus.ASSIGNED,
        EscalationStatus.CANCELLED,
    },
    EscalationStatus.ASSIGNED: {
        EscalationStatus.ACCEPTED,
        EscalationStatus.CANCELLED,
    },
    EscalationStatus.ACCEPTED: {EscalationStatus.RESOLVED},
    # Terminal states — no transitions allowed
    EscalationStatus.RESOLVED: set(),
    EscalationStatus.CANCELLED: set(),
}


class CampaignStatus(StrEnum):
    """Communication campaign lifecycle.

    Phase 14B.1 provides the persistent foundation only — audience
    execution, scheduling, and analytics belong to later 14B blocks.
    """

    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


CAMPAIGN_TRANSITIONS: dict[CampaignStatus, set[CampaignStatus]] = {
    CampaignStatus.DRAFT: {
        CampaignStatus.SCHEDULED,
        CampaignStatus.ACTIVE,
        CampaignStatus.CANCELLED,
    },
    CampaignStatus.SCHEDULED: {
        CampaignStatus.ACTIVE,
        CampaignStatus.CANCELLED,
    },
    CampaignStatus.ACTIVE: {
        CampaignStatus.PAUSED,
        CampaignStatus.COMPLETED,
        CampaignStatus.CANCELLED,
    },
    CampaignStatus.PAUSED: {
        CampaignStatus.ACTIVE,
        CampaignStatus.CANCELLED,
    },
    # Terminal states — no transitions allowed
    CampaignStatus.COMPLETED: set(),
    CampaignStatus.CANCELLED: set(),
}


class CampaignRecipientStatus(StrEnum):
    """Campaign recipient lifecycle.

    Recipients never bypass the consent / suppression / DNC /
    frequency / timing / Business Brain / authorization policy chain.
    """

    PENDING = "PENDING"
    ELIGIBLE = "ELIGIBLE"
    CONTACTED = "CONTACTED"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    SUPPRESSED = "SUPPRESSED"
    FAILED = "FAILED"


CAMPAIGN_RECIPIENT_TRANSITIONS: dict[CampaignRecipientStatus, set[CampaignRecipientStatus]] = {
    CampaignRecipientStatus.PENDING: {
        CampaignRecipientStatus.ELIGIBLE,
        CampaignRecipientStatus.SKIPPED,
        CampaignRecipientStatus.SUPPRESSED,
        CampaignRecipientStatus.FAILED,
    },
    CampaignRecipientStatus.ELIGIBLE: {
        CampaignRecipientStatus.CONTACTED,
        CampaignRecipientStatus.SKIPPED,
        CampaignRecipientStatus.SUPPRESSED,
        CampaignRecipientStatus.FAILED,
    },
    CampaignRecipientStatus.CONTACTED: {
        CampaignRecipientStatus.COMPLETED,
        CampaignRecipientStatus.FAILED,
    },
    # Terminal states — no transitions allowed
    CampaignRecipientStatus.COMPLETED: set(),
    CampaignRecipientStatus.SKIPPED: set(),
    CampaignRecipientStatus.SUPPRESSED: set(),
    CampaignRecipientStatus.FAILED: set(),
}


class CallOutcome(StrEnum):
    """Recorded conversational/call outcome.

    Recorded on the call session by the Call Agent or a human.
    Marketing calls may never record transactional outcomes
    (CONFIRMED, RESCHEDULE_REQUESTED, CANCELLATION_REQUESTED,
    PAYMENT_ARRANGED) — enforced deterministically in the agent
    runtime.
    """

    CONFIRMED = "CONFIRMED"
    INFORMATION_COLLECTED = "INFORMATION_COLLECTED"
    RESCHEDULE_REQUESTED = "RESCHEDULE_REQUESTED"
    CANCELLATION_REQUESTED = "CANCELLATION_REQUESTED"
    PAYMENT_ARRANGED = "PAYMENT_ARRANGED"
    COMPLAINT_LOGGED = "COMPLAINT_LOGGED"
    NOT_INTERESTED = "NOT_INTERESTED"
    CALLBACK_REQUESTED = "CALLBACK_REQUESTED"
    NO_CONTACT = "NO_CONTACT"
    OTHER = "OTHER"


# Outcomes reserved for transactional calls — a marketing call may
# never report these (the recipient cannot "confirm" a booking they
# were called about promotionally).
TRANSACTIONAL_ONLY_OUTCOMES: frozenset[CallOutcome] = frozenset(
    {
        CallOutcome.CONFIRMED,
        CallOutcome.RESCHEDULE_REQUESTED,
        CallOutcome.CANCELLATION_REQUESTED,
        CallOutcome.PAYMENT_ARRANGED,
    }
)


class AgentAction(StrEnum):
    """Actions the Call Agent may propose for a conversation turn.

    The AI provider only PROPOSES actions; every action is validated
    against the governed configuration and executed through the
    deterministic lifecycle services.  The agent never mutates call
    state directly.
    """

    CONTINUE = "CONTINUE"
    COLLECT_INFORMATION = "COLLECT_INFORMATION"
    REQUEST_HUMAN = "REQUEST_HUMAN"
    END_CALL = "END_CALL"


# Default collectible information keys when the Brain does not
# declare its own.  Everything else is rejected (fail-closed).
DEFAULT_COLLECTIBLE_FIELDS: frozenset[str] = frozenset(
    {
        "callback_number",
        "preferred_time",
        "notes",
    }
)


# ──────────────────────────────────────────────────────────────────────────────
# Phase 15 — Payments & Financial Operations
# ──────────────────────────────────────────────────────────────────────────────


class PaymentStatus(StrEnum):
    """Payment lifecycle state machine.

    Normal flow:
        PENDING -> PROCESSING -> SUCCEEDED

    Exception/terminal states:
        FAILED, EXPIRED, CANCELLED

    Refund track (post-SUCCEEDED only):
        SUCCEEDED -> REFUNDED (full) or PARTIALLY_REFUNDED
        PARTIALLY_REFUNDED -> REFUNDED (if fully refunded)

    Dispute track (post-SUCCEEDED only):
        SUCCEEDED -> DISPUTED
        DISPUTED -> REFUNDED (dispute lost / refund issued)
        DISPUTED -> SUCCEEDED (dispute won — rare)

    The AI never determines payment amount, authorization,
    transaction state, or refund eligibility.
    """

    # Active states
    PENDING = "pending"
    PROCESSING = "processing"
    # Success
    SUCCEEDED = "succeeded"
    # Exception/terminal states
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    # Refund track
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    # Dispute track
    DISPUTED = "disputed"


PAYMENT_TRANSITIONS: dict[PaymentStatus, set[PaymentStatus]] = {
    PaymentStatus.PENDING: {
        PaymentStatus.PROCESSING,
        PaymentStatus.FAILED,
        PaymentStatus.EXPIRED,
        PaymentStatus.CANCELLED,
    },
    PaymentStatus.PROCESSING: {
        PaymentStatus.SUCCEEDED,
        PaymentStatus.FAILED,
        PaymentStatus.EXPIRED,
        PaymentStatus.CANCELLED,
    },
    # SUCCEEDED can transition to refund states or dispute
    PaymentStatus.SUCCEEDED: {
        PaymentStatus.REFUNDED,
        PaymentStatus.PARTIALLY_REFUNDED,
        PaymentStatus.DISPUTED,
    },
    # Partial refund can become full refund
    PaymentStatus.PARTIALLY_REFUNDED: {
        PaymentStatus.REFUNDED,
        PaymentStatus.DISPUTED,
    },
    # Dispute can resolve to refund (lost) or back to succeeded (won)
    PaymentStatus.DISPUTED: {
        PaymentStatus.REFUNDED,
        PaymentStatus.SUCCEEDED,
    },
    # Terminal states — no transitions allowed
    PaymentStatus.FAILED: set(),
    PaymentStatus.EXPIRED: set(),
    PaymentStatus.CANCELLED: set(),
    PaymentStatus.REFUNDED: set(),
}


class PaymentMethod(StrEnum):
    """Supported payment methods.

    The business Brain may govern which methods are accepted,
    but the platform supports these canonical types.
    """

    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    CASH = "cash"
    DIGITAL_WALLET = "digital_wallet"
    OTHER = "other"


class RefundStatus(StrEnum):
    """Refund lifecycle."""

    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PaymentWebhookStatus(StrEnum):
    """Payment webhook processing status."""

    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


# ──────────────────────────────────────────────────────────────────────────────
# Phase 18 — Business Brain Interactive Co-Brain
# ──────────────────────────────────────────────────────────────────────────────


class BrainConversationStatus(StrEnum):
    """Brain conversation lifecycle.

    A conversation is ACTIVE while the owner is engaged.
    It becomes ARCHIVED when explicitly closed or superseded.
    """

    ACTIVE = "active"
    ARCHIVED = "archived"


class BrainMessageRole(StrEnum):
    """Message author role in a Brain conversation."""

    BRAIN = "brain"
    OWNER = "owner"
    SYSTEM = "system"


class BrainProposalStatus(StrEnum):
    """Brain proposal governance lifecycle.

    PENDING  — AI proposed, awaiting owner decision
    APPROVED — Owner approved; eligible for application to Brain
    EDITED   — Owner approved with modifications
    REJECTED — Owner explicitly rejected
    APPLIED  — Approved change has been applied to governed Brain state
    """

    PENDING = "pending"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"
    APPLIED = "applied"


class BrainProposalType(StrEnum):
    """What kind of business knowledge a Brain proposal represents."""

    NEW_SERVICE = "new_service"
    PRICING_RULE = "pricing_rule"
    POLICY_RULE = "policy_rule"
    AVAILABILITY_RULE = "availability_rule"
    QUALIFICATION_RULE = "qualification_rule"
    ESCALATION_RULE = "escalation_rule"
    IDENTITY_UPDATE = "identity_update"
    COMMUNICATION_UPDATE = "communication_update"
    GENERAL_KNOWLEDGE = "general_knowledge"


class StripeConnectAccountStatus(StrEnum):
    """Stripe Connect connected-account onboarding status.

    Mirrors the key capabilities/charges/payouts state of a Stripe
    Express/Standard connected account.

    NONE         — No Stripe account created yet.
    PENDING      — Account created but onboarding not completed.
    RESTRICTED   — Account restricted (limited functionality).
    ACTIVE       — Charges and payouts enabled.
    CHARGES_DISABLED   — Onboarding incomplete; charges not allowed.
    PAYOUTS_DISABLED   — Payouts suspended (e.g. missing verification).
    """

    NONE = "none"
    PENDING = "pending"
    RESTRICTED = "restricted"
    ACTIVE = "active"
    CHARGES_DISABLED = "charges_disabled"
    PAYOUTS_DISABLED = "payouts_disabled"


class CommercialPolicyScope(StrEnum):
    """Commercial policy scope / precedence tier.

    Precedence (highest → lowest):
        BUSINESS_SPECIFIC  — Negotiated per-business agreement
        PROMOTION          — Time-limited promotional offer
        BUSINESS_PLAN      — Plan-level policy (e.g. premium plan)
        CATEGORY_DEFAULT   — Service-category / segment default
        GLOBAL_DEFAULT     — FIELDed platform-wide fallback
    """

    GLOBAL_DEFAULT = "global_default"
    CATEGORY_DEFAULT = "category_default"
    BUSINESS_PLAN = "business_plan"
    PROMOTION = "promotion"
    BUSINESS_SPECIFIC = "business_specific"


# Numeric precedence — higher value wins.
COMMERCIAL_POLICY_PRECEDENCE: dict[CommercialPolicyScope, int] = {
    CommercialPolicyScope.GLOBAL_DEFAULT: 0,
    CommercialPolicyScope.CATEGORY_DEFAULT: 10,
    CommercialPolicyScope.BUSINESS_PLAN: 20,
    CommercialPolicyScope.PROMOTION: 30,
    CommercialPolicyScope.BUSINESS_SPECIFIC: 40,
}


class CommercialPolicyFeeType(StrEnum):
    """How the FIELDed platform fee is calculated.

    PERCENTAGE — fee = amount × percent / 100
    FIXED      — fee = fixed_amount (regardless of transaction value)
    COMBINED   — fee = (amount × percent / 100) + fixed_amount
    ZERO       — fee = 0 (launch / onboarding / free-tier)
    """

    PERCENTAGE = "percentage"
    FIXED = "fixed"
    COMBINED = "combined"
    ZERO = "zero"


class CommercialPolicyStatus(StrEnum):
    """Commercial policy lifecycle.

    DRAFT      — Being configured; not yet effective.
    ACTIVE     — Currently effective for eligible transactions.
    INACTIVE   — Manually deactivated (e.g. early retirement).
    SUPERSEDED — Replaced by a newer version of the same policy.
    """

    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUPERSEDED = "superseded"


COMMERCIAL_POLICY_TRANSITIONS: dict[CommercialPolicyStatus, set[CommercialPolicyStatus]] = {
    CommercialPolicyStatus.DRAFT: {CommercialPolicyStatus.ACTIVE, CommercialPolicyStatus.INACTIVE},
    CommercialPolicyStatus.ACTIVE: {CommercialPolicyStatus.INACTIVE, CommercialPolicyStatus.SUPERSEDED},
    CommercialPolicyStatus.INACTIVE: {CommercialPolicyStatus.ACTIVE},
    CommercialPolicyStatus.SUPERSEDED: set(),
}


class BrainKnowledgeStatus(StrEnum):
    """Brain memory classification for learned information.

    Known      — Explicitly confirmed by the owner
    Proposed   — Inferred/suggested by Brain, awaiting approval
    Uncertain  — Needs clarification from the owner
    Deprecated — Previously valid, now replaced
    Rejected   — Explicitly rejected by the owner
    """

    KNOWN = "known"
    PROPOSED = "proposed"
    UNCERTAIN = "uncertain"
    DEPRECATED = "deprecated"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# Agent Capability / Delegation Architecture
# ---------------------------------------------------------------------------


class AgentType(StrEnum):
    """Registered agent types in the FIELDed platform.

    Each agent type has a defined set of capabilities.
    """

    DISCOVERY = "discovery"
    BRAIN = "brain"
    CALL_AGENT = "call_agent"
    MARKETING = "marketing"


class AgentCapabilityType(StrEnum):
    """Capabilities that agents may be granted.

    Capabilities are atomic permissions — an agent either has the
    capability or does not.  Capabilities are scoped to a business
    and a specific agent type.
    """

    # Discovery capabilities
    INTERPRET_INTENT = "interpret_intent"
    MATCH_BUSINESSES = "match_businesses"

    # Brain / Co-Brain capabilities
    READ_BUSINESS_CONTEXT = "read_business_context"
    PROPOSE_CHANGES = "propose_changes"
    ACTIVATE_BRAIN_VERSION = "activate_brain_version"
    READ_ENQUIRY_CONTEXT = "read_enquiry_context"
    READ_BOOKING_CONTEXT = "read_booking_context"

    # Call Agent capabilities
    HANDLE_INBOUND_CALL = "handle_inbound_call"
    MAKE_OUTBOUND_CALL = "make_outbound_call"
    CREATE_ENQUIRY_FROM_CALL = "create_enquiry_from_call"
    COLLECT_CALLER_INFO = "collect_caller_info"
    SUMMARISE_CALL = "summarise_call"
    ESCALATE_CALL = "escalate_call"

    # Marketing capabilities
    DRAFT_CONTENT = "draft_content"
    SCHEDULE_CAMPAIGN = "schedule_campaign"
    EXECUTE_CAMPAIGN = "execute_campaign"
    ANALYTICS_READ = "analytics_read"

    # Communication capabilities
    SEND_MESSAGE = "send_message"
    SEND_NOTIFICATION = "send_notification"


class AgentAuthorityMode(StrEnum):
    """How an agent is authorised to act for a given capability.

    DISABLED       — Capability is not available.
    ASSIST         — Agent may propose / interpret but never execute.
    APPROVAL       — Agent may execute only after explicit owner approval.
    DELEGATED      — Agent may execute automatically within deterministic
                     policy bounds (e.g. price within configured range).
    """

    DISABLED = "disabled"
    ASSIST = "assist"
    APPROVAL = "approval"
    DELEGATED = "delegated"


class AgentDelegationStatus(StrEnum):
    """Lifecycle of an agent delegation record.

    ACTIVE   — Delegation is currently effective.
    REVOKED  — Owner explicitly revoked the delegation.
    EXPIRED  — Time-bounded delegation has expired.
    """

    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
