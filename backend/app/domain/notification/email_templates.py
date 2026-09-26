"""Transactional email templates for FIELDed lifecycle events.

Each template is a (subject, html_body) pair with {{ variable }} placeholders.
Templates use real FIELDed data from outbox event payloads — no invented
customer or business information.

The EmailNotificationService selects the correct template for each event
type and renders it with variables resolved from the domain.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EmailTemplate:
    """A transactional email template.

    Attributes:
        event_type: The outbox event type this template handles.
        subject: Email subject line with {{ variable }} placeholders.
        heading: Main heading shown in the email body.
        body: HTML body with {{ variable }} placeholders.
        recipient_kind: "customer" | "business" | "both".
    """

    event_type: str
    subject: str
    heading: str
    body: str
    recipient_kind: str


# ── HTML layout helpers ──────────────────────────────────────────────────────

_WRAPPER_TOP = """\
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #1a1a1a;">
<div style="background: #f8f9fa; border-radius: 8px; padding: 32px; margin-bottom: 16px;">
<h1 style="margin: 0 0 16px 0; font-size: 20px; color: #111;">{{ heading }}</h1>
<div style="background: #ffffff; border-radius: 6px; padding: 24px; border: 1px solid #e2e8f0;">
"""

_WRAPPER_BOTTOM = """\
</div>
</div>
<p style="font-size: 12px; color: #6b7280; margin-top: 24px;">
  This is an automated message from FIELDed. Do not reply directly to this email.
