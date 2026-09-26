"""Financial Integration Completion — fee evidence through the transaction chain.

Tests that the Commercial Policy fee flows through:
    Quote → Invoice → Payment → LedgerEntry
as immutable fee_evidence, and that:
- Historical evidence is preserved after policy changes
- Tenant isolation prevents cross-business fee leakage
- Zero-fee policies work correctly
- Stripe processing fees remain separate
- Idempotent retries don't create contradictory evidence
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.domain.commercial_policy.fee_calculator import FeeCalculator
from app.domain.commercial_policy.models import CommercialPolicy
from app.domain.commercial_policy.service import CommercialPolicyService
from app.domain.common.enums import (
    CommercialPolicyFeeType,
    CommercialPolicyScope,
    CommercialPolicyStatus,
    EnquiryStatus,
    QuoteStatus,
)
from app.domain.identity.models import Business, BusinessMember
from app.domain.services.models import ServiceOffer

# ── Helpers ────────────────────────────────────────────────────────


def _make_enquiry(*, business_id, customer_id, service_offer_id, subject="Need service", message="I need this service"):
    """Create an Enquiry with all required fields."""
    from app.domain.enquiry.models import Enquiry
    return Enquiry(
        reference=f"ENQ-{uuid.uuid4().hex[:8]}",
        business_id=business_id,
        customer_id=customer_id,
        service_offer_id=service_offer_id,
        subject=subject,
        message=message,
        status=EnquiryStatus.RECEIVED,
    )


async def _create_global_default_policy(db_session, *, fee_type="percentage", percentage="5.0000", fixed_amount="0.00"):
    """Create and activate a global default commercial policy."""
    policy = CommercialPolicy(
        name="Global Default",
        scope=CommercialPolicyScope.GLOBAL_DEFAULT,
        fee_type=fee_type,
        percentage=percentage,
        fixed_amount=fixed_amount,
        fixed_currency="GBP",
        effective_from=datetime(2020, 1, 1, tzinfo=UTC),
        status=CommercialPolicyStatus.ACTIVE,
        version=1,
    )
    db_session.add(policy)
    await db_session.flush()
    return policy


async def _create_business_policy(db_session, *, business_id, fee_type="percentage", percentage="10.0000"):
    """Create and activate a business-specific commercial policy."""
    policy = CommercialPolicy(
        name="Business Specific",
        scope=CommercialPolicyScope.BUSINESS_SPECIFIC,
        fee_type=fee_type,
        percentage=percentage,
        fixed_amount="0.00",
        fixed_currency="GBP",
        effective_from=datetime(2020, 1, 1, tzinfo=UTC),
        status=CommercialPolicyStatus.ACTIVE,
        version=1,
        business_id=business_id,
    )
    db_session.add(policy)
    await db_session.flush()
    return policy


async def _create_zero_fee_policy(db_session):
    """Create and activate a zero-fee global default policy."""
    policy = CommercialPolicy(
        name="Zero Fee Launch",
        scope=CommercialPolicyScope.GLOBAL_DEFAULT,
        fee_type=CommercialPolicyFeeType.ZERO,
        percentage="0.0000",
        fixed_amount="0.00",
        fixed_currency="GBP",
        effective_from=datetime(2020, 1, 1, tzinfo=UTC),
        status=CommercialPolicyStatus.ACTIVE,
        version=1,
    )
    db_session.add(policy)
    await db_session.flush()
    return policy


async def _create_business(db_session, user, *, name="Test Biz", slug="test-biz"):
    """Create a business with an owner member."""
    business = Business(name=name, slug=slug)
    db_session.add(business)
    await db_session.flush()

    member = BusinessMember(
        business_id=business.id,
        user_id=user.id,
        role="owner",
    )
    db_session.add(member)
    await db_session.flush()
    return business


async def _create_service_offer(db_session, business_id, *, amount="100.00"):
    """Create a fixed-price service offer."""
    offer = ServiceOffer(
        business_id=business_id,
        name="Test Service",
        slug=f"test-svc-{uuid.uuid4().hex[:6]}",
        description="A test service",
        pricing_model="fixed",
        pricing_config={"amount": amount, "currency": "GBP"},
        category_id=None,
    )
    db_session.add(offer)
    await db_session.flush()
    return offer


# ── Tests: FeeCalculator produces correct evidence dict ───────────


class TestFeeEvidenceDict:
    """Verify FeeResult.to_evidence_dict() produces complete evidence."""

    def test_percentage_fee_evidence_contains_all_fields(self):
        policy = CommercialPolicy(
            name="Test",
            scope="global_default",
            fee_type="percentage",
            percentage="5.0000",
            fixed_amount="0.00",
            effective_from=datetime(2024, 1, 1, tzinfo=UTC),
            status="active",
            version=1,
        )
        # Need an ID for the policy
        policy.id = uuid.uuid4()

        calc = FeeCalculator()
        result = calc.calculate(policy, amount=Decimal("100.00"), currency="GBP")
        evidence = result.to_evidence_dict()

        assert evidence["customer_amount"] == "100.00"
        assert evidence["platform_fee"] == "5.00"
        assert evidence["fee_type"] == "percentage"
        assert evidence["percentage_applied"] == "5.0000"
        assert evidence["business_proceeds"] == "95.00"
        assert evidence["currency"] == "GBP"
        assert evidence["policy_id"] == str(policy.id)
        assert evidence["policy_name"] == "Test"
        assert evidence["policy_scope"] == "global_default"
        assert evidence["policy_version"] == 1
        assert "stripe_note" in evidence
        assert "Stripe" in evidence["stripe_note"]

    def test_zero_fee_evidence(self):
        policy = CommercialPolicy(
            name="Zero",
            scope="global_default",
            fee_type="zero",
            percentage="0.0000",
            fixed_amount="0.00",
            effective_from=datetime(2024, 1, 1, tzinfo=UTC),
            status="active",
            version=1,
        )
        policy.id = uuid.uuid4()

        calc = FeeCalculator()
        result = calc.calculate(policy, amount=Decimal("50.00"), currency="GBP")
        evidence = result.to_evidence_dict()

        assert evidence["platform_fee"] == "0.00"
        assert evidence["business_proceeds"] == "50.00"
        assert evidence["fee_type"] == "zero"


# ── Tests: Quote receives fee_evidence ────────────────────────────


class TestQuoteFeeEvidence:
    """Verify Quote creation populates fee_evidence from CommercialPolicyService."""

    @pytest.mark.asyncio
    async def test_quote_receives_fee_evidence(self, db_session, test_user):
        """QuoteService.create_quote() stores fee_evidence on the Quote."""
        from app.domain.quote.service import QuoteService

        business = await _create_business(db_session, test_user, slug="quote-fee-biz")
        offer = await _create_service_offer(db_session, business.id)
        await _create_global_default_policy(db_session)

        # Create an enquiry
        enquiry = _make_enquiry(
            business_id=business.id,
            customer_id=test_user.id,
            service_offer_id=offer.id,
            subject="I need this service",
            message="I need this service please",
        )
        db_session.add(enquiry)
        await db_session.flush()

        # Create a quote
        svc = QuoteService(db_session)
        quote = await svc.create_quote(
            business_id=business.id,
            enquiry_id=enquiry.id,
        )

        assert quote.fee_evidence is not None
        assert "platform_fee" in quote.fee_evidence
        assert "policy_id" in quote.fee_evidence
        assert "policy_version" in quote.fee_evidence
        # 5% of 100.00 = 5.00
        assert Decimal(quote.fee_evidence["platform_fee"]) == Decimal("5.00")
        assert Decimal(quote.fee_evidence["business_proceeds"]) == Decimal("95.00")

    @pytest.mark.asyncio
    async def test_quote_fee_evidence_uses_business_specific_policy(self, db_session, test_user):
        """Business-specific policy takes precedence over global default."""
        from app.domain.quote.service import QuoteService

        business = await _create_business(db_session, test_user, slug="quote-biz-specific")
        offer = await _create_service_offer(db_session, business.id)
        await _create_global_default_policy(db_session, percentage="5.0000")
        await _create_business_policy(db_session, business_id=business.id, percentage="10.0000")

        enquiry = _make_enquiry(
            business_id=business.id,
            customer_id=test_user.id,
            service_offer_id=offer.id,
        )
        db_session.add(enquiry)
        await db_session.flush()

        svc = QuoteService(db_session)
        quote = await svc.create_quote(
            business_id=business.id,
            enquiry_id=enquiry.id,
        )

        assert quote.fee_evidence is not None
        # Business-specific 10% of 100 = 10.00
        assert Decimal(quote.fee_evidence["platform_fee"]) == Decimal("10.00")
        assert quote.fee_evidence["policy_scope"] == "business_specific"

    @pytest.mark.asyncio
    async def test_quote_zero_fee_policy(self, db_session, test_user):
        """Zero-fee policy produces platform_fee=0."""
        from app.domain.quote.service import QuoteService

        business = await _create_business(db_session, test_user, slug="quote-zero-fee")
        offer = await _create_service_offer(db_session, business.id)
        await _create_zero_fee_policy(db_session)

        enquiry = _make_enquiry(
            business_id=business.id,
            customer_id=test_user.id,
            service_offer_id=offer.id,
            subject="Free service",
            message="I need a free service",
        )
        db_session.add(enquiry)
        await db_session.flush()

        svc = QuoteService(db_session)
        quote = await svc.create_quote(
            business_id=business.id,
            enquiry_id=enquiry.id,
        )

        assert quote.fee_evidence is not None
        assert Decimal(quote.fee_evidence["platform_fee"]) == Decimal("0.00")
        assert Decimal(quote.fee_evidence["business_proceeds"]) == Decimal("100.00")


# ── Tests: Invoice + LedgerEntry inherit fee_evidence ─────────────


class TestInvoiceLedgerFeeEvidence:
    """Verify Invoice and LedgerEntry inherit fee_evidence from Quote."""

    @pytest.mark.asyncio
    async def test_invoice_inherits_quote_fee_evidence(self, db_session, test_user):
        """Service completion creates Invoice with the Quote's fee_evidence."""
        from app.domain.booking.service import BookingService
        from app.domain.common.enums import BookingStatus
        from app.domain.quote.service import QuoteService
        from app.domain.service_execution.service import ServiceExecutionService

        business = await _create_business(db_session, test_user, slug="invoice-fee-biz")
        offer = await _create_service_offer(db_session, business.id)
        await _create_global_default_policy(db_session)

        # Create enquiry + quote
        enquiry = _make_enquiry(
            business_id=business.id,
            customer_id=test_user.id,
            service_offer_id=offer.id,
        )
        db_session.add(enquiry)
        await db_session.flush()

        quote_svc = QuoteService(db_session)
        quote = await quote_svc.create_quote(business_id=business.id, enquiry_id=enquiry.id)
        original_evidence = dict(quote.fee_evidence)  # snapshot

        # Issue + accept quote
        await quote_svc.transition_quote(quote, QuoteStatus.ISSUED, actor="business")
        await quote_svc.transition_quote(quote, QuoteStatus.ACCEPTED, actor="customer")

        # Create booking
        booking_svc = BookingService(db_session)
        booking = await booking_svc.create_booking(
            customer_id=test_user.id,
            quote_id=quote.id,
            requested_at=datetime.now(UTC),
            notes="Test booking",
        )
        # Customer must accept before business can confirm
        await booking_svc.transition_booking(booking, BookingStatus.PROPOSED, actor="business")
        await booking_svc.transition_booking(booking, BookingStatus.ACCEPTED, actor="customer")
        await booking_svc.transition_booking(booking, BookingStatus.CONFIRMED, actor="business")

        # Create service execution
        exec_svc = ServiceExecutionService(db_session)
        execution = await exec_svc.create_from_booking(
            booking_id=booking.id,
            business_id=business.id,
        )

        # Complete service → creates Invoice + LedgerEntry
        await exec_svc.complete_service(execution, actor_id=test_user.id)

        # Verify Invoice has fee_evidence
        from app.domain.invoice.repository import InvoiceRepository

        invoice_repo = InvoiceRepository(db_session)
        invoice = await invoice_repo.get_by_service_execution_id(execution.id)
        assert invoice is not None
        assert invoice.fee_evidence is not None
        assert invoice.fee_evidence["policy_id"] == original_evidence["policy_id"]
        assert invoice.fee_evidence["platform_fee"] == original_evidence["platform_fee"]

        # Verify LedgerEntry has fee_evidence
        from app.domain.ledger.repository import LedgerRepository

        ledger_repo = LedgerRepository(db_session)
        entries = await ledger_repo.get_by_invoice_id(invoice.id)
        assert len(entries) > 0
        assert entries[0].fee_evidence is not None
        assert entries[0].fee_evidence["policy_id"] == original_evidence["policy_id"]

    @pytest.mark.asyncio
    async def test_historical_evidence_preserved_after_policy_change(
        self, db_session, test_user
    ):
        """Changing the policy after a Quote does NOT alter existing fee_evidence."""
        from app.domain.quote.service import QuoteService

        business = await _create_business(db_session, test_user, slug="hist-fee-biz")
        offer = await _create_service_offer(db_session, business.id)
        policy = await _create_global_default_policy(db_session, percentage="5.0000")

        enquiry = _make_enquiry(
            business_id=business.id,
            customer_id=test_user.id,
            service_offer_id=offer.id,
        )
        db_session.add(enquiry)
        await db_session.flush()

        # Create quote with 5% policy
        svc = QuoteService(db_session)
        quote = await svc.create_quote(business_id=business.id, enquiry_id=enquiry.id)
        original_fee = quote.fee_evidence["platform_fee"]
        original_policy_id = quote.fee_evidence["policy_id"]

        # Now change the policy to 20%
        policy.percentage = "20.0000"
        await db_session.flush()

        # Create a NEW enquiry + quote
        enquiry2 = _make_enquiry(
            business_id=business.id,
            customer_id=test_user.id,
            service_offer_id=offer.id,
            subject="Another enquiry",
            message="Another enquiry message",
        )
        db_session.add(enquiry2)
        await db_session.flush()

        quote2 = await svc.create_quote(business_id=business.id, enquiry_id=enquiry2.id)

        # Original quote's evidence is unchanged
        await db_session.refresh(quote)
        assert quote.fee_evidence["platform_fee"] == original_fee
        assert quote.fee_evidence["policy_id"] == original_policy_id

        # New quote uses the updated policy
        assert Decimal(quote2.fee_evidence["platform_fee"]) == Decimal("20.00")


