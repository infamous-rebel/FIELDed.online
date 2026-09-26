"""Stripe Connect API endpoints.

Provides Stripe Connect onboarding, account status, and webhook handling
for business connected accounts.

All ownership is verified server-side.
Tenant isolation is enforced — a business can only access its own
Stripe Connect status.

Secrets (API keys, webhook secrets) are never exposed to the frontend.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.domain.identity.models import User
from app.domain.stripe_connect.schemas import (
    StripeAccountLinkCreate,
    StripeAccountLinkRead,
    StripeAccountRefreshRead,
    StripeConnectStatusRead,
)
from app.domain.stripe_connect.service import StripeConnectService
from app.exceptions import ValidationError
from app.security.authorization import require_business_member

logger = logging.getLogger(__name__)

router = APIRouter()


def _stripe_connect_service(db: AsyncSession, request: Request) -> StripeConnectService:
    """Build a StripeConnectService from application settings."""
    settings = request.app.state.settings
    api_key = getattr(settings, "payment_api_key", "")
    if not api_key:
        raise ValidationError("Stripe is not configured. Set PAYMENT_API_KEY to use Stripe Connect.")
    platform_fee = Decimal(getattr(settings, "platform_fee_percent", "5.00"))
    return StripeConnectService(
        session=db,
        stripe_api_key=api_key,
        platform_fee_percent=platform_fee,
    )


# --- Business Stripe Connect status ---


@router.get(
    "/businesses/{business_id}/stripe-connect",
    response_model=StripeConnectStatusRead,
)
async def get_stripe_connect_status(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
) -> StripeConnectStatusRead:
    """Get the Stripe Connect status for a business.

    Returns the connected account ID, onboarding status,
    charges/payouts capability flags, and platform fee percent.
    """
    service = _stripe_connect_service(db, request)
    business = await service._get_business(business_id)
    status = service.get_connect_status(business)
    return StripeConnectStatusRead(**status)


# --- Account creation ---


@router.post(
    "/businesses/{business_id}/stripe-connect/account",
    response_model=StripeConnectStatusRead,
    status_code=201,
)
async def create_stripe_connected_account(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
) -> StripeConnectStatusRead:
    """Create a Stripe connected account for a business.

    The business must not already have a connected account.
    After creation, use the account-link endpoint to start onboarding.
    """
    service = _stripe_connect_service(db, request)
    business = await service.create_connected_account(
        business_id,
        email=user.email,
    )
    status = service.get_connect_status(business)
    return StripeConnectStatusRead(**status)


# --- Account link (onboarding) ---


@router.post(
    "/businesses/{business_id}/stripe-connect/account-link",
    response_model=StripeAccountLinkRead,
    status_code=201,
)
async def create_stripe_account_link(
    business_id: uuid.UUID,
    body: StripeAccountLinkCreate,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
) -> StripeAccountLinkRead:
    """Create a Stripe-hosted onboarding account link.

    The business must already have a connected Stripe account.
    Returns a URL that the business owner should visit to complete
    onboarding.
    """
    service = _stripe_connect_service(db, request)
    link_data = await service.create_account_link(
        business_id,
        refresh_url=body.refresh_url,
        return_url=body.return_url,
        link_type=body.type,
    )
    return StripeAccountLinkRead(**link_data)


# --- Account status refresh ---


@router.post(
    "/businesses/{business_id}/stripe-connect/refresh",
    response_model=StripeAccountRefreshRead,
)
async def refresh_stripe_account_status(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
) -> StripeAccountRefreshRead:
    """Refresh the Stripe account status from the Stripe API.

    Fetches the latest account details from Stripe and updates
    the business's stored status.
    """
    service = _stripe_connect_service(db, request)
    business = await service.refresh_account_status(business_id)
    return StripeAccountRefreshRead(
        business_id=business.id,
        stripe_account_id=business.stripe_account_id,
        stripe_connect_status=business.stripe_connect_status,
        stripe_charges_enabled=business.stripe_charges_enabled,
        stripe_payouts_enabled=business.stripe_payouts_enabled,
        stripe_details=business.stripe_details,
    )


# --- Stripe Connect webhook (public, no auth) ---


@router.post(
    "/webhooks/stripe-connect",
    status_code=200,
)
async def stripe_connect_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> JSONResponse:
    """Handle Stripe Connect webhook events.

    Processes account.updated events to keep the business's
    Stripe Connect status in sync.
    """
    body = await request.body()
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON payload"},
        )

    settings = request.app.state.settings
    webhook_secret = getattr(settings, "stripe_connect_webhook_secret", "")
    # Fall back to the payment webhook secret if no dedicated Connect secret.
    if not webhook_secret:
        webhook_secret = getattr(settings, "payment_webhook_secret", "")

    # Verify signature if secret is configured.
    if webhook_secret:
        import stripe as stripe_module

        signature = request.headers.get("Stripe-Signature", "")
        if not signature:
            return JSONResponse(
                status_code=401,
                content={"error": "Missing webhook signature"},
            )
        try:
            stripe_module.WebhookSignature.verify_header(
                payload=body,
                header=signature,
                secret=webhook_secret,
            )
        except stripe_module.SignatureVerificationError:
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid webhook signature"},
            )

    event_type = payload.get("type", "")
    data_object = payload.get("data", {}).get("object", {})

    if event_type == "account.updated":
        api_key = getattr(settings, "payment_api_key", "")
        if api_key:
            service = StripeConnectService(
                session=db,
                stripe_api_key=api_key,
            )
            business = await service.handle_account_updated(data_object)
            return JSONResponse(
                status_code=200,
                content={
                    "received": True,
                    "business_id": str(business.id) if business else None,
                },
            )

    # Acknowledge unhandled events to prevent Stripe retries.
    return JSONResponse(
        status_code=200,
        content={"received": True, "event_type": event_type},
    )