</p>
</div>
"""


def _wrap(content: str) -> str:
    """Wrap template content in the standard FIELDed email layout."""
    return _WRAPPER_TOP + content + _WRAPPER_BOTTOM


# ── Customer templates ───────────────────────────────────────────────────────

_CUSTOMER_ENQUIRY_SUBMITTED = EmailTemplate(
    event_type="ENQUIRY_SUBMITTED",
    subject="Your enquiry {{ reference }} has been sent",
    heading="Enquiry Submitted",
    body=_wrap(
        "<p>Hi {{ customer_name }},</p>"
        "<p>Your enquiry <strong>{{ reference }}</strong> has been sent to "
        "<strong>{{ business_name }}</strong>.</p>"
        "<p><strong>Subject:</strong> {{ subject }}</p>"
        "<p>The business will review your enquiry and respond. "
        "You will be notified when they reply.</p>"
    ),
    recipient_kind="customer",
)

_CUSTOMER_BUSINESS_RESPONDED = EmailTemplate(
    event_type="ENQUIRY_BUSINESS_RESPONDED",
    subject="{{ business_name }} responded to your enquiry {{ reference }}",
    heading="Business Responded",
    body=_wrap(
        "<p>Hi {{ customer_name }},</p>"
        "<p><strong>{{ business_name }}</strong> has responded to your "
        "enquiry <strong>{{ reference }}</strong>.</p>"
        "<p>Log in to FIELDed to read their message and continue the conversation.</p>"
    ),
    recipient_kind="customer",
)

_CUSTOMER_QUOTE_RECEIVED = EmailTemplate(
    event_type="QUOTE_SENT",
    subject="You have a new quote ({{ quote_reference }})",
    heading="Quote Received",
    body=_wrap(
        "<p>Hi {{ customer_name }},</p>"
        "<p><strong>{{ business_name }}</strong> has sent you quote "
        "<strong>{{ quote_reference }}</strong>.</p>"
        "<p>Log in to FIELDed to review the quote and accept it if you are "
        "ready to proceed.</p>"
    ),
    recipient_kind="customer",
)

_CUSTOMER_QUOTE_ACCEPTED = EmailTemplate(
    event_type="QUOTE_ACCEPTED",
    subject="Quote {{ quote_reference }} accepted",
    heading="Quote Accepted",
    body=_wrap(
        "<p>Hi {{ customer_name }},</p>"
        "<p>Quote <strong>{{ quote_reference }}</strong> has been accepted. "
        "The business will now prepare your booking.</p>"
    ),
    recipient_kind="customer",
)

_CUSTOMER_BOOKING_REQUESTED = EmailTemplate(
    event_type="BOOKING_PROPOSED",
    subject="Booking proposed for {{ reference }}",
    heading="Booking Proposed",
    body=_wrap(
        "<p>Hi {{ customer_name }},</p>"
        "<p><strong>{{ business_name }}</strong> has proposed a booking "
        "for <strong>{{ reference }}</strong>.</p>"
        "<p>Log in to FIELDed to review and confirm the booking details.</p>"
    ),
    recipient_kind="customer",
)

_CUSTOMER_BOOKING_CONFIRMED = EmailTemplate(
    event_type="BOOKING_CONFIRMED",
    subject="Booking {{ reference }} confirmed",
    heading="Booking Confirmed",
    body=_wrap(
        "<p>Hi {{ customer_name }},</p>"
        "<p>Your booking <strong>{{ reference }}</strong> has been confirmed "
        "with <strong>{{ business_name }}</strong>.</p>"
        "<p>You will be notified of any changes.</p>"
    ),
    recipient_kind="customer",
)

_CUSTOMER_BOOKING_CHANGED = EmailTemplate(
    event_type="BOOKING_RESCHEDULED",
    subject="Booking {{ reference }} has been updated",
    heading="Booking Updated",
    body=_wrap(
        "<p>Hi {{ customer_name }},</p>"
        "<p>Your booking <strong>{{ reference }}</strong> has been updated. "
        "Log in to FIELDed to see the new details.</p>"
    ),
    recipient_kind="customer",
)

_CUSTOMER_BOOKING_CANCELLED = EmailTemplate(
    event_type="BOOKING_CANCELLED",
    subject="Booking {{ reference }} cancelled",
    heading="Booking Cancelled",
    body=_wrap(
        "<p>Hi {{ customer_name }},</p>"
        "<p>Your booking <strong>{{ reference }}</strong> has been cancelled.</p>"
        "<p>If you have questions, contact <strong>{{ business_name }}</strong> "
        "through FIELDed.</p>"
    ),
    recipient_kind="customer",
)

_CUSTOMER_PAYMENT_SUCCEEDED = EmailTemplate(
    event_type="PAYMENT_SUCCEEDED",
    subject="Payment received — {{ currency }} {{ amount }}",
    heading="Payment Received",
    body=_wrap(
        "<p>Hi {{ customer_name }},</p>"
        "<p>Your payment of <strong>{{ currency }} {{ amount }}</strong> has "
        "been received successfully.</p>"
        "<p>Thank you for using FIELDed.</p>"
    ),
    recipient_kind="customer",
)

_CUSTOMER_PAYMENT_FAILED = EmailTemplate(
    event_type="PAYMENT_FAILED",
    subject="Payment failed — {{ currency }} {{ amount }}",
    heading="Payment Failed",
    body=_wrap(
        "<p>Hi {{ customer_name }},</p>"
        "<p>Your payment of <strong>{{ currency }} {{ amount }}</strong> could "
        "not be processed.</p>"
        "<p>Please try again or use a different payment method through FIELDed.</p>"
    ),
    recipient_kind="customer",
)

_CUSTOMER_SERVICE_COMPLETED = EmailTemplate(
    event_type="SERVICE_COMPLETED",
    subject="Your service is complete",
    heading="Service Completed",
    body=_wrap(
        "<p>Hi {{ customer_name }},</p>"
        "<p>Your service with <strong>{{ business_name }}</strong> "
        "(booking <strong>{{ reference }}</strong>) has been marked as complete.</p>"
        "<p>Log in to FIELDed to leave a review and share your experience.</p>"
    ),
    recipient_kind="customer",
)

_CUSTOMER_REVIEW_ELIGIBLE = EmailTemplate(
    event_type="REVIEW_ELIGIBLE",
    subject="How was your experience with {{ business_name }}?",
    heading="Leave a Review",
    body=_wrap(
        "<p>Hi {{ customer_name }},</p>"
        "<p>Your service with <strong>{{ business_name }}</strong> is now "
        "eligible for review.</p>"
        "<p>Log in to FIELDed to share your feedback and help other customers "
        "make informed decisions.</p>"
    ),
    recipient_kind="customer",
)

# ── Business templates ───────────────────────────────────────────────────────

_BUSINESS_NEW_ENQUIRY = EmailTemplate(
    event_type="ENQUIRY_SUBMITTED",
    subject="New enquiry {{ reference }} from {{ customer_name }}",
    heading="New Enquiry Received",
    body=_wrap(
        "<p>A new enquiry has been received.</p>"
        "<p><strong>Reference:</strong> {{ reference }}</p>"
        "<p><strong>Customer:</strong> {{ customer_name }}</p>"
        "<p><strong>Subject:</strong> {{ subject }}</p>"
        "<p>Log in to FIELDed to review and respond.</p>"
    ),
    recipient_kind="business",
)

_BUSINESS_CUSTOMER_MESSAGE = EmailTemplate(
    event_type="ENQUIRY_BUSINESS_RESPONDED",
    subject="New message in enquiry {{ reference }}",
    heading="Customer Message",
    body=_wrap(
        "<p>A customer has sent a message in enquiry "
        "<strong>{{ reference }}</strong>.</p>"
        "<p>Log in to FIELDed to read and respond.</p>"
    ),
    recipient_kind="business",
)

_BUSINESS_QUOTE_ACCEPTED = EmailTemplate(
    event_type="QUOTE_ACCEPTED",
    subject="Quote {{ quote_reference }} accepted by customer",
    heading="Quote Accepted",
    body=_wrap(
        "<p>Your quote <strong>{{ quote_reference }}</strong> has been "
        "accepted by the customer.</p>"
        "<p>Log in to FIELDed to create the booking.</p>"
    ),
    recipient_kind="business",
)

_BUSINESS_BOOKING_REQUESTED = EmailTemplate(
    event_type="BOOKING_PROPOSED",
    subject="Booking {{ reference }} ready for confirmation",
    heading="Booking Request",
    body=_wrap(
        "<p>A booking has been proposed for <strong>{{ reference }}</strong>.</p>"
        "<p>Log in to FIELDed to review and confirm.</p>"
    ),
    recipient_kind="business",
)

_BUSINESS_BOOKING_CONFIRMED = EmailTemplate(
    event_type="BOOKING_CONFIRMED",
    subject="Booking {{ reference }} confirmed",
    heading="Booking Confirmed",
    body=_wrap("<p>Booking <strong>{{ reference }}</strong> has been confirmed.</p>"),
    recipient_kind="business",
)

_BUSINESS_BOOKING_CANCELLED = EmailTemplate(
    event_type="BOOKING_CANCELLED",
    subject="Booking {{ reference }} cancelled",
    heading="Booking Cancelled",
    body=_wrap("<p>Booking <strong>{{ reference }}</strong> has been cancelled.</p>"),
    recipient_kind="business",
)

_BUSINESS_PAYMENT_STATUS = EmailTemplate(
    event_type="PAYMENT_SUCCEEDED",
    subject="Payment received — {{ currency }} {{ amount }}",
    heading="Payment Received",
    body=_wrap(
        "<p>A payment of <strong>{{ currency }} {{ amount }}</strong> has been "
        "received for booking <strong>{{ reference }}</strong>.</p>"
    ),
    recipient_kind="business",
)

_BUSINESS_PAYMENT_FAILED = EmailTemplate(
    event_type="PAYMENT_FAILED",
    subject="Payment failed — {{ currency }} {{ amount }}",
    heading="Payment Failed",
    body=_wrap(
        "<p>A payment of <strong>{{ currency }} {{ amount }}</strong> for booking "
        "<strong>{{ reference }}</strong> has failed.</p>"
        "<p>Error: {{ error }}</p>"
    ),
    recipient_kind="business",
)

_BUSINESS_SERVICE_DUE = EmailTemplate(
    event_type="BOOKING_CONFIRMED",
    subject="Upcoming service — {{ reference }}",
    heading="Service Due",
    body=_wrap(
        "<p>Booking <strong>{{ reference }}</strong> is confirmed and the "
        "service is due.</p>"
        "<p>Log in to FIELDed to prepare.</p>"
    ),
    recipient_kind="business",
)

_BUSINESS_SERVICE_COMPLETED = EmailTemplate(
    event_type="SERVICE_COMPLETED",
    subject="Service completed — {{ reference }}",
    heading="Service Completed",
    body=_wrap("<p>Booking <strong>{{ reference }}</strong> has been marked as complete.</p>"),
    recipient_kind="business",
)

# ── Template registry ────────────────────────────────────────────────────────

CUSTOMER_TEMPLATES: dict[str, EmailTemplate] = {
    t.event_type: t
    for t in [
        _CUSTOMER_ENQUIRY_SUBMITTED,
        _CUSTOMER_BUSINESS_RESPONDED,
        _CUSTOMER_QUOTE_RECEIVED,
        _CUSTOMER_QUOTE_ACCEPTED,
        _CUSTOMER_BOOKING_REQUESTED,
        _CUSTOMER_BOOKING_CONFIRMED,
        _CUSTOMER_BOOKING_CHANGED,
        _CUSTOMER_BOOKING_CANCELLED,
        _CUSTOMER_PAYMENT_SUCCEEDED,
        _CUSTOMER_PAYMENT_FAILED,
        _CUSTOMER_SERVICE_COMPLETED,
        _CUSTOMER_REVIEW_ELIGIBLE,
    ]
}

BUSINESS_TEMPLATES: dict[str, EmailTemplate] = {
    t.event_type: t
    for t in [
        _BUSINESS_NEW_ENQUIRY,
        _BUSINESS_CUSTOMER_MESSAGE,
        _BUSINESS_QUOTE_ACCEPTED,
        _BUSINESS_BOOKING_REQUESTED,
        _BUSINESS_BOOKING_CONFIRMED,
        _BUSINESS_BOOKING_CANCELLED,
        _BUSINESS_PAYMENT_STATUS,
        _BUSINESS_PAYMENT_FAILED,
        _BUSINESS_SERVICE_DUE,
        _BUSINESS_SERVICE_COMPLETED,
    ]
}

# Event types that trigger customer emails
CUSTOMER_EMAIL_EVENTS: frozenset[str] = frozenset(CUSTOMER_TEMPLATES.keys())

# Event types that trigger business emails
BUSINESS_EMAIL_EVENTS: frozenset[str] = frozenset(BUSINESS_TEMPLATES.keys())

# All event types that trigger any email
ALL_EMAIL_EVENTS: frozenset[str] = CUSTOMER_EMAIL_EVENTS | BUSINESS_EMAIL_EVENTS

# Mapping from outbox event types to notification event types
# Some outbox events map to the same notification type
_EVENT_TYPE_ALIASES: dict[str, str] = {
    "QUOTE_SENT": "QUOTE_SENT",
    "QUOTE_ACCEPTED": "QUOTE_ACCEPTED",
    "BOOKING_PROPOSED": "BOOKING_PROPOSED",
    "BOOKING_CONFIRMED": "BOOKING_CONFIRMED",
    "BOOKING_CANCELLED": "BOOKING_CANCELLED",
    "BOOKING_RESCHEDULED": "BOOKING_RESCHEDULED",
    "BOOKING_COMPLETED": "SERVICE_COMPLETED",
    "SERVICE_COMPLETED": "SERVICE_COMPLETED",
    "ENQUIRY_SUBMITTED": "ENQUIRY_SUBMITTED",
    "ENQUIRY_BUSINESS_RESPONDED": "ENQUIRY_BUSINESS_RESPONDED",
    "PAYMENT_SUCCEEDED": "PAYMENT_SUCCEEDED",
    "PAYMENT_FAILED": "PAYMENT_FAILED",
    "REVIEW_ELIGIBLE": "REVIEW_ELIGIBLE",
}


def resolve_event_type(event_type: str) -> str:
    """Resolve an outbox event type to its notification event type."""
    return _EVENT_TYPE_ALIASES.get(event_type, event_type)