# ── Tests: Payment inherits fee_evidence ──────────────────────────


async def _build_full_chain_to_invoice(db_session, business_owner, customer, *, biz_slug="chain-biz"):
    """Build the full Quote→Booking→Execution→Invoice chain.

    Returns (invoice, quote) for downstream assertions.
    """
    from app.domain.booking.service import BookingService
    from app.domain.common.enums import BookingStatus
    from app.domain.quote.service import QuoteService
    from app.domain.service_execution.service import ServiceExecutionService

    business = await _create_business(db_session, business_owner, slug=biz_slug)
    offer = await _create_service_offer(db_session, business.id)
    await _create_global_default_policy(db_session)

    # Enquiry
    enquiry = _make_enquiry(
        business_id=business.id,
        customer_id=customer.id,
        service_offer_id=offer.id,
    )
    db_session.add(enquiry)
    await db_session.flush()

    # Quote
    quote_svc = QuoteService(db_session)
    quote = await quote_svc.create_quote(business_id=business.id, enquiry_id=enquiry.id)
    await quote_svc.transition_quote(quote, QuoteStatus.ISSUED, actor="business")
    await quote_svc.transition_quote(quote, QuoteStatus.ACCEPTED, actor="customer")

    # Booking
    booking_svc = BookingService(db_session)
    booking = await booking_svc.create_booking(
        customer_id=customer.id,
        quote_id=quote.id,
        requested_at=datetime.now(UTC),
        notes="Test",
    )
    await booking_svc.transition_booking(booking, BookingStatus.PROPOSED, actor="business")
    await booking_svc.transition_booking(booking, BookingStatus.ACCEPTED, actor="customer")
    await booking_svc.transition_booking(booking, BookingStatus.CONFIRMED, actor="business")

    # Service Execution
    exec_svc = ServiceExecutionService(db_session)
    execution = await exec_svc.create_from_booking(booking_id=booking.id, business_id=business.id)
    await exec_svc.complete_service(execution, actor_id=business_owner.id)

    # Retrieve the invoice
    from app.domain.invoice.repository import InvoiceRepository
    invoice_repo = InvoiceRepository(db_session)
    invoice = await invoice_repo.get_by_service_execution_id(execution.id)
    return invoice, quote, business


