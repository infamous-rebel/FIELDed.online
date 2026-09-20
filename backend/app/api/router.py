"""Root API router.

All v1 routes are mounted under /api/v1/.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    bookings,
    brain,
    business_enquiries,
    businesses,
    communications,
    customer,
    discovery,
    enquiries,
    health,
    invoices,
    ledger,
    payments,
    public,
    quotes,
    reviews,
    service_categories,
    service_executions,
    service_offers,
    voice,
)

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(customer.router, prefix="/customer", tags=["customer"])
api_router.include_router(businesses.router, prefix="/businesses", tags=["businesses"])
api_router.include_router(service_offers.router, prefix="/businesses", tags=["service-offers"])
api_router.include_router(
    service_categories.router, prefix="/categories", tags=["service-categories"]
)
api_router.include_router(public.router, prefix="/public", tags=["public"])
api_router.include_router(discovery.router, prefix="/discovery", tags=["discovery"])
api_router.include_router(enquiries.router, prefix="/enquiries", tags=["enquiries"])
api_router.include_router(
    business_enquiries.router, prefix="/businesses", tags=["business-enquiries"]
)
api_router.include_router(brain.router, prefix="/businesses", tags=["business-brain"])
api_router.include_router(quotes.router, prefix="/businesses", tags=["quotes"])
api_router.include_router(bookings.router, prefix="/businesses", tags=["bookings"])

# Phase 13 — Service Execution, Invoice, Ledger
api_router.include_router(
    service_executions.router, prefix="/businesses", tags=["service-executions"]
)
api_router.include_router(invoices.router, prefix="/businesses", tags=["invoices"])
api_router.include_router(ledger.router, prefix="/businesses", tags=["ledger"])

# Phase 14A — Communications, Notifications, Provider Infrastructure
api_router.include_router(communications.router, prefix="", tags=["communications"])

# Phase 14B — Voice Calls, Call Agent, Campaigns, Provider Webhooks
api_router.include_router(voice.router, prefix="", tags=["voice"])

# Phase 15 — Payments & Financial Operations
api_router.include_router(
    payments.router, prefix="", tags=["payments"]
)

# Phase 17 — Reviews & Trust
api_router.include_router(
    reviews.router, prefix="", tags=["reviews"]
)

# Phase 17 — Member invitation acceptance (public path outside /businesses)
api_router.include_router(
    businesses.accept_router, prefix="", tags=["businesses"]
)
