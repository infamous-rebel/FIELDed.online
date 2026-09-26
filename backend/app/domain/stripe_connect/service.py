"""Stripe Connect domain service.

Manages the lifecycle of Stripe connected accounts for FIELDed businesses:
- Account creation via Stripe Connect
- Onboarding account-link generation
- Account status refresh from Stripe API
- Application-fee computation for Direct Charges
- Pre-payment validation (account exists, charges enabled)

This service depends on the Stripe SDK through the existing
StripePaymentProvider adapter.  It never exposes secret keys.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.common.enums import StripeConnectAccountStatus
from app.domain.identity.models import Business
from app.exceptions import NotFoundError, ValidationError

logger = logging.getLogger(__name__)


class StripeConnectService:
    """Stripe Connect lifecycle management for FIELDed businesses."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        stripe_api_key: str,
        platform_fee_percent: Decimal | None = None,
        http_client: Any | None = None,
    ) -> None:
        self.session = session
        self._api_key = stripe_api_key
        self._default_platform_fee_percent = platform_fee_percent or Decimal("5.00")

        client_kwargs: dict[str, Any] = {}
        if http_client is not None:
            client_kwargs["http_client"] = http_client
        self._client = stripe.StripeClient(api_key=stripe_api_key, **client_kwargs)

    # ------------------------------------------------------------------
    # Account creation
    # ------------------------------------------------------------------

    async def create_connected_account(
        self,
        business_id: uuid.UUID,
        *,
        account_type: str = "express",
        email: str | None = None,
        country: str = "AU",
    ) -> Business:
        """Create a Stripe connected account for a business.

        The business must not already have a connected account.
        """
        business = await self._get_business(business_id)
        if business.stripe_account_id:
            raise ValidationError(
                f"Business {business_id} already has a Stripe connected account ({business.stripe_account_id})"
            )

        try:
            params: dict[str, Any] = {
                "type": account_type,
                "country": country,
            }
            if email:
                params["email"] = email

            account = self._client.v1.accounts.create(params)
            stripe_account_id = account.id

            business.stripe_account_id = stripe_account_id
            business.stripe_connect_status = StripeConnectAccountStatus.PENDING
            business.stripe_details = {
                "id": stripe_account_id,
                "type": account_type,
                "country": country,
                "charges_enabled": getattr(account, "charges_enabled", False),
                "payouts_enabled": getattr(account, "payouts_enabled", False),
                "details_submitted": getattr(account, "details_submitted", False),
            }
            await self.session.flush()

            logger.info(
                "stripe_connect_account_created: business=%s stripe=%s",
                business_id,
                stripe_account_id,
            )
            return business

        except stripe.StripeError as exc:
            logger.warning("stripe_connect_create_failed: %s", exc)
            raise ValidationError(f"Stripe account creation failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Account link (onboarding)
    # ------------------------------------------------------------------

    async def create_account_link(
        self,
        business_id: uuid.UUID,
        *,
        refresh_url: str,
        return_url: str,
        link_type: str = "account_onboarding",
    ) -> dict[str, Any]:
        """Create a Stripe-hosted onboarding account link.

        The business must already have a connected Stripe account.
        """
        business = await self._get_business(business_id)
        if not business.stripe_account_id:
            raise ValidationError(f"Business {business_id} has no Stripe connected account. Create one first.")

        try:
            link = self._client.v1.account_links.create(
                {
                    "account": business.stripe_account_id,
                    "refresh_url": refresh_url,
                    "return_url": return_url,
                    "type": link_type,
                }
            )
            return {
                "url": link.url,
                "expires_at": getattr(link, "expires_at", None),
                "created": getattr(link, "created", None),
            }
        except stripe.StripeError as exc:
            logger.warning("stripe_connect_account_link_failed: %s", exc)
            raise ValidationError(f"Account link creation failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Account status refresh
    # ------------------------------------------------------------------

    async def refresh_account_status(self, business_id: uuid.UUID) -> Business:
        """Fetch the latest account status from Stripe and persist it."""
        business = await self._get_business(business_id)
        if not business.stripe_account_id:
            raise ValidationError(f"Business {business_id} has no Stripe connected account.")

        try:
            account = self._client.v1.accounts.retrieve(business.stripe_account_id)
            self._apply_account_status(business, account)
            await self.session.flush()

            logger.info(
                "stripe_connect_status_refreshed: business=%s status=%s",
                business_id,
                business.stripe_connect_status,
            )
            return business

        except stripe.StripeError as exc:
            logger.warning("stripe_connect_refresh_failed: %s", exc)
            raise ValidationError(f"Account status refresh failed: {exc}") from exc

    def get_connect_status(self, business: Business) -> dict[str, Any]:
        """Return the current Stripe Connect status for a business."""
        return {
            "business_id": business.id,
            "stripe_account_id": business.stripe_account_id,
            "stripe_connect_status": business.stripe_connect_status,
            "stripe_charges_enabled": business.stripe_charges_enabled,
            "stripe_payouts_enabled": business.stripe_payouts_enabled,
            "stripe_details": business.stripe_details,
            "platform_fee_percent": str(business.platform_fee_percent),
        }

    # ------------------------------------------------------------------
    # Pre-payment validation
    # ------------------------------------------------------------------

    async def validate_can_charge(self, business_id: uuid.UUID) -> str:
        """Validate the business can accept Stripe charges.

        Returns the stripe_account_id on success.
        Raises ValidationError if the account is missing, incomplete,
        or charges are disabled.
        """
        business = await self._get_business(business_id)

        if not business.stripe_account_id:
            raise ValidationError(
                f"Business {business_id} has no Stripe connected account. Cannot process Stripe payments."
            )

        status = StripeConnectAccountStatus(business.stripe_connect_status)
        if status == StripeConnectAccountStatus.NONE:
            raise ValidationError(f"Business {business_id} Stripe account not initialised.")
        if status == StripeConnectAccountStatus.PENDING:
            raise ValidationError(f"Business {business_id} Stripe onboarding incomplete. Charges are not yet enabled.")
        if status == StripeConnectAccountStatus.RESTRICTED:
            raise ValidationError(f"Business {business_id} Stripe account is restricted.")
        if status == StripeConnectAccountStatus.CHARGES_DISABLED:
            raise ValidationError(f"Business {business_id} Stripe charges are disabled.")
        if not business.stripe_charges_enabled:
            raise ValidationError(f"Business {business_id} Stripe charges_enabled is false.")

        return business.stripe_account_id

    # ------------------------------------------------------------------
    # Application fee computation
    # ------------------------------------------------------------------

    def compute_application_fee(
        self,
        amount: Decimal,
        currency: str,
        business: Business,
    ) -> int:
        """Compute the platform application fee in smallest currency unit.

        Uses the business's platform_fee_percent (or the global default).
        Returns 0 when no fee is configured.
        """
        fee_percent = Decimal(str(business.platform_fee_percent))
        if fee_percent <= 0:
            fee_percent = self._default_platform_fee_percent

        if fee_percent <= 0:
            return 0

        # Convert to smallest currency unit
        zero_decimal_currencies = {"jpy", "krw", "vnd", "clp", "huf"}
        if currency.lower() in zero_decimal_currencies:
            amount_minor = int(amount)
        else:
            amount_minor = int(amount * 100)

        fee = int(amount_minor * fee_percent / Decimal("100"))
        return max(0, fee)

    # ------------------------------------------------------------------
    # Webhook: account.updated
    # ------------------------------------------------------------------

    async def handle_account_updated(self, account_data: dict) -> Business | None:
        """Process a Stripe account.updated webhook event.

        Updates the business's Stripe Connect status from the event data.
        """
        stripe_account_id = account_data.get("id", "")
        if not stripe_account_id:
            return None

        business = await self._get_business_by_stripe_account(stripe_account_id)
        if business is None:
            logger.warning(
                "stripe_connect_webhook_unknown_account: %s",
                stripe_account_id,
            )
            return None

        self._apply_account_status_from_dict(business, account_data)
        await self.session.flush()

        logger.info(
            "stripe_connect_account_updated: business=%s status=%s",
            business.id,
            business.stripe_connect_status,
        )
        return business

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_business(self, business_id: uuid.UUID) -> Business:
        """Fetch a business by ID."""
        result = await self.session.execute(
            select(Business).where(
                Business.id == business_id,
                Business.deleted_at.is_(None),
            )
        )
        business = result.scalar_one_or_none()
        if business is None:
            raise NotFoundError(f"Business {business_id} not found")
        return business

    async def _get_business_by_stripe_account(self, stripe_account_id: str) -> Business | None:
        """Fetch a business by its Stripe connected account ID."""
        result = await self.session.execute(
            select(Business).where(
                Business.stripe_account_id == stripe_account_id,
                Business.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    def _apply_account_status(self, business: Business, account: Any) -> None:
        """Map Stripe account capabilities to FIELDed status fields."""
        charges_enabled = getattr(account, "charges_enabled", False)
        payouts_enabled = getattr(account, "payouts_enabled", False)
        details_submitted = getattr(account, "details_submitted", False)
        requirements = getattr(account, "requirements", None)

        business.stripe_charges_enabled = charges_enabled
        business.stripe_payouts_enabled = payouts_enabled

        # Build a snapshot of the account for audit/debugging.
        business.stripe_details = {
            "id": getattr(account, "id", ""),
            "type": getattr(account, "type", ""),
            "country": getattr(account, "country", ""),
            "charges_enabled": charges_enabled,
            "payouts_enabled": payouts_enabled,
            "details_submitted": details_submitted,
        }
        if requirements:
            business.stripe_details["requirements"] = {
                "currently_due": getattr(requirements, "currently_due", []),
                "eventually_due": getattr(requirements, "eventually_due", []),
                "past_due": getattr(requirements, "past_due", []),
                "disabled_reason": getattr(requirements, "disabled_reason", None),
            }

        # Derive the FIELDed connect status.
        business.stripe_connect_status = self._derive_connect_status(
            charges_enabled=charges_enabled,
            payouts_enabled=payouts_enabled,
            details_submitted=details_submitted,
            requirements=requirements,
        )

    def _apply_account_status_from_dict(self, business: Business, account_data: dict) -> None:
        """Same as _apply_account_status but from a raw dict (webhook)."""
        charges_enabled = account_data.get("charges_enabled", False)
        payouts_enabled = account_data.get("payouts_enabled", False)
        details_submitted = account_data.get("details_submitted", False)
        requirements = account_data.get("requirements")

        business.stripe_charges_enabled = charges_enabled
        business.stripe_payouts_enabled = payouts_enabled

        business.stripe_details = {
            "id": account_data.get("id", ""),
            "type": account_data.get("type", ""),
            "country": account_data.get("country", ""),
            "charges_enabled": charges_enabled,
            "payouts_enabled": payouts_enabled,
            "details_submitted": details_submitted,
        }
        if requirements:
            business.stripe_details["requirements"] = {
                "currently_due": requirements.get("currently_due", []),
                "eventually_due": requirements.get("eventually_due", []),
                "past_due": requirements.get("past_due", []),
                "disabled_reason": requirements.get("disabled_reason"),
            }

        business.stripe_connect_status = self._derive_connect_status(
            charges_enabled=charges_enabled,
            payouts_enabled=payouts_enabled,
            details_submitted=details_submitted,
            requirements_dict=requirements,
        )

    @staticmethod
    def _derive_connect_status(
        *,
        charges_enabled: bool,
        payouts_enabled: bool,
        details_submitted: bool,
        requirements: Any = None,
        requirements_dict: dict | None = None,
    ) -> str:
        """Derive the FIELDed StripeConnectAccountStatus from Stripe data."""
        # Check for disabled_reason in requirements
        disabled_reason = None
        if requirements is not None:
            disabled_reason = getattr(requirements, "disabled_reason", None)
        elif requirements_dict:
            disabled_reason = requirements_dict.get("disabled_reason")

        if disabled_reason:
            return StripeConnectAccountStatus.RESTRICTED

        if charges_enabled and payouts_enabled:
            return StripeConnectAccountStatus.ACTIVE

        if charges_enabled and not payouts_enabled:
            return StripeConnectAccountStatus.PAYOUTS_DISABLED

        if not charges_enabled and payouts_enabled:
            return StripeConnectAccountStatus.CHARGES_DISABLED

        if not details_submitted:
            return StripeConnectAccountStatus.PENDING

        # charges_enabled=False, payouts_enabled=False, details_submitted=True
        return StripeConnectAccountStatus.CHARGES_DISABLED