class TestPaymentFeeEvidence:
    """Verify Payment inherits fee_evidence from Invoice."""

    @pytest.mark.asyncio
    async def test_payment_inherits_invoice_fee_evidence(self, db_session, test_user, second_user):
        """PaymentService.create_payment() copies fee_evidence from Invoice."""
        from app.domain.payment.service import PaymentService

        invoice, quote, business = await _build_full_chain_to_invoice(
            db_session, test_user, second_user, biz_slug="pay-fee-biz"
        )

        assert invoice.fee_evidence is not None, "Invoice should have fee_evidence from chain"

        svc = PaymentService(db_session)
        payment = await svc.create_payment(
            business_id=business.id,
            customer_id=second_user.id,
            invoice_id=invoice.id,
            amount=invoice.total,
            currency=invoice.currency,
            payment_method="card",
            idempotency_key=f"test-pay-{uuid.uuid4().hex[:8]}",
        )

        assert payment.fee_evidence is not None
        assert payment.fee_evidence["platform_fee"] == invoice.fee_evidence["platform_fee"]
        assert payment.fee_evidence["policy_id"] == invoice.fee_evidence["policy_id"]


# ── Tests: Tenant isolation ───────────────────────────────────────


class TestTenantIsolation:
    """Verify one business cannot use another business's commercial policy."""

    @pytest.mark.asyncio
    async def test_business_specific_policy_not_shared(self, db_session, test_user, second_user):
        """Business A's specific policy does not apply to Business B."""
        from app.domain.quote.service import QuoteService

        biz_a = await _create_business(db_session, test_user, slug="tenant-biz-a")
        biz_b = await _create_business(db_session, second_user, slug="tenant-biz-b")
        await _create_service_offer(db_session, biz_a.id)  # offer_a exists for symmetry
        offer_b = await _create_service_offer(db_session, biz_b.id)

        await _create_global_default_policy(db_session, percentage="5.0000")
        await _create_business_policy(db_session, business_id=biz_a.id, percentage="15.0000")

        # Create enquiry for business B
        enquiry_b = _make_enquiry(
            business_id=biz_b.id,
            customer_id=test_user.id,
            service_offer_id=offer_b.id,
            subject="Need service from B",
            message="I need service from business B",
        )
        db_session.add(enquiry_b)
        await db_session.flush()

        # Quote for business B should use global default (5%), NOT biz A's (15%)
        svc = QuoteService(db_session)
        quote_b = await svc.create_quote(business_id=biz_b.id, enquiry_id=enquiry_b.id)

        assert quote_b.fee_evidence is not None
        # Should be 5% (global default), not 15% (biz A's policy)
        assert Decimal(quote_b.fee_evidence["platform_fee"]) == Decimal("5.00")
        assert quote_b.fee_evidence["policy_scope"] == "global_default"


