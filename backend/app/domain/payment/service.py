"""Payment domain service.

Contains business logic for payment lifecycle management including:
- Payment initiation and provider interaction
- State machine transitions with audit
- Invoice balance updates
- Refund processing
- Webhook handling with idempotent processing
- Tenant isolation enforcement

AI may interpret/propose but cannot determine:
- payment amount
- authorization
- transaction state
- refund eligibility

All critical decisions flow through validated domain rules.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.payment.base import PaymentProvider, PaymentRequest, RefundRequest
from app.domain.common.enums import (
    PAYMENT_TRANSITIONS,
    InvoicePaymentStatus,
    PaymentStatus,
)
from app.domain.identity.models import Business
from app.domain.invoice.repository import InvoiceRepository
from app.domain.ledger.repository import LedgerRepository
from app.domain.outbox.models import OutboxEvent
from app.domain.payment.models import Payment, PaymentAttempt
from app.domain.payment.repository import PaymentRepository
from app.exceptions import (
    AuthorizationError,
    NotFoundError,
    StateTransitionError,
    ValidationError,
)
from app.logging import get_logger

logger = get_logger(__name__)


class PaymentService:
    """Payment lifecycle management.

    Orchestrates payment initiation, provider interaction,
    invoice balance updates, and refund processing.
    """

    def __init__(
        self,
        session: AsyncSession,
        payment_provider: PaymentProvider | None = None,
    ) -> None:
        self.session = session
        self.payment_repo = PaymentRepository(session)
        self.invoice_repo = InvoiceRepository(session)
        self.ledger_repo = LedgerRepository(session)
        self.payment_provider = payment_provider

    # --- Retrieval ---

    async def get_payment(self, payment_id: uuid.UUID) -> Payment:
        """Get a payment by ID."""
        payment = await self.payment_repo.get_by_id(payment_id)
        if payment is None:
            raise NotFoundError("Payment not found")
        return payment

    async def get_business_payment(self, payment_id: uuid.UUID, business_id: uuid.UUID) -> Payment:
        """Get a payment, verifying it belongs to the business."""
        payment = await self.get_payment(payment_id)
        if payment.business_id != business_id:
            raise AuthorizationError("Payment does not belong to this business")
        return payment

    async def get_customer_payment(self, payment_id: uuid.UUID, customer_id: uuid.UUID) -> Payment:
        """Get a payment, verifying customer ownership."""
        payment = await self.get_payment(payment_id)
        if payment.customer_id != customer_id:
            raise AuthorizationError("Not your payment")
        return payment

    async def list_business_payments(
        self,
        business_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Payment]:
        """List payments for a business."""
        return await self.payment_repo.get_by_business(business_id, status=status, limit=limit, offset=offset)

    async def list_customer_payments(
        self,
        customer_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Payment]:
        """List payments for a customer."""
        return await self.payment_repo.get_by_customer(customer_id, status=status, limit=limit, offset=offset)

    async def get_invoice_payments(self, invoice_id: uuid.UUID) -> list[Payment]:
        """List all payments for an invoice."""
        return await self.payment_repo.get_by_invoice(invoice_id)

    async def get_invoice_payment_status(self, invoice_id: uuid.UUID) -> dict:
        """Get payment status and balance for an invoice."""
        invoice = await self.invoice_repo.get_by_id(invoice_id)
        if invoice is None:
            raise NotFoundError("Invoice not found")

        paid_amount = Decimal(await self.payment_repo.get_successful_total_for_invoice(invoice_id))
        refunded_amount = Decimal(await self.payment_repo.get_refunded_total_for_invoice(invoice_id))
        net_paid = paid_amount - refunded_amount
        invoice_total = Decimal(str(invoice.total))
        outstanding = max(Decimal("0.00"), invoice_total - net_paid)
        payments = await self.payment_repo.get_by_invoice(invoice_id)

        return {
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "total": str(invoice_total),
            "currency": invoice.currency,
            "paid_amount": str(net_paid),
            "outstanding_amount": str(outstanding),
            "payment_status": invoice.payment_status,
            "payments": payments,
        }

    # --- Payment creation ---

    async def create_payment(
        self,
        *,
        business_id: uuid.UUID,
        customer_id: uuid.UUID,
        invoice_id: uuid.UUID,
        amount: str,
        currency: str,
        payment_method: str,
        idempotency_key: str,
        provider_name: str = "stub",
        notes: str | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> Payment:
        """Create a new payment for an invoice.

        Idempotent: if a payment with the same idempotency_key already
        exists, the existing payment is returned.
        """
        # Idempotency check
        existing = await self.payment_repo.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            logger.info(
                "payment_idempotency_hit",
                idempotency_key=idempotency_key,
                existing_payment_id=str(existing.id),
            )
            return existing

        # Validate invoice exists and belongs to this business
        invoice = await self.invoice_repo.get_by_id(invoice_id)
        if invoice is None:
            raise NotFoundError("Invoice not found")
        if invoice.business_id != business_id:
            raise AuthorizationError("Invoice does not belong to this business")
        if invoice.customer_id != customer_id:
            raise AuthorizationError("Invoice does not belong to this customer")

        # Validate amount
        try:
            amount_decimal = Decimal(amount)
        except (InvalidOperation, ValueError):
            raise ValidationError("Invalid amount format") from None
        if amount_decimal <= 0:
            raise ValidationError("Payment amount must be positive")

        # Validate currency matches invoice
        if currency != invoice.currency:
            raise ValidationError(f"Payment currency {currency} does not match invoice currency {invoice.currency}")

        # Calculate outstanding balance
        paid_amount = Decimal(await self.payment_repo.get_successful_total_for_invoice(invoice_id))
        refunded_amount = Decimal(await self.payment_repo.get_refunded_total_for_invoice(invoice_id))
        net_paid = paid_amount - refunded_amount
        invoice_total = Decimal(str(invoice.total))
        outstanding = invoice_total - net_paid

        if amount_decimal > outstanding:
            raise ValidationError(f"Payment amount {amount} exceeds outstanding balance {outstanding}")

        # Create payment
        # Inherit fee_evidence from the invoice (authoritative transaction
        # evidence — preserves the Commercial Policy fee through the
        # payment chain).
        payment = Payment(
            idempotency_key=idempotency_key,
            business_id=business_id,
            customer_id=customer_id,
            invoice_id=invoice_id,
            amount=str(amount_decimal),
            currency=currency,
            payment_method=payment_method,
            status=PaymentStatus.PENDING,
            provider=provider_name,
            fee_evidence=invoice.fee_evidence,
            notes=notes,
        )
        payment = await self.payment_repo.create(payment)

        logger.info(
            "payment_created",
            payment_id=str(payment.id),
            invoice_id=str(invoice_id),
            amount=amount,
            currency=currency,
            actor=str(actor_id) if actor_id else None,
        )

        return payment

    # --- Payment processing ---

    async def process_payment(
        self,
        payment: Payment,
    ) -> Payment:
        """Process a payment through the provider.

        Transitions: PENDING -> PROCESSING -> SUCCEEDED/FAILED
        Creates a PaymentAttempt for each provider interaction.
        """
        if PaymentStatus(payment.status) != PaymentStatus.PENDING:
            raise StateTransitionError(f"Cannot process payment in status {payment.status}")

        if self.payment_provider is None:
            raise ValidationError("No payment provider configured")

        # Transition to PROCESSING
        self._validate_transition(payment.status, PaymentStatus.PROCESSING)
        payment.status = PaymentStatus.PROCESSING
        await self.payment_repo.update(payment)

        # Create attempt
        # Query attempt count to avoid lazy loading relationship
        attempt_count_result = await self.session.execute(
            select(func.count()).select_from(PaymentAttempt).where(PaymentAttempt.payment_id == payment.id)
        )
        attempt_number = attempt_count_result.scalar_one() + 1

        attempt = PaymentAttempt(
            payment_id=payment.id,
            attempt_number=attempt_number,
            provider=payment.provider,
            amount=payment.amount,
            currency=payment.currency,
            requested_at=datetime.now(UTC),
            status="processing",
        )
        attempt = await self.payment_repo.create_attempt(attempt)

        # Call provider
        # Resolve Stripe Connect details for Direct Charges.
        stripe_account, application_fee = await self._resolve_stripe_connect(
            business_id=payment.business_id,
            amount=Decimal(payment.amount),
            currency=payment.currency,
            payment=payment,
        )

        request = PaymentRequest(
            amount=Decimal(payment.amount),
            currency=payment.currency,
            description="FIELDed payment for invoice",
            idempotency_key=payment.idempotency_key,
            metadata={"payment_id": str(payment.id)},
            stripe_account=stripe_account,
            application_fee_amount=application_fee,
        )
        result = await self.payment_provider.initiate_payment(request)

        now = datetime.now(UTC)
        attempt.completed_at = now

        # Extract the provider-level status from the raw response.
        # For synchronous providers (stub) this is "succeeded".
        # For async providers (Stripe) this may be "requires_payment_method"
        # or another non-terminal state indicating further action needed.
        provider_status = result.raw_response.get("status", "") if result.raw_response else ""

        # Statuses indicating the payment requires further confirmation
        # (e.g. Stripe PaymentIntent awaiting customer card confirmation).
        pending_confirmation = {
            "requires_payment_method",
            "requires_confirmation",
            "requires_action",
            "processing",
            "pending",
        }

        if result.success and provider_status in pending_confirmation:
            # Payment created but awaiting customer confirmation (e.g. Stripe
            # PaymentIntent).  Keep payment in PROCESSING — the webhook will
            # transition to SUCCEEDED/FAILED after the customer confirms.
            attempt.status = "processing"
            attempt.provider_reference = result.provider_reference
            attempt.provider_response = result.raw_response
            await self.payment_repo.update_attempt(attempt)

            payment.provider_reference = result.provider_reference
            await self.payment_repo.update(payment)

            logger.info(
                "payment_awaiting_confirmation",
                payment_id=str(payment.id),
                provider_reference=result.provider_reference,
                provider_status=provider_status,
            )
            return payment

        if result.success:
            attempt.status = "succeeded"
            attempt.provider_reference = result.provider_reference
            attempt.provider_response = result.raw_response

            # Transition payment to SUCCEEDED
            self._validate_transition(payment.status, PaymentStatus.SUCCEEDED)
            payment.status = PaymentStatus.SUCCEEDED
            payment.provider_reference = result.provider_reference
            payment.paid_at = now
            payment.provider_evidence = result.raw_response

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
                    "notification_title": "Payment received",
                    "notification_body": f"Payment of {payment.currency} {payment.amount} received successfully.",
                },
            )

            logger.info(
                "payment_succeeded",
                payment_id=str(payment.id),
                provider_reference=result.provider_reference,
            )
        else:
            attempt.status = "failed"
            attempt.error_code = result.error
            attempt.provider_response = result.raw_response

            # Transition payment to FAILED
            self._validate_transition(payment.status, PaymentStatus.FAILED)
            payment.status = PaymentStatus.FAILED
            payment.failure_code = result.error
            payment.failure_message = result.error

            # Emit outbox event
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
                    "error": result.error,
                    "notification_title": "Payment failed",
                    "notification_body": f"Payment of {payment.currency} {payment.amount} failed: {result.error}",
                },
            )

            logger.info(
                "payment_failed",
                payment_id=str(payment.id),
                error=result.error,
            )

        await self.payment_repo.update(payment)
        return payment

    # --- Webhook handling ---

    async def handle_webhook(
        self,
        *,
        provider_event_id: str,
        provider_payment_reference: str,
        event_type: str,
        status: str | None = None,
        amount: str | None = None,
    ) -> Payment | None:
        """Process a payment webhook event idempotently.

        Maps provider events to deterministic payment state transitions.
        Duplicate webhook deliveries are safely ignored.
        """
        # Find payment by provider reference
        payment = await self.payment_repo.get_by_provider_reference(provider_payment_reference)
        if payment is None:
            logger.warning(
                "payment_webhook_unknown_reference",
                provider_reference=provider_payment_reference,
            )
            return None

        current_status = PaymentStatus(payment.status)

        # Map provider event to payment status
        target_status = self._map_webhook_to_status(event_type, status)
        if target_status is None:
            logger.info(
                "payment_webhook_ignored",
                event_type=event_type,
                payment_id=str(payment.id),
            )
            return payment

        # Idempotent: if already in target state, skip
        if current_status == target_status:
            logger.info(
                "payment_webhook_idempotent_skip",
                payment_id=str(payment.id),
                current_status=current_status.value,
            )
            return payment

        # Validate transition
        try:
            self._validate_transition(payment.status, target_status)
        except StateTransitionError:
            logger.warning(
                "payment_webhook_invalid_transition",
                payment_id=str(payment.id),
                from_status=payment.status,
                to_status=target_status.value,
            )
            return payment

        # Apply transition
        now = datetime.now(UTC)
        payment.status = target_status

        if target_status == PaymentStatus.SUCCEEDED:
            payment.paid_at = now
            await self._update_invoice_payment_status(payment)
        elif target_status == PaymentStatus.FAILED:
            payment.failure_code = event_type
        elif target_status == PaymentStatus.EXPIRED or target_status == PaymentStatus.CANCELLED:
            pass

        await self.payment_repo.update(payment)

        logger.info(
            "payment_webhook_processed",
            payment_id=str(payment.id),
            event_type=event_type,
            new_status=target_status.value,
        )

        return payment

    # --- Refund ---

    async def refund_payment(
        self,
        payment: Payment,
        *,
        amount: str | None = None,
        reason: str | None = None,
        actor_id: uuid.UUID,
    ) -> Payment:
        """Process a refund for a succeeded payment.

        Supports full and partial refunds.
        AI does NOT determine refund eligibility — this is deterministic.
        """
        current_status = PaymentStatus(payment.status)

        # Only succeeded or partially_refunded payments can be refunded
        if current_status not in (
            PaymentStatus.SUCCEEDED,
            PaymentStatus.PARTIALLY_REFUNDED,
        ):
            raise StateTransitionError(f"Cannot refund payment in status {payment.status}")

        if self.payment_provider is None:
            raise ValidationError("No payment provider configured")

        # Calculate refund amount
        payment_amount = Decimal(payment.amount)
        already_refunded = Decimal(payment.refunded_amount)
        max_refundable = payment_amount - already_refunded

        if amount is not None:
            try:
                refund_amount = Decimal(amount)
            except (InvalidOperation, ValueError):
                raise ValidationError("Invalid refund amount format") from None
            if refund_amount <= 0:
                raise ValidationError("Refund amount must be positive")
            if refund_amount > max_refundable:
                raise ValidationError(f"Refund amount {refund_amount} exceeds refundable balance {max_refundable}")
        else:
            refund_amount = max_refundable

        # Process refund with provider
        # Resolve the business's Stripe account for Direct Charge refunds.
        stripe_account = await self._resolve_business_stripe_account(payment.business_id)

        refund_request = RefundRequest(
            provider_payment_reference=payment.provider_reference or "",
            amount=refund_amount,
            reason=reason,
            idempotency_key=f"refund-{payment.id}-{uuid.uuid4().hex[:8]}",
            stripe_account=stripe_account,
        )
        result = await self.payment_provider.refund(refund_request)

        now = datetime.now(UTC)

        if result.success:
            # Update refunded amount
            new_refunded = already_refunded + refund_amount
            payment.refunded_amount = str(new_refunded)
            payment.refunded_at = now
            payment.refund_provider_reference = result.provider_reference

            # Determine new status
            if new_refunded >= payment_amount:
                self._validate_transition(payment.status, PaymentStatus.REFUNDED)
                payment.status = PaymentStatus.REFUNDED
            else:
                self._validate_transition(payment.status, PaymentStatus.PARTIALLY_REFUNDED)
                payment.status = PaymentStatus.PARTIALLY_REFUNDED

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
                    "refund_amount": str(refund_amount),
                    "currency": payment.currency,
                    "status": payment.status,
                    "notification_title": "Refund processed",
                    "notification_body": f"Refund of {payment.currency} {refund_amount} has been processed.",
                },
            )

            logger.info(
                "payment_refunded",
                payment_id=str(payment.id),
                refund_amount=str(refund_amount),
                new_status=payment.status,
                actor=str(actor_id),
            )
        else:
            raise ValidationError(f"Refund failed: {result.error}")

        await self.payment_repo.update(payment)
        return payment

    # --- State machine ---

    async def cancel_payment(
        self,
        payment: Payment,
        *,
        actor_id: uuid.UUID,
    ) -> Payment:
        """Cancel a pending payment."""
        current_status = PaymentStatus(payment.status)
        if current_status != PaymentStatus.PENDING:
            raise StateTransitionError(f"Cannot cancel payment in status {payment.status}")

        self._validate_transition(payment.status, PaymentStatus.CANCELLED)
        payment.status = PaymentStatus.CANCELLED
        await self.payment_repo.update(payment)

        logger.info(
            "payment_cancelled",
            payment_id=str(payment.id),
            actor=str(actor_id),
        )
        return payment

    async def expire_payment(
        self,
        payment: Payment,
    ) -> Payment:
        """Expire a payment that has exceeded its time limit."""
        current_status = PaymentStatus(payment.status)
        if current_status not in (PaymentStatus.PENDING, PaymentStatus.PROCESSING):
            raise StateTransitionError(f"Cannot expire payment in status {payment.status}")

        self._validate_transition(payment.status, PaymentStatus.EXPIRED)
        payment.status = PaymentStatus.EXPIRED
        await self.payment_repo.update(payment)

        logger.info(
            "payment_expired",
            payment_id=str(payment.id),
        )
        return payment

    # --- Internal helpers ---

    async def _resolve_stripe_connect(
        self,
        *,
        business_id: uuid.UUID,
        amount: Decimal,
        currency: str,
        payment: Payment | None = None,
    ) -> tuple[str | None, int | None]:
        """Resolve Stripe Connect details for a Direct Charge.

        Returns (stripe_account_id, application_fee_amount) for the
        PaymentRequest.  When the configured provider is not Stripe or
        the business has no connected account, returns (None, None) so
        the provider falls back to its default behaviour (e.g. stub).

        The application_fee is derived from the authoritative Commercial
        Policy fee_evidence when available.  Falls back to
        Business.platform_fee_percent only when no fee_evidence exists.
        """
        if self.payment_provider is None:
            return None, None

        # Only relevant for the Stripe provider.
        if self.payment_provider.provider_name != "stripe":
            return None, None

        # Fetch the business to check Stripe Connect status.
        result = await self.session.execute(
            select(Business).where(
                Business.id == business_id,
                Business.deleted_at.is_(None),
            )
        )
        business = result.scalar_one_or_none()
        if business is None:
            return None, None

        stripe_account_id = business.stripe_account_id
        if not stripe_account_id:
            # No connected account — the provider will use the platform
            # account.  This is acceptable for stub/dev but should not
            # happen in production with real Stripe.
            return None, None

        # Validate the account can accept charges.
        from app.domain.common.enums import StripeConnectAccountStatus

        status = StripeConnectAccountStatus(business.stripe_connect_status)
        if status in (
            StripeConnectAccountStatus.NONE,
            StripeConnectAccountStatus.PENDING,
            StripeConnectAccountStatus.RESTRICTED,
            StripeConnectAccountStatus.CHARGES_DISABLED,
        ):
            raise ValidationError(
                f"Business {business_id} Stripe account cannot accept charges (status={status.value})."
            )

        if not business.stripe_charges_enabled:
            raise ValidationError(f"Business {business_id} Stripe charges are not enabled.")

        # Compute application fee.
        # Prefer the authoritative Commercial Policy fee_evidence
        # (stored on the payment or its invoice).  Fall back to
        # Business.platform_fee_percent only when no evidence exists.
        from decimal import Decimal as _Decimal

        application_fee: int | None = None
        fee_evidence = getattr(payment, "fee_evidence", None) if payment else None

        if fee_evidence and fee_evidence.get("platform_fee"):
            # Use the Commercial Policy platform fee
            platform_fee = _Decimal(fee_evidence["platform_fee"])
            if platform_fee > 0:
                zero_decimal_currencies = {"jpy", "krw", "vnd", "clp", "huf"}
                if currency.lower() in zero_decimal_currencies:
                    application_fee = int(platform_fee)
                else:
                    application_fee = int(platform_fee * 100)
        else:
            # Fallback: legacy platform_fee_percent
            fee_percent = _Decimal(str(business.platform_fee_percent))
            if fee_percent > 0:
                zero_decimal_currencies = {"jpy", "krw", "vnd", "clp", "huf"}
                if currency.lower() in zero_decimal_currencies:
                    amount_minor = int(amount)
                else:
                    amount_minor = int(amount * 100)
                application_fee = int(amount_minor * fee_percent / _Decimal("100"))
                application_fee = max(0, application_fee)

        return stripe_account_id, application_fee

    async def _resolve_business_stripe_account(self, business_id: uuid.UUID) -> str | None:
        """Return the business's stripe_account_id if the provider is Stripe."""
        if self.payment_provider is None:
            return None
        if self.payment_provider.provider_name != "stripe":
            return None
        result = await self.session.execute(
            select(Business.stripe_account_id).where(
                Business.id == business_id,
                Business.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def _emit_outbox_event(
        self,
        *,
        business_id: uuid.UUID,
        event_type: str,
        aggregate_id: uuid.UUID,
        payload: dict,
    ) -> None:
        """Create an outbox event in the same transaction."""
        event = OutboxEvent(
            business_id=business_id,
            event_type=event_type,
            aggregate_type="payment",
            aggregate_id=aggregate_id,
            payload=payload,
            idempotency_key=f"{event_type}:payment:{aggregate_id}",
            status="PENDING",
            available_at=datetime.now(UTC),
        )
        self.session.add(event)
        await self.session.flush()

    def _validate_transition(self, from_status: str, to_status: PaymentStatus) -> None:
        """Validate a payment state transition."""
        current = PaymentStatus(from_status)
        allowed = PAYMENT_TRANSITIONS.get(current, set())
        if to_status not in allowed:
            raise StateTransitionError(f"Invalid payment transition from {from_status} to {to_status.value}")

    def _map_webhook_to_status(self, event_type: str, provider_status: str | None) -> PaymentStatus | None:
        """Map a webhook event to a payment status.

        Returns None if the event should be ignored.
        """
        event_lower = event_type.lower()

        if "succeeded" in event_lower or provider_status == "succeeded":
            return PaymentStatus.SUCCEEDED
        if "failed" in event_lower or provider_status == "failed":
            return PaymentStatus.FAILED
        if "expired" in event_lower or provider_status == "expired":
            return PaymentStatus.EXPIRED
        if "cancelled" in event_lower or provider_status == "cancelled":
            return PaymentStatus.CANCELLED
        if "processing" in event_lower or provider_status == "processing":
            return PaymentStatus.PROCESSING

        return None

    async def _update_invoice_payment_status(self, payment: Payment) -> None:
        """Update the linked invoice's payment status based on payments.

        Deterministic: derives status from the aggregate of all
        successful payments vs the invoice total.
        """
        if payment.invoice_id is None:
            return

        invoice = await self.invoice_repo.get_by_id(payment.invoice_id)
        if invoice is None:
            return

        # Skip if invoice is voided
        if InvoicePaymentStatus(invoice.payment_status) == InvoicePaymentStatus.VOID:
            return

        # Calculate totals from payments
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
            # Overpaid (shouldn't happen but handle gracefully)
            new_status = InvoicePaymentStatus.PAID

        # Check for refund states
        if refunded_amount > Decimal("0.00"):
            if refunded_amount >= invoice_total:
                new_status = InvoicePaymentStatus.REFUNDED
            else:
                new_status = InvoicePaymentStatus.PARTIALLY_REFUNDED

        old_status = invoice.payment_status
        invoice.payment_status = new_status
        await self.invoice_repo.update(invoice)

        # Sync the linked ledger entry's payment status so ledger
        # summaries (paid/outstanding) reflect actual payments.
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
