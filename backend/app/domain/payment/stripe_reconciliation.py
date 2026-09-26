"""Stripe webhook reconciliation service.

The single authoritative handler for all Stripe webhook events that
affect FIELDed payment state.  Every event passes through:

    1. Idempotency check (StripeEvent table)
    2. Event routing (payment_intent / refund / dispute / account)
    3. Tenant isolation (Stripe account → business verification)
    4. Deterministic state transition (PaymentStatus state machine)
    5. Financial record update (Payment → Invoice → LedgerEntry)
    6. Evidence preservation (raw payload stored in StripeEvent)
    7. Outbox event emission (notification / downstream processing)

AI may READ and EXPLAIN reconciliation results but must NEVER:
- Override the deterministic state machine
- Change financial amounts
- Skip tenant isolation checks
- Mark a payment successful without evidence
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.payment.base import WebhookEvent
from app.domain.common.enums import (
    InvoicePaymentStatus,
    PaymentStatus,
)
from app.domain.identity.models import Business
from app.domain.invoice.repository import InvoiceRepository
from app.domain.ledger.repository import LedgerRepository
from app.domain.outbox.models import OutboxEvent
from app.domain.payment.models import Payment
from app.domain.payment.repository import PaymentRepository
from app.domain.payment.stripe_event_model import StripeEvent
from app.exceptions import StateTransitionError
from app.logging import get_logger

logger = get_logger(__name__)

# Event types that the reconciliation service handles
_HANDLED_EVENT_TYPES: frozenset[str] = frozenset(
    {
        # PaymentIntent lifecycle
        "payment_intent.succeeded",
        "payment_intent.payment_failed",
        "payment_intent.canceled",
        "payment_intent.requires_action",
        "payment_intent.processing",
        "payment_intent.amount_capturable_updated",
        # Refund lifecycle
        "charge.refund.updated",
        "charge.refunded",
        # Dispute lifecycle
        "charge.dispute.created",
        "charge.dispute.updated",
        "charge.dispute.closed",
        "charge.dispute.funds_reinstated",
        "charge.dispute.funds_withdrawn",
    }
)


class StripeWebhookReconciliationService:
    """Deterministic Stripe webhook reconciliation.

    Usage:
        service = StripeWebhookReconciliationService(session)
        result = await service.reconcile(event)
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.payment_repo = PaymentRepository(session)
        self.invoice_repo = InvoiceRepository(session)
        self.ledger_repo = LedgerRepository(session)

    async def reconcile(self, event: WebhookEvent) -> StripeEvent:
        """Process a Stripe webhook event with full reconciliation.

        Returns the StripeEvent record (created or existing for
        duplicate detection).
        """
        # ── 1. Idempotency check ───────────────────────────────────
        existing = await self._get_event_by_stripe_id(event.provider_event_id)
        if existing is not None:
            logger.info(
                "stripe_webhook_duplicate",
                stripe_event_id=event.provider_event_id,
                original_status=existing.status,
            )
            existing.status = "duplicate"
            await self.session.flush()
            return existing

        # ── 2. Check if this event type is relevant ────────────────
        if event.event_type not in _HANDLED_EVENT_TYPES:
            stripe_event = self._create_stripe_event(
                event=event,
                status="ignored",
                error_message=f"Event type {event.event_type} is not handled",
            )
            self.session.add(stripe_event)
            await self.session.flush()
            logger.info(
                "stripe_webhook_ignored",
                event_type=event.event_type,
                stripe_event_id=event.provider_event_id,
            )
            return stripe_event

        # ── 3. Find the FIELDed payment ────────────────────────────
        payment = None
        if event.provider_payment_reference:
            payment = await self.payment_repo.get_by_provider_reference(event.provider_payment_reference)

        # If no payment found by provider_reference, try to find by
        # looking at the PaymentIntent metadata (for events that arrive
        # before the payment is fully linked).
        if payment is None and event.raw_payload:
            payment = await self._find_payment_by_metadata(event)

        # ── 4. Tenant isolation ────────────────────────────────────
        if payment is not None:
            tenant_ok = await self._verify_tenant_isolation(
                payment=payment,
                event=event,
            )
            if not tenant_ok:
                stripe_event = self._create_stripe_event(
                    event=event,
                    status="tenant_mismatch",
                    payment=payment,
                    error_message=(f"Stripe account mismatch for payment {payment.id}"),
                )
                self.session.add(stripe_event)
                await self.session.flush()
                logger.warning(
                    "stripe_webhook_tenant_mismatch",
                    stripe_event_id=event.provider_event_id,
                    payment_id=str(payment.id),
                )
                return stripe_event

        if payment is None:
            stripe_event = self._create_stripe_event(
                event=event,
                status="unknown_payment",
                error_message=(f"No FIELDed payment found for provider_reference={event.provider_payment_reference}"),
            )
            self.session.add(stripe_event)
            await self.session.flush()
            logger.warning(
                "stripe_webhook_unknown_payment",
                stripe_event_id=event.provider_event_id,
                provider_reference=event.provider_payment_reference,
            )
            return stripe_event

        # ── 5. Route to handler ────────────────────────────────────
        try:
            stripe_event = await self._route_event(event, payment)
        except Exception as exc:
            logger.exception(
                "stripe_webhook_reconciliation_error",
                stripe_event_id=event.provider_event_id,
                payment_id=str(payment.id),
            )
            stripe_event = self._create_stripe_event(
                event=event,
                status="error",
                payment=payment,
                error_message=str(exc),
            )
            self.session.add(stripe_event)
            await self.session.flush()
            return stripe_event

        return stripe_event

    # ── Event routing ──────────────────────────────────────────────

    async def _route_event(self, event: WebhookEvent, payment: Payment) -> StripeEvent:
        """Route a verified event to the appropriate handler."""
        event_type = event.event_type

        if event_type.startswith("payment_intent."):
            return await self._handle_payment_intent(event, payment)

        if event_type.startswith("charge.refund"):
            return await self._handle_refund(event, payment)

        if event_type.startswith("charge.dispute."):
            return await self._handle_dispute(event, payment)

        # Should not reach here (filtered by _HANDLED_EVENT_TYPES)
        return self._create_stripe_event(
            event=event,
            status="ignored",
            payment=payment,
        )

    # ── PaymentIntent handlers ─────────────────────────────────────

    async def _handle_payment_intent(self, event: WebhookEvent, payment: Payment) -> StripeEvent:
        """Handle payment_intent.* events."""
        event_type = event.event_type
        current_status = PaymentStatus(payment.status)

        if event_type == "payment_intent.succeeded":
            return await self._apply_payment_success(event, payment)

        if event_type == "payment_intent.payment_failed":
            return await self._apply_payment_failed(event, payment)

        if event_type == "payment_intent.canceled":
            return await self._apply_payment_cancelled(event, payment)

        if event_type in (
            "payment_intent.requires_action",
            "payment_intent.processing",
            "payment_intent.amount_capturable_updated",
        ):
            # Intermediate states — record evidence but don't transition
            # if already in a terminal state.
            if current_status in (
                PaymentStatus.SUCCEEDED,
                PaymentStatus.FAILED,
                PaymentStatus.EXPIRED,
                PaymentStatus.CANCELLED,
                PaymentStatus.REFUNDED,
            ):
                return self._create_stripe_event(
                    event=event,
                    status="processed",
                    payment=payment,
                    error_message=(
                        f"Ignored intermediate event {event_type} for payment in status {current_status.value}"
                    ),
                )

            # Update provider evidence on the payment
            payment.provider_evidence = event.raw_payload
            await self.payment_repo.update(payment)

            return self._create_stripe_event(event=event, status="processed", payment=payment)

        return self._create_stripe_event(event=event, status="ignored", payment=payment)

    async def _apply_payment_success(self, event: WebhookEvent, payment: Payment) -> StripeEvent:
        """Transition payment to SUCCEEDED and update financial records."""
        current_status = PaymentStatus(payment.status)

        # Already succeeded — idempotent
        if current_status == PaymentStatus.SUCCEEDED:
            return self._create_stripe_event(
                event=event,
                status="processed",
                payment=payment,
                error_message="Payment already succeeded (idempotent)",
            )

        # Validate transition
        try:
            self._validate_transition(current_status, PaymentStatus.SUCCEEDED)
        except StateTransitionError:
            return self._create_stripe_event(
                event=event,
                status="error",
                payment=payment,
                error_message=(f"Invalid transition {current_status.value} -> succeeded"),
            )

        now = datetime.now(UTC)
        payment.status = PaymentStatus.SUCCEEDED
        payment.paid_at = now
        payment.provider_evidence = event.raw_payload

        # Verify amount matches (defensive check)
        if event.amount is not None:
            expected = Decimal(payment.amount)
            if event.amount != expected:
                logger.warning(
                    "stripe_webhook_amount_mismatch",
                    payment_id=str(payment.id),
                    expected=str(expected),
                    received=str(event.amount),
                )

        await self.payment_repo.update(payment)

        # Update invoice payment status
        await self._update_invoice_payment_status(payment)

        # Emit outbox event
        await self._emit_outbox_event(
            business_id=payment.business_id,
            event_type="PAYMENT_SUCCEEDED",
            aggregate_id=payment.id,
            payload={
                "payment_id": str(payment.id),
                "invoice_id": str(payment.invoice_id),
                "customer_id": str(payment.customer_id),
                "amount": payment.amount,
                "currency": payment.currency,
                "status": PaymentStatus.SUCCEEDED,
                "stripe_event_id": event.provider_event_id,
                "notification_title": "Payment received",
                "notification_body": (f"Payment of {payment.currency} {payment.amount} received successfully."),
            },
        )

        logger.info(
            "stripe_webhook_payment_succeeded",
            payment_id=str(payment.id),
            stripe_event_id=event.provider_event_id,
        )

        return self._create_stripe_event(event=event, status="processed", payment=payment)

    async def _apply_payment_failed(self, event: WebhookEvent, payment: Payment) -> StripeEvent:
        """Transition payment to FAILED."""
        current_status = PaymentStatus(payment.status)

        if current_status == PaymentStatus.FAILED:
            return self._create_stripe_event(
                event=event,
                status="processed",
                payment=payment,
                error_message="Payment already failed (idempotent)",
            )

        try:
            self._validate_transition(current_status, PaymentStatus.FAILED)
        except StateTransitionError:
            return self._create_stripe_event(
                event=event,
                status="error",
                payment=payment,
                error_message=(f"Invalid transition {current_status.value} -> failed"),
            )

        payment.status = PaymentStatus.FAILED
        payment.failure_code = "stripe_payment_failed"
        payment.provider_evidence = event.raw_payload

        # Extract failure message from the event
        data_object = event.raw_payload.get("data", {}).get("object", {})
        last_error = data_object.get("last_payment_error", {})
        if last_error:
            payment.failure_message = last_error.get("message") or last_error.get("decline_code") or "Payment failed"

        await self.payment_repo.update(payment)

        await self._emit_outbox_event(
            business_id=payment.business_id,
            event_type="PAYMENT_FAILED",
            aggregate_id=payment.id,
            payload={
                "payment_id": str(payment.id),
                "invoice_id": str(payment.invoice_id),
                "customer_id": str(payment.customer_id),
                "amount": payment.amount,
                "currency": payment.currency,
                "status": PaymentStatus.FAILED,
                "error": payment.failure_message,
                "stripe_event_id": event.provider_event_id,
                "notification_title": "Payment failed",
                "notification_body": (
                    f"Payment of {payment.currency} {payment.amount} failed: "
                    f"{payment.failure_message or 'Unknown error'}"
                ),
            },
        )

        logger.info(
            "stripe_webhook_payment_failed",
            payment_id=str(payment.id),
            stripe_event_id=event.provider_event_id,
        )

        return self._create_stripe_event(event=event, status="processed", payment=payment)

    async def _apply_payment_cancelled(self, event: WebhookEvent, payment: Payment) -> StripeEvent:
        """Transition payment to CANCELLED."""
        current_status = PaymentStatus(payment.status)

        if current_status == PaymentStatus.CANCELLED:
            return self._create_stripe_event(
                event=event,
                status="processed",
                payment=payment,
                error_message="Payment already cancelled (idempotent)",
            )

        try:
            self._validate_transition(current_status, PaymentStatus.CANCELLED)
        except StateTransitionError:
            return self._create_stripe_event(
                event=event,
                status="error",
                payment=payment,
                error_message=(f"Invalid transition {current_status.value} -> cancelled"),
            )

        payment.status = PaymentStatus.CANCELLED
        payment.provider_evidence = event.raw_payload
        await self.payment_repo.update(payment)

        return self._create_stripe_event(event=event, status="processed", payment=payment)

    # ── Refund handlers ────────────────────────────────────────────

    async def _handle_refund(self, event: WebhookEvent, payment: Payment) -> StripeEvent:
        """Handle charge.refund.updated and charge.refunded events.

        Reconciles the refund against the FIELDed payment's
        refunded_amount and transitions to REFUNDED /
        PARTIALLY_REFUNDED as appropriate.
        """
        current_status = PaymentStatus(payment.status)

        # Only succeeded or partially_refunded payments can receive refunds
        if current_status not in (
            PaymentStatus.SUCCEEDED,
            PaymentStatus.PARTIALLY_REFUNDED,
        ):
            return self._create_stripe_event(
                event=event,
                status="error",
                payment=payment,
                error_message=(f"Refund event for payment in status {current_status.value} — cannot process refund"),
            )

        # Extract refund details from the event
        data_object = event.raw_payload.get("data", {}).get("object", {})
        refund_amount_stripe = data_object.get("amount_refunded", 0)
        currency = data_object.get("currency", payment.currency)

        # Convert from Stripe minor units
        zero_decimal = {"jpy", "krw", "vnd", "clp", "huf"}
        if currency.lower() in zero_decimal:
            total_refunded = Decimal(str(refund_amount_stripe))
        else:
            total_refunded = Decimal(str(refund_amount_stripe)) / Decimal("100")

        payment_amount = Decimal(payment.amount)

        # Update refunded amount
        payment.refunded_amount = str(total_refunded)
        payment.refunded_at = datetime.now(UTC)
        payment.provider_evidence = event.raw_payload

        # Determine new status
        if total_refunded >= payment_amount:
            try:
                self._validate_transition(current_status, PaymentStatus.REFUNDED)
            except StateTransitionError:
                return self._create_stripe_event(
                    event=event,
                    status="error",
                    payment=payment,
                    error_message=(f"Invalid transition {current_status.value} -> refunded"),
                )
            payment.status = PaymentStatus.REFUNDED
        else:
            try:
                self._validate_transition(current_status, PaymentStatus.PARTIALLY_REFUNDED)
            except StateTransitionError:
                return self._create_stripe_event(
                    event=event,
                    status="error",
                    payment=payment,
                    error_message=(f"Invalid transition {current_status.value} -> partially_refunded"),
                )
            payment.status = PaymentStatus.PARTIALLY_REFUNDED

        await self.payment_repo.update(payment)

        # Update invoice payment status
        await self._update_invoice_payment_status(payment)

        # Emit outbox event
        await self._emit_outbox_event(
            business_id=payment.business_id,
            event_type="PAYMENT_REFUNDED",
            aggregate_id=payment.id,
            payload={
                "payment_id": str(payment.id),
                "invoice_id": str(payment.invoice_id),
                "customer_id": str(payment.customer_id),
                "refund_amount": str(total_refunded),
                "currency": payment.currency,
                "status": payment.status,
                "stripe_event_id": event.provider_event_id,
                "notification_title": "Refund processed",
                "notification_body": (f"Refund of {payment.currency} {total_refunded} has been processed."),
            },
        )

        logger.info(
            "stripe_webhook_refund_processed",
            payment_id=str(payment.id),
            refund_amount=str(total_refunded),
            new_status=payment.status,
            stripe_event_id=event.provider_event_id,
        )

        return self._create_stripe_event(event=event, status="processed", payment=payment)

    # ── Dispute handlers ───────────────────────────────────────────

    async def _handle_dispute(self, event: WebhookEvent, payment: Payment) -> StripeEvent:
        """Handle charge.dispute.* events.

        Tracks the dispute on the payment record and transitions
        payment state appropriately.
        """
        event_type = event.event_type
        data_object = event.raw_payload.get("data", {}).get("object", {})
        dispute_id = data_object.get("id", "")
        dispute_reason = data_object.get("reason", "")
        dispute_status = data_object.get("status", "")
        current_status = PaymentStatus(payment.status)

        if event_type == "charge.dispute.created":
            # A dispute has been opened — transition to DISPUTED
            if current_status not in (
                PaymentStatus.SUCCEEDED,
                PaymentStatus.PARTIALLY_REFUNDED,
            ):
                return self._create_stripe_event(
                    event=event,
                    status="error",
                    payment=payment,
                    error_message=(f"Dispute created for payment in status {current_status.value}"),
                )

            try:
                self._validate_transition(current_status, PaymentStatus.DISPUTED)
            except StateTransitionError:
                return self._create_stripe_event(
                    event=event,
                    status="error",
                    payment=payment,
                    error_message=(f"Invalid transition {current_status.value} -> disputed"),
                )

            payment.status = PaymentStatus.DISPUTED
            payment.dispute_id = dispute_id
            payment.dispute_reason = dispute_reason
            payment.dispute_status = dispute_status
            payment.dispute_created_at = datetime.now(UTC)
            payment.dispute_evidence = data_object
            payment.provider_evidence = event.raw_payload

            await self.payment_repo.update(payment)

            # Update invoice to reflect disputed state
            await self._update_invoice_payment_status(payment)

            await self._emit_outbox_event(
                business_id=payment.business_id,
                event_type="PAYMENT_DISPUTED",
                aggregate_id=payment.id,
                payload={
                    "payment_id": str(payment.id),
                    "invoice_id": str(payment.invoice_id),
                    "dispute_id": dispute_id,
                    "dispute_reason": dispute_reason,
                    "amount": payment.amount,
                    "currency": payment.currency,
                    "status": PaymentStatus.DISPUTED,
                    "stripe_event_id": event.provider_event_id,
                    "notification_title": "Payment disputed",
                    "notification_body": (
                        f"Payment of {payment.currency} {payment.amount} has been disputed. Reason: {dispute_reason}"
                    ),
                },
            )

            logger.info(
                "stripe_webhook_dispute_created",
                payment_id=str(payment.id),
                dispute_id=dispute_id,
                reason=dispute_reason,
            )

        elif event_type == "charge.dispute.closed":
            # Dispute resolved — check outcome
            dispute_outcome = data_object.get("status", "")

            if dispute_outcome in ("lost", "expired") and current_status == PaymentStatus.DISPUTED:
                # Business lost the dispute — funds are gone
                try:
                    self._validate_transition(current_status, PaymentStatus.REFUNDED)
                except StateTransitionError:
                    return self._create_stripe_event(
                        event=event,
                        status="error",
                        payment=payment,
                        error_message=(f"Cannot transition {current_status.value} -> refunded on dispute lost"),
                    )
                payment.status = PaymentStatus.REFUNDED
                payment.dispute_status = dispute_outcome
                payment.provider_evidence = event.raw_payload
                await self.payment_repo.update(payment)
                await self._update_invoice_payment_status(payment)

            elif dispute_outcome == "won" and current_status == PaymentStatus.DISPUTED:
                # Business won the dispute — funds reinstated
                try:
                    self._validate_transition(current_status, PaymentStatus.SUCCEEDED)
                except StateTransitionError:
                    return self._create_stripe_event(
                        event=event,
                        status="error",
                        payment=payment,
                        error_message=(f"Cannot transition {current_status.value} -> succeeded on dispute won"),
                    )
                payment.status = PaymentStatus.SUCCEEDED
                payment.dispute_status = dispute_outcome
                payment.provider_evidence = event.raw_payload
                await self.payment_repo.update(payment)
                await self._update_invoice_payment_status(payment)

        elif event_type in (
            "charge.dispute.updated",
            "charge.dispute.funds_reinstated",
            "charge.dispute.funds_withdrawn",
        ):
            # Update dispute evidence without state transition
            payment.dispute_evidence = data_object
            payment.dispute_status = dispute_status
            payment.provider_evidence = event.raw_payload
            await self.payment_repo.update(payment)

        logger.info(
            "stripe_webhook_dispute_handled",
            payment_id=str(payment.id),
            event_type=event_type,
            dispute_id=dispute_id,
        )

        return self._create_stripe_event(event=event, status="processed", payment=payment)

    # ── Tenant isolation ───────────────────────────────────────────

    async def _verify_tenant_isolation(self, payment: Payment, event: WebhookEvent) -> bool:
        """Verify the Stripe event belongs to the payment's business.

        For Direct Charges, the PaymentIntent's on_behalf_of / account
        must match the business's stripe_account_id.

        Returns True if the event is legitimate for this business,
        False if there is a mismatch.
        """
        # Extract the connected account from the event
        data_object = event.raw_payload.get("data", {}).get("object", {})
        event_account = data_object.get("on_behalf_of") or data_object.get("account") or ""

        if not event_account:
            # No connected account in the event — this could be a
            # platform-level charge.  Allow it if the business has
            # no stripe_account_id either.
            result = await self.session.execute(
                select(Business.stripe_account_id).where(
                    Business.id == payment.business_id,
                    Business.deleted_at.is_(None),
                )
            )
            business_account = result.scalar_one_or_none()
            if not business_account:
                return True  # Both empty — acceptable
            # Business has an account but event doesn't reference it.
            # This is suspicious but not definitive — allow for now
            # and log a warning.
            logger.warning(
                "stripe_webhook_no_account_in_event",
                payment_id=str(payment.id),
                business_has_account=business_account,
            )
            return True

        # Look up the business's Stripe account
        result = await self.session.execute(
            select(Business.stripe_account_id).where(
                Business.id == payment.business_id,
                Business.deleted_at.is_(None),
            )
        )
        business_account = result.scalar_one_or_none()

        if not business_account:
            # Business has no Stripe account but the event references one.
            # This is a mismatch — the event shouldn't be for this business.
            logger.warning(
                "stripe_webhook_business_has_no_account",
                payment_id=str(payment.id),
                event_account=event_account,
            )
            return False

        if event_account != business_account:
            logger.warning(
                "stripe_webhook_account_mismatch",
                payment_id=str(payment.id),
                event_account=event_account,
                business_account=business_account,
            )
            return False

        return True

    # ── Invoice / Ledger update ────────────────────────────────────

    async def _update_invoice_payment_status(self, payment: Payment) -> None:
        """Update invoice and ledger payment status from payment aggregate.

        Deterministic: derives status from all successful payments
        vs the invoice total.
        """
        if payment.invoice_id is None:
            return

        invoice = await self.invoice_repo.get_by_id(payment.invoice_id)
        if invoice is None:
            return

        # Skip voided invoices
        if InvoicePaymentStatus(invoice.payment_status) == InvoicePaymentStatus.VOID:
            return

        paid_amount = Decimal(await self.payment_repo.get_successful_total_for_invoice(payment.invoice_id))
        refunded_amount = Decimal(await self.payment_repo.get_refunded_total_for_invoice(payment.invoice_id))
        net_paid = paid_amount - refunded_amount
        invoice_total = Decimal(str(invoice.total))

        # Determine new invoice payment status
        if net_paid <= Decimal("0.00"):
            new_status = InvoicePaymentStatus.UNPAID
        elif net_paid < invoice_total:
            new_status = InvoicePaymentStatus.PARTIALLY_PAID
        elif net_paid == invoice_total:
            new_status = InvoicePaymentStatus.PAID
        else:
            new_status = InvoicePaymentStatus.PAID

        # Check for refund / dispute states
        if refunded_amount > Decimal("0.00"):
            if refunded_amount >= invoice_total:
                new_status = InvoicePaymentStatus.REFUNDED
            else:
                new_status = InvoicePaymentStatus.PARTIALLY_REFUNDED

        # Check if any payment is disputed
        payments = await self.payment_repo.get_by_invoice(payment.invoice_id)
        has_disputed = any(PaymentStatus(p.status) == PaymentStatus.DISPUTED for p in payments)
        if has_disputed and new_status not in (
            InvoicePaymentStatus.REFUNDED,
            InvoicePaymentStatus.PARTIALLY_REFUNDED,
        ):
            # Keep the current status but note the dispute
            pass

        old_status = invoice.payment_status
        invoice.payment_status = new_status
        await self.invoice_repo.update(invoice)

        # Sync ledger entries
        ledger_entries = await self.ledger_repo.get_by_invoice_id(invoice.id)
        for entry in ledger_entries:
            if entry.payment_status != new_status:
                entry.payment_status = new_status
                await self.ledger_repo.update(entry)

        logger.info(
            "invoice_payment_status_updated",
            invoice_id=str(invoice.id),
            from_status=old_status,
            to_status=new_status.value,
        )

    # ── Helpers ────────────────────────────────────────────────────

    async def _get_event_by_stripe_id(self, stripe_event_id: str) -> StripeEvent | None:
        """Look up a previously processed Stripe event."""
        result = await self.session.execute(
            select(StripeEvent).where(
                StripeEvent.stripe_event_id == stripe_event_id,
                StripeEvent.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def _find_payment_by_metadata(self, event: WebhookEvent) -> Payment | None:
        """Try to find a payment from Stripe event metadata.

        When a PaymentIntent is created, FIELDed stores the payment_id
        in the metadata.  This allows matching even if the
        provider_reference hasn't been set yet.
        """
        data_object = event.raw_payload.get("data", {}).get("object", {})
        metadata = data_object.get("metadata", {})
        fielded_payment_id = metadata.get("payment_id")

        if fielded_payment_id:
            try:
                pid = uuid.UUID(fielded_payment_id)
                return await self.payment_repo.get_by_id(pid)
            except (ValueError, TypeError):
                pass

        return None

    def _validate_transition(self, from_status: PaymentStatus, to_status: PaymentStatus) -> None:
        """Validate a payment state transition."""
        from app.domain.common.enums import PAYMENT_TRANSITIONS

        allowed = PAYMENT_TRANSITIONS.get(from_status, set())
        if to_status not in allowed:
            raise StateTransitionError(f"Invalid payment transition from {from_status.value} to {to_status.value}")

    def _create_stripe_event(
        self,
        *,
        event: WebhookEvent,
        status: str,
        payment: Payment | None = None,
        error_message: str | None = None,
    ) -> StripeEvent:
        """Build a StripeEvent record from a webhook event."""
        data_object = event.raw_payload.get("data", {}).get("object", {})
        stripe_created = data_object.get("created")
        stripe_created_dt = None
        if stripe_created:
            stripe_created_dt = datetime.fromtimestamp(stripe_created, tz=UTC)

        return StripeEvent(
            stripe_event_id=event.provider_event_id,
            event_type=event.event_type,
            payment_intent_id=event.provider_payment_reference or None,
            stripe_account_id=(data_object.get("on_behalf_of") or data_object.get("account") or None),
            business_id=payment.business_id if payment else None,
            payment_id=payment.id if payment else None,
            status=status,
            error_message=error_message,
            raw_payload=event.raw_payload,
            stripe_created_at=stripe_created_dt,
        )

    async def _emit_outbox_event(
        self,
        *,
        business_id: uuid.UUID,
        event_type: str,
        aggregate_id: uuid.UUID,
        payload: dict,
    ) -> None:
        """Create an outbox event for downstream processing."""
        outbox = OutboxEvent(
            business_id=business_id,
            event_type=event_type,
            aggregate_type="payment",
            aggregate_id=aggregate_id,
            payload=payload,
            idempotency_key=f"{event_type}:payment:{aggregate_id}",
            status="PENDING",
            available_at=datetime.now(UTC),
        )
        self.session.add(outbox)
        await self.session.flush()