# ── Tests: Idempotency ───────────────────────────────────────────


class TestFeeIdempotency:
    """Verify retried operations don't create contradictory fee evidence."""

    @pytest.mark.asyncio
    async def test_duplicate_payment_creation_preserves_evidence(self, db_session, test_user, second_user):
        """Creating a payment with the same idempotency_key returns the original."""
        from app.domain.payment.service import PaymentService

        invoice, quote, business = await _build_full_chain_to_invoice(
            db_session, test_user, second_user, biz_slug="idem-fee-biz"
        )

        svc = PaymentService(db_session)
        key = f"idem-test-{uuid.uuid4().hex[:8]}"

        pay1 = await svc.create_payment(
            business_id=business.id,
            customer_id=second_user.id,
            invoice_id=invoice.id,
            amount=invoice.total,
            currency=invoice.currency,
            payment_method="card",
            idempotency_key=key,
        )

        # Retry with same key
        pay2 = await svc.create_payment(
            business_id=business.id,
            customer_id=second_user.id,
            invoice_id=invoice.id,
            amount=invoice.total,
            currency=invoice.currency,
            payment_method="card",
            idempotency_key=key,
        )

        assert pay1.id == pay2.id
        assert pay1.fee_evidence == pay2.fee_evidence


# ── Tests: Stripe processing fees remain separate ─────────────────


