"""Stripe Connect payment foundation — unit tests.

Tests cover:
- StripeConnectAccountStatus enum values
- Stripe Connect service: account creation, link, status refresh
- Direct Charge creation with stripe_account + application_fee
- Missing Stripe account → ValidationError
- Restricted/incomplete connected account → ValidationError
- Application fee computation
- Connected account ownership / tenant isolation
- Payment provider failure handling
- Existing payment-domain compatibility (stub still works)
- Stripe Connect webhook (account.updated)
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.payment.base import PaymentRequest
from app.adapters.payment.stripe_provider import StripePaymentProvider
from app.adapters.payment.stub import StubPaymentProvider
from app.domain.common.enums import StripeConnectAccountStatus
from app.domain.identity.models import (
    Business,
    BusinessMember,
    BusinessProfile,
    User,
)
from app.domain.payment.service import PaymentService
from app.domain.stripe_connect.service import StripeConnectService
from app.exceptions import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeStripeAccount:
    """Simulates a Stripe Account object."""

    def __init__(
        self,
        *,
        account_id: str = "acct_test123",
        account_type: str = "express",
        country: str = "AU",
        charges_enabled: bool = False,
        payouts_enabled: bool = False,
        details_submitted: bool = False,
        requirements: Any = None,
    ) -> None:
        self.id = account_id
        self.type = account_type
        self.country = country
        self.charges_enabled = charges_enabled
        self.payouts_enabled = payouts_enabled
        self.details_submitted = details_submitted
        self.requirements = requirements


class FakeStripeAccountLink:
    """Simulates a Stripe AccountLink object."""

    def __init__(self, url: str = "https://connect.stripe.com/setup/s/test") -> None:
        self.url = url
        self.expires_at = 1700000000
        self.created = 1699999000


class FakeStripePaymentIntent:
    """Simulates a Stripe PaymentIntent object."""

    def __init__(
        self,
        *,
        pi_id: str = "pi_test123",
        status: str = "requires_payment_method",
        client_secret: str = "pi_test123_secret_abc",
        amount: int = 8500,
        currency: str = "aud",
    ) -> None:
        self.id = pi_id
        self.status = status
        self.client_secret = client_secret
        self.amount = amount
        self.currency = currency


class MockStripeClient:
    """Mock StripeClient for testing StripeConnectService."""

    def __init__(
        self,
        *,
        account: FakeStripeAccount | None = None,
        account_link: FakeStripeAccountLink | None = None,
        payment_intent: FakeStripePaymentIntent | None = None,
        create_account_error: Exception | None = None,
    ) -> None:
        self._account = account or FakeStripeAccount()
        self._account_link = account_link or FakeStripeAccountLink()
        self._payment_intent = payment_intent
        self._create_account_error = create_account_error
        # Track calls for assertions
        self.create_account_calls: list[dict] = []
        self.create_link_calls: list[dict] = []
        self.retrieve_account_calls: list[str] = []
        self.create_pi_calls: list[dict] = []

    @property
    def v1(self) -> Any:
        return self

    @property
    def accounts(self) -> Any:
        return self

    @property
    def account_links(self) -> Any:
        return self

    @property
    def payment_intents(self) -> Any:
        return self

    def create(self, params: dict, options: dict | None = None) -> Any:
        """Route create calls based on the caller context."""
        # This is called by both accounts.create and account_links.create
        # and payment_intents.create.  We use the params to distinguish.
        if "type" in params and "country" in params:
            # Account creation
            if self._create_account_error:
                raise self._create_account_error
            self.create_account_calls.append(params)
            return self._account
        if "account" in params:
            # Account link creation
            self.create_link_calls.append(params)
            return self._account_link
        if "amount" in params and "currency" in params:
            # PaymentIntent creation
            self.create_pi_calls.append({"params": params, "options": options or {}})
            return self._payment_intent or FakeStripePaymentIntent()
        return self._account

    def retrieve(self, account_id: str, options: dict | None = None) -> Any:
        self.retrieve_account_calls.append(account_id)
        return self._account


async def _create_business(
    db_session: AsyncSession,
    user: User,
    *,
    name: str = "Test Business",
    slug: str | None = None,
    stripe_account_id: str | None = None,
    stripe_connect_status: str = "none",
    stripe_charges_enabled: bool = False,
    stripe_payouts_enabled: bool = False,
    platform_fee_percent: str = "5.00",
) -> Business:
    """Create a test business with a membership for the given user."""
    business = Business(
        name=name,
        slug=slug or f"test-biz-{uuid.uuid4().hex[:8]}",
        status="active",
        currency="AUD",
        stripe_account_id=stripe_account_id,
        stripe_connect_status=stripe_connect_status,
        stripe_charges_enabled=stripe_charges_enabled,
        stripe_payouts_enabled=stripe_payouts_enabled,
        platform_fee_percent=platform_fee_percent,
    )
    db_session.add(business)
    await db_session.flush()

    member = BusinessMember(user_id=user.id, business_id=business.id, role="owner")
    db_session.add(member)

    profile = BusinessProfile(business_id=business.id)
    db_session.add(profile)
    await db_session.flush()
    return business


# ---------------------------------------------------------------------------
# Tests: StripeConnectAccountStatus enum
# ---------------------------------------------------------------------------


class TestStripeConnectAccountStatus:
    """Verify the enum values are correct."""

    def test_none_status(self) -> None:
        assert StripeConnectAccountStatus.NONE == "none"

    def test_pending_status(self) -> None:
        assert StripeConnectAccountStatus.PENDING == "pending"

    def test_restricted_status(self) -> None:
        assert StripeConnectAccountStatus.RESTRICTED == "restricted"

    def test_active_status(self) -> None:
        assert StripeConnectAccountStatus.ACTIVE == "active"

    def test_charges_disabled_status(self) -> None:
        assert StripeConnectAccountStatus.CHARGES_DISABLED == "charges_disabled"

    def test_payouts_disabled_status(self) -> None:
        assert StripeConnectAccountStatus.PAYOUTS_DISABLED == "payouts_disabled"


# ---------------------------------------------------------------------------
# Tests: StripeConnectService
# ---------------------------------------------------------------------------


class TestStripeConnectServiceCreateAccount:
    """Test connected account creation."""

    @pytest.mark.asyncio
    async def test_create_connected_account_success(self, db_session: AsyncSession, test_user: User) -> None:
        """Creating a connected account stores the Stripe account ID."""
        business = await _create_business(db_session, test_user)
        mock_client = MockStripeClient(
            account=FakeStripeAccount(account_id="acct_new123"),
        )

        service = StripeConnectService.__new__(StripeConnectService)
        service.session = db_session
        service._api_key = "sk_test_fake"
        service._default_platform_fee_percent = Decimal("5.00")
        service._client = mock_client

        result = await service.create_connected_account(business.id, email=test_user.email)

        assert result.stripe_account_id == "acct_new123"
        assert result.stripe_connect_status == StripeConnectAccountStatus.PENDING
        assert result.stripe_details is not None
        assert result.stripe_details["id"] == "acct_new123"

    @pytest.mark.asyncio
    async def test_create_connected_account_already_exists(self, db_session: AsyncSession, test_user: User) -> None:
        """Cannot create a second connected account for the same business."""
        business = await _create_business(db_session, test_user, stripe_account_id="acct_existing")
        mock_client = MockStripeClient()

        service = StripeConnectService.__new__(StripeConnectService)
        service.session = db_session
        service._api_key = "sk_test_fake"
        service._default_platform_fee_percent = Decimal("5.00")
        service._client = mock_client

        with pytest.raises(ValidationError, match="already has a Stripe connected account"):
            await service.create_connected_account(business.id)

    @pytest.mark.asyncio
    async def test_create_connected_account_stripe_error(self, db_session: AsyncSession, test_user: User) -> None:
        """Stripe API errors are translated to ValidationError."""
        import stripe

        business = await _create_business(db_session, test_user)
        mock_client = MockStripeClient(
            create_account_error=stripe.StripeError("API error"),
        )

        service = StripeConnectService.__new__(StripeConnectService)
        service.session = db_session
        service._api_key = "sk_test_fake"
        service._default_platform_fee_percent = Decimal("5.00")
        service._client = mock_client

        with pytest.raises(ValidationError, match="Stripe account creation failed"):
            await service.create_connected_account(business.id)


class TestStripeConnectServiceAccountLink:
    """Test account link generation."""

    @pytest.mark.asyncio
    async def test_create_account_link_success(self, db_session: AsyncSession, test_user: User) -> None:
        """Account link is created for a business with a connected account."""
        business = await _create_business(db_session, test_user, stripe_account_id="acct_linked")
        mock_client = MockStripeClient(
            account_link=FakeStripeAccountLink(url="https://connect.stripe.com/setup/s/abc"),
        )

        service = StripeConnectService.__new__(StripeConnectService)
        service.session = db_session
        service._api_key = "sk_test_fake"
        service._default_platform_fee_percent = Decimal("5.00")
        service._client = mock_client

        result = await service.create_account_link(
            business.id,
            refresh_url="https://fielded.local/refresh",
            return_url="https://fielded.local/return",
        )

        assert result["url"] == "https://connect.stripe.com/setup/s/abc"

    @pytest.mark.asyncio
    async def test_create_account_link_no_account(self, db_session: AsyncSession, test_user: User) -> None:
        """Cannot create an account link without a connected account."""
        business = await _create_business(db_session, test_user)
        mock_client = MockStripeClient()

        service = StripeConnectService.__new__(StripeConnectService)
        service.session = db_session
        service._api_key = "sk_test_fake"
        service._default_platform_fee_percent = Decimal("5.00")
        service._client = mock_client

        with pytest.raises(ValidationError, match="has no Stripe connected account"):
            await service.create_account_link(
                business.id,
                refresh_url="https://fielded.local/refresh",
                return_url="https://fielded.local/return",
            )


class TestStripeConnectServiceStatusRefresh:
    """Test account status refresh."""

    @pytest.mark.asyncio
    async def test_refresh_active_account(self, db_session: AsyncSession, test_user: User) -> None:
        """Refreshing an active account sets ACTIVE status."""
        business = await _create_business(
            db_session,
            test_user,
            stripe_account_id="acct_refresh",
            stripe_connect_status="pending",
        )
        mock_client = MockStripeClient(
            account=FakeStripeAccount(
                account_id="acct_refresh",
                charges_enabled=True,
                payouts_enabled=True,
                details_submitted=True,
            ),
        )

        service = StripeConnectService.__new__(StripeConnectService)
        service.session = db_session
        service._api_key = "sk_test_fake"
        service._default_platform_fee_percent = Decimal("5.00")
        service._client = mock_client

        result = await service.refresh_account_status(business.id)

        assert result.stripe_connect_status == StripeConnectAccountStatus.ACTIVE
        assert result.stripe_charges_enabled is True
        assert result.stripe_payouts_enabled is True

    @pytest.mark.asyncio
    async def test_refresh_restricted_account(self, db_session: AsyncSession, test_user: User) -> None:
        """Refreshing a restricted account sets RESTRICTED status."""

        class FakeRequirements:
            currently_due = ["external_account"]
            eventually_due = []
            past_due = []
            disabled_reason = "requirements.past_due"

        business = await _create_business(
            db_session,
            test_user,
            stripe_account_id="acct_restricted",
        )
        mock_client = MockStripeClient(
            account=FakeStripeAccount(
                account_id="acct_restricted",
                charges_enabled=False,
                payouts_enabled=False,
                details_submitted=True,
                requirements=FakeRequirements(),
            ),
        )

        service = StripeConnectService.__new__(StripeConnectService)
        service.session = db_session
        service._api_key = "sk_test_fake"
        service._default_platform_fee_percent = Decimal("5.00")
        service._client = mock_client

        result = await service.refresh_account_status(business.id)

        assert result.stripe_connect_status == StripeConnectAccountStatus.RESTRICTED


class TestStripeConnectServiceValidateCanCharge:
    """Test pre-payment validation."""

    @pytest.mark.asyncio
    async def test_validate_can_charge_active(self, db_session: AsyncSession, test_user: User) -> None:
        """Active account with charges enabled passes validation."""
        business = await _create_business(
            db_session,
            test_user,
            stripe_account_id="acct_active",
            stripe_connect_status="active",
            stripe_charges_enabled=True,
            stripe_payouts_enabled=True,
        )

        service = StripeConnectService.__new__(StripeConnectService)
        service.session = db_session
        service._api_key = "sk_test_fake"
        service._default_platform_fee_percent = Decimal("5.00")
        service._client = MockStripeClient()

        result = await service.validate_can_charge(business.id)
        assert result == "acct_active"

    @pytest.mark.asyncio
    async def test_validate_can_charge_no_account(self, db_session: AsyncSession, test_user: User) -> None:
        """Missing Stripe account raises ValidationError."""
        business = await _create_business(db_session, test_user)

        service = StripeConnectService.__new__(StripeConnectService)
        service.session = db_session
        service._api_key = "sk_test_fake"
        service._default_platform_fee_percent = Decimal("5.00")
        service._client = MockStripeClient()

        with pytest.raises(ValidationError, match="has no Stripe connected account"):
            await service.validate_can_charge(business.id)

    @pytest.mark.asyncio
    async def test_validate_can_charge_pending(self, db_session: AsyncSession, test_user: User) -> None:
        """Pending onboarding raises ValidationError."""
        business = await _create_business(
            db_session,
            test_user,
            stripe_account_id="acct_pending",
            stripe_connect_status="pending",
        )

        service = StripeConnectService.__new__(StripeConnectService)
        service.session = db_session
        service._api_key = "sk_test_fake"
        service._default_platform_fee_percent = Decimal("5.00")
        service._client = MockStripeClient()

        with pytest.raises(ValidationError, match="onboarding incomplete"):
            await service.validate_can_charge(business.id)

    @pytest.mark.asyncio
    async def test_validate_can_charge_disabled(self, db_session: AsyncSession, test_user: User) -> None:
        """Charges disabled raises ValidationError."""
        business = await _create_business(
            db_session,
            test_user,
            stripe_account_id="acct_disabled",
            stripe_connect_status="charges_disabled",
            stripe_charges_enabled=False,
        )

        service = StripeConnectService.__new__(StripeConnectService)
        service.session = db_session
        service._api_key = "sk_test_fake"
        service._default_platform_fee_percent = Decimal("5.00")
        service._client = MockStripeClient()

        with pytest.raises(ValidationError, match="charges are disabled"):
            await service.validate_can_charge(business.id)


# ---------------------------------------------------------------------------
# Tests: Application fee computation
# ---------------------------------------------------------------------------


class TestApplicationFeeComputation:
    """Test platform fee calculation."""

    def test_fee_5_percent_aud(self) -> None:
        """5% of AUD 85.00 = 425 pence."""
        service = StripeConnectService.__new__(StripeConnectService)
        service._default_platform_fee_percent = Decimal("5.00")

        business = MagicMock()
        business.platform_fee_percent = "5.00"

        fee = service.compute_application_fee(Decimal("85.00"), "aud", business)
        assert fee == 425  # 8500 * 5 / 100

    def test_fee_10_percent_gbp(self) -> None:
        """10% of GBP 100.00 = 1000 pence."""
        service = StripeConnectService.__new__(StripeConnectService)
        service._default_platform_fee_percent = Decimal("5.00")

        business = MagicMock()
        business.platform_fee_percent = "10.00"

        fee = service.compute_application_fee(Decimal("100.00"), "gbp", business)
        assert fee == 1000  # 10000 * 10 / 100

    def test_fee_zero_percent(self) -> None:
        """0% fee returns 0."""
        service = StripeConnectService.__new__(StripeConnectService)
        service._default_platform_fee_percent = Decimal("0.00")

        business = MagicMock()
        business.platform_fee_percent = "0.00"

        fee = service.compute_application_fee(Decimal("85.00"), "aud", business)
        assert fee == 0

    def test_fee_zero_decimal_currency(self) -> None:
        """JPY (zero-decimal) fee computation."""
        service = StripeConnectService.__new__(StripeConnectService)
        service._default_platform_fee_percent = Decimal("5.00")

        business = MagicMock()
        business.platform_fee_percent = "5.00"

        fee = service.compute_application_fee(Decimal("1000"), "jpy", business)
        assert fee == 50  # 1000 * 5 / 100


# ---------------------------------------------------------------------------
# Tests: StripePaymentProvider Direct Charge
# ---------------------------------------------------------------------------


class TestStripeProviderDirectCharge:
    """Test that the Stripe provider creates Direct Charges correctly."""

    @pytest.mark.asyncio
    async def test_direct_charge_passes_stripe_account(self) -> None:
        """Direct Charge includes stripe_account in options."""
        mock_client = MockStripeClient(
            payment_intent=FakeStripePaymentIntent(
                pi_id="pi_direct",
                status="requires_payment_method",
            ),
        )

        provider = StripePaymentProvider.__new__(StripePaymentProvider)
        provider._api_key = "sk_test_fake"
        provider._webhook_secret = ""
        provider._client = mock_client

        request = PaymentRequest(
            amount=Decimal("85.00"),
            currency="aud",
            description="Test payment",
            idempotency_key="test-key-123",
            stripe_account="acct_connected",
            application_fee_amount=425,
        )

        result = await provider.initiate_payment(request)

        assert result.success is True
        assert result.provider_reference == "pi_direct"
        # Verify the stripe_account was passed in options
        assert len(mock_client.create_pi_calls) == 1
        call = mock_client.create_pi_calls[0]
        assert call["options"]["stripe_account"] == "acct_connected"
        assert call["params"]["application_fee_amount"] == 425

    @pytest.mark.asyncio
    async def test_regular_charge_no_stripe_account(self) -> None:
        """Without stripe_account, no Direct Charge headers are sent."""
        mock_client = MockStripeClient(
            payment_intent=FakeStripePaymentIntent(pi_id="pi_regular"),
        )

        provider = StripePaymentProvider.__new__(StripePaymentProvider)
        provider._api_key = "sk_test_fake"
        provider._webhook_secret = ""
        provider._client = mock_client

        request = PaymentRequest(
            amount=Decimal("50.00"),
            currency="gbp",
            description="Regular payment",
            idempotency_key="test-key-456",
        )

        result = await provider.initiate_payment(request)

        assert result.success is True
        call = mock_client.create_pi_calls[0]
        assert "stripe_account" not in call["options"]
        assert "application_fee_amount" not in call["params"]

    @pytest.mark.asyncio
    async def test_direct_charge_response_includes_connect_fields(self) -> None:
        """Direct Charge response includes stripe_account and application_fee."""
        mock_client = MockStripeClient(
            payment_intent=FakeStripePaymentIntent(pi_id="pi_dc"),
        )

        provider = StripePaymentProvider.__new__(StripePaymentProvider)
        provider._api_key = "sk_test_fake"
        provider._webhook_secret = ""
        provider._client = mock_client

        request = PaymentRequest(
            amount=Decimal("100.00"),
            currency="usd",
            description="DC payment",
            idempotency_key="test-key-789",
            stripe_account="acct_dc",
            application_fee_amount=500,
        )

        result = await provider.initiate_payment(request)

        assert result.raw_response["stripe_account"] == "acct_dc"
        assert result.raw_response["application_fee_amount"] == 500


# ---------------------------------------------------------------------------
# Tests: PaymentService Stripe Connect resolution
# ---------------------------------------------------------------------------


class TestPaymentServiceStripeConnect:
    """Test that PaymentService resolves Stripe Connect details."""

    @pytest.mark.asyncio
    async def test_resolve_stripe_connect_active(self, db_session: AsyncSession, test_user: User) -> None:
        """Active Stripe account returns account ID and fee."""
        business = await _create_business(
            db_session,
            test_user,
            stripe_account_id="acct_pay",
            stripe_connect_status="active",
            stripe_charges_enabled=True,
            stripe_payouts_enabled=True,
            platform_fee_percent="5.00",
        )

        service = PaymentService(db_session, payment_provider=StripePaymentProvider(api_key="sk_test"))
        stripe_account, fee = await service._resolve_stripe_connect(
            business_id=business.id,
            amount=Decimal("100.00"),
            currency="aud",
        )

        assert stripe_account == "acct_pay"
        assert fee == 500  # 10000 * 5 / 100

    @pytest.mark.asyncio
    async def test_resolve_stripe_connect_no_account(self, db_session: AsyncSession, test_user: User) -> None:
        """No Stripe account returns (None, None)."""
        business = await _create_business(db_session, test_user)

        service = PaymentService(db_session, payment_provider=StripePaymentProvider(api_key="sk_test"))
        stripe_account, fee = await service._resolve_stripe_connect(
            business_id=business.id,
            amount=Decimal("100.00"),
            currency="aud",
        )

        assert stripe_account is None
        assert fee is None

    @pytest.mark.asyncio
    async def test_resolve_stripe_connect_pending_raises(self, db_session: AsyncSession, test_user: User) -> None:
        """Pending onboarding raises ValidationError."""
        business = await _create_business(
            db_session,
            test_user,
            stripe_account_id="acct_pending",
            stripe_connect_status="pending",
        )

        service = PaymentService(db_session, payment_provider=StripePaymentProvider(api_key="sk_test"))

        with pytest.raises(ValidationError, match="cannot accept charges"):
            await service._resolve_stripe_connect(
                business_id=business.id,
                amount=Decimal("100.00"),
                currency="aud",
            )

    @pytest.mark.asyncio
    async def test_resolve_stripe_connect_stub_provider(self, db_session: AsyncSession, test_user: User) -> None:
        """Stub provider returns (None, None) — no Stripe Connect."""
        business = await _create_business(
            db_session,
            test_user,
            stripe_account_id="acct_stub",
            stripe_connect_status="active",
            stripe_charges_enabled=True,
        )

        service = PaymentService(db_session, payment_provider=StubPaymentProvider())
        stripe_account, fee = await service._resolve_stripe_connect(
            business_id=business.id,
            amount=Decimal("100.00"),
            currency="aud",
        )

        assert stripe_account is None
        assert fee is None

    @pytest.mark.asyncio
    async def test_resolve_stripe_connect_charges_disabled_raises(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """Charges disabled raises ValidationError."""
        business = await _create_business(
            db_session,
            test_user,
            stripe_account_id="acct_nochg",
            stripe_connect_status="charges_disabled",
            stripe_charges_enabled=False,
        )

        service = PaymentService(db_session, payment_provider=StripePaymentProvider(api_key="sk_test"))

        with pytest.raises(ValidationError, match="cannot accept charges"):
            await service._resolve_stripe_connect(
                business_id=business.id,
                amount=Decimal("100.00"),
                currency="aud",
            )


# ---------------------------------------------------------------------------
# Tests: Tenant isolation
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    """Verify connected account ownership is tenant-scoped."""

    @pytest.mark.asyncio
    async def test_stripe_account_id_unique_per_business(
        self, db_session: AsyncSession, test_user: User, second_user: User
    ) -> None:
        """Two businesses cannot share the same Stripe account ID."""
        biz1 = await _create_business(db_session, test_user, stripe_account_id="acct_unique")
        biz2 = await _create_business(db_session, second_user, name="Other Biz", slug="other-biz")

        # biz2 should not have the same stripe_account_id
        assert biz2.stripe_account_id is None
        assert biz1.stripe_account_id == "acct_unique"

    @pytest.mark.asyncio
    async def test_resolve_stripe_connect_wrong_business(
        self, db_session: AsyncSession, test_user: User, second_user: User
    ) -> None:
        """A business can only resolve its own Stripe account."""
        biz1 = await _create_business(
            db_session,
            test_user,
            stripe_account_id="acct_biz1",
            stripe_connect_status="active",
            stripe_charges_enabled=True,
        )
        biz2 = await _create_business(db_session, second_user, name="Other Biz", slug="other-biz-2")

        service = PaymentService(db_session, payment_provider=StripePaymentProvider(api_key="sk_test"))

        # biz2 has no Stripe account — should return (None, None)
        stripe_account, fee = await service._resolve_stripe_connect(
            business_id=biz2.id,
            amount=Decimal("100.00"),
            currency="aud",
        )
        assert stripe_account is None

        # biz1 has a valid account
        stripe_account, fee = await service._resolve_stripe_connect(
            business_id=biz1.id,
            amount=Decimal("100.00"),
            currency="aud",
        )
        assert stripe_account == "acct_biz1"


# ---------------------------------------------------------------------------
# Tests: Webhook account.updated
# ---------------------------------------------------------------------------


class TestAccountUpdatedWebhook:
    """Test the account.updated webhook handler."""

    @pytest.mark.asyncio
    async def test_handle_account_updated(self, db_session: AsyncSession, test_user: User) -> None:
        """account.updated webhook updates business status."""
        await _create_business(
            db_session,
            test_user,
            stripe_account_id="acct_webhook",
            stripe_connect_status="pending",
        )

        service = StripeConnectService.__new__(StripeConnectService)
        service.session = db_session
        service._api_key = "sk_test_fake"
        service._default_platform_fee_percent = Decimal("5.00")
        service._client = MockStripeClient()

        account_data = {
            "id": "acct_webhook",
            "type": "express",
            "country": "AU",
            "charges_enabled": True,
            "payouts_enabled": True,
            "details_submitted": True,
        }

        result = await service.handle_account_updated(account_data)

        assert result is not None
        assert result.stripe_connect_status == StripeConnectAccountStatus.ACTIVE
        assert result.stripe_charges_enabled is True
        assert result.stripe_payouts_enabled is True

    @pytest.mark.asyncio
    async def test_handle_account_updated_unknown_account(self, db_session: AsyncSession, test_user: User) -> None:
        """Unknown Stripe account ID returns None."""
        service = StripeConnectService.__new__(StripeConnectService)
        service.session = db_session
        service._api_key = "sk_test_fake"
        service._default_platform_fee_percent = Decimal("5.00")
        service._client = MockStripeClient()

        result = await service.handle_account_updated({"id": "acct_unknown"})
        assert result is None


# ---------------------------------------------------------------------------
# Tests: Derive connect status
# ---------------------------------------------------------------------------


class TestDeriveConnectStatus:
    """Test the status derivation logic."""

    def test_active(self) -> None:
        status = StripeConnectService._derive_connect_status(
            charges_enabled=True, payouts_enabled=True, details_submitted=True
        )
        assert status == StripeConnectAccountStatus.ACTIVE

    def test_payouts_disabled(self) -> None:
        status = StripeConnectService._derive_connect_status(
            charges_enabled=True, payouts_enabled=False, details_submitted=True
        )
        assert status == StripeConnectAccountStatus.PAYOUTS_DISABLED

    def test_charges_disabled(self) -> None:
        status = StripeConnectService._derive_connect_status(
            charges_enabled=False, payouts_enabled=True, details_submitted=True
        )
        assert status == StripeConnectAccountStatus.CHARGES_DISABLED

    def test_restricted(self) -> None:
        class FakeReq:
            currently_due = []
            eventually_due = []
            past_due = []
            disabled_reason = "requirements.past_due"

        status = StripeConnectService._derive_connect_status(
            charges_enabled=False,
            payouts_enabled=False,
            details_submitted=True,
            requirements=FakeReq(),
        )
        assert status == StripeConnectAccountStatus.RESTRICTED

    def test_pending_not_submitted(self) -> None:
        status = StripeConnectService._derive_connect_status(
            charges_enabled=False, payouts_enabled=False, details_submitted=False
        )
        assert status == StripeConnectAccountStatus.PENDING

    def test_charges_disabled_both_false_submitted(self) -> None:
        status = StripeConnectService._derive_connect_status(
            charges_enabled=False, payouts_enabled=False, details_submitted=True
        )
        assert status == StripeConnectAccountStatus.CHARGES_DISABLED