class TestStripeFeeSeparation:
    """Verify Stripe processing fees are NOT merged into the platform fee."""

    def test_fee_evidence_contains_stripe_note(self):
        """FeeResult.to_evidence_dict() explicitly notes Stripe fees are separate."""
        policy = CommercialPolicy(
            name="Test",
            scope="global_default",
            fee_type="percentage",
            percentage="5.0000",
            fixed_amount="0.00",
            effective_from=datetime(2024, 1, 1, tzinfo=UTC),
            status="active",
            version=1,
        )
        policy.id = uuid.uuid4()

        calc = FeeCalculator()
        result = calc.calculate(policy, amount=Decimal("100.00"), currency="GBP")
        evidence = result.to_evidence_dict()

        assert "stripe_note" in evidence
        assert "separately" in evidence["stripe_note"].lower()
        # Platform fee is only the FIELDed fee
        assert evidence["platform_fee"] == "5.00"
        assert evidence["business_proceeds"] == "95.00"


# ── Tests: CommercialPolicyService integration ────────────────────


class TestCommercialPolicyServiceIntegration:
    """Test the service layer integration, not just isolated FeeCalculator."""

    @pytest.mark.asyncio
    async def test_calculate_fee_with_no_policy_raises(self, db_session, test_user):
        """If no policy exists at all, calculate_fee raises ValidationError."""
        from app.exceptions import ValidationError

        business = await _create_business(db_session, test_user, slug="no-policy-biz")
        svc = CommercialPolicyService(db_session)

        with pytest.raises(ValidationError, match="No commercial policy"):
            await svc.calculate_fee(
                business_id=business.id,
                amount=Decimal("100.00"),
                currency="GBP",
            )

    @pytest.mark.asyncio
    async def test_calculate_fee_deterministic(self, db_session, test_user):
        """Same input → same output, every time."""
        business = await _create_business(db_session, test_user, slug="determ-biz")
        await _create_global_default_policy(db_session, percentage="7.5000")

        svc = CommercialPolicyService(db_session)
        r1 = await svc.calculate_fee(business_id=business.id, amount=Decimal("200.00"), currency="GBP")
        r2 = await svc.calculate_fee(business_id=business.id, amount=Decimal("200.00"), currency="GBP")

        assert r1.platform_fee == r2.platform_fee
        assert r1.business_proceeds == r2.business_proceeds
        assert r1.policy_id == r2.policy_id
        assert r1.to_evidence_dict() == r2.to_evidence_dict()

    @pytest.mark.asyncio
    async def test_combined_fee_type(self, db_session, test_user):
        """Combined fee (percentage + fixed) calculates correctly."""
        business = await _create_business(db_session, test_user, slug="combined-biz")

        policy = CommercialPolicy(
            name="Combined Fee",
            scope=CommercialPolicyScope.GLOBAL_DEFAULT,
            fee_type=CommercialPolicyFeeType.COMBINED,
            percentage="3.0000",
            fixed_amount="1.50",
            fixed_currency="GBP",
            effective_from=datetime(2020, 1, 1, tzinfo=UTC),
            status=CommercialPolicyStatus.ACTIVE,
            version=1,
        )
        db_session.add(policy)
        await db_session.flush()

        svc = CommercialPolicyService(db_session)
        result = await svc.calculate_fee(
            business_id=business.id,
            amount=Decimal("100.00"),
            currency="GBP",
        )

        # 3% of 100 = 3.00 + 1.50 fixed = 4.50
        assert result.platform_fee == Decimal("4.50")
        assert result.business_proceeds == Decimal("95.50")
        assert result.fee_type == "combined"

    @pytest.mark.asyncio
    async def test_fixed_fee_type(self, db_session, test_user):
        """Fixed fee ignores percentage and applies flat amount."""
        business = await _create_business(db_session, test_user, slug="fixed-biz")

        policy = CommercialPolicy(
            name="Fixed Fee",
            scope=CommercialPolicyScope.GLOBAL_DEFAULT,
            fee_type=CommercialPolicyFeeType.FIXED,
            percentage="0.0000",
            fixed_amount="2.99",
            fixed_currency="GBP",
            effective_from=datetime(2020, 1, 1, tzinfo=UTC),
            status=CommercialPolicyStatus.ACTIVE,
            version=1,
        )
        db_session.add(policy)
        await db_session.flush()

        svc = CommercialPolicyService(db_session)
        result = await svc.calculate_fee(
            business_id=business.id,
            amount=Decimal("100.00"),
            currency="GBP",
        )

        assert result.platform_fee == Decimal("2.99")
        assert result.business_proceeds == Decimal("97.01")

    @pytest.mark.asyncio
    async def test_fee_capped_at_amount(self, db_session, test_user):
        """Fee cannot exceed the transaction amount."""
        business = await _create_business(db_session, test_user, slug="cap-biz")

        policy = CommercialPolicy(
            name="Huge Fixed Fee",
            scope=CommercialPolicyScope.GLOBAL_DEFAULT,
            fee_type=CommercialPolicyFeeType.FIXED,
            percentage="0.0000",
            fixed_amount="999.99",
            fixed_currency="GBP",
            effective_from=datetime(2020, 1, 1, tzinfo=UTC),
            status=CommercialPolicyStatus.ACTIVE,
            version=1,
        )
        db_session.add(policy)
        await db_session.flush()

        svc = CommercialPolicyService(db_session)
        result = await svc.calculate_fee(
            business_id=business.id,
            amount=Decimal("5.00"),
            currency="GBP",
        )

        # Fee capped at transaction amount
        assert result.platform_fee == Decimal("5.00")
        assert result.business_proceeds == Decimal("0.00")
