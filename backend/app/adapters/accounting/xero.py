"""Xero accounting provider.

Implements the AccountingProvider interface using the Xero API.
Syncs FIELDed invoices to Xero for professional accounting.

Configuration:
    ACCOUNTING_PROVIDER=xero
    ACCOUNTING_API_KEY=<Xero OAuth2 access token or client credentials>
    XERO_TENANT_ID=<Xero tenant/connection ID>

The provider creates invoices in Xero matching FIELDed invoice data.
Uses the Xero Accounting API v2.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.adapters.accounting.base import (
    AccountingProvider,
    InvoiceSyncRequest,
    InvoiceSyncResult,
)

logger = logging.getLogger(__name__)

_XERO_API_BASE = "https://api.xero.com/api.xro/2.0"


class XeroAccountingProvider(AccountingProvider):
    """Xero accounting integration provider."""

    def __init__(self, access_token: str, tenant_id: str) -> None:
        self._access_token = access_token
        self._tenant_id = tenant_id

    @property
    def provider_name(self) -> str:
        return "xero"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Xero-Tenant-Id": self._tenant_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def sync_invoice(self, request: InvoiceSyncRequest) -> InvoiceSyncResult:
        """Sync an invoice to Xero.

        Creates a Xero invoice with contact, line items, and due date.
        Uses the FIELDed invoice ID as the Xero InvoiceNumber for
        idempotent correlation.
        """
        if not self._access_token or not self._tenant_id:
            logger.warning("Xero provider selected but credentials are empty.")
            return InvoiceSyncResult(
                external_id="",
                success=False,
                provider_name=self.provider_name,
                error="Xero credentials not configured",
            )

        # First, ensure the contact exists in Xero
        contact_id = await self._ensure_contact(
            name=request.customer_name,
            email=request.customer_email,
        )
        if not contact_id:
            return InvoiceSyncResult(
                external_id="",
                success=False,
                provider_name=self.provider_name,
                error="Failed to create/find Xero contact",
            )

        # Build Xero invoice payload
        xero_invoice = self._build_xero_invoice(request, contact_id)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{_XERO_API_BASE}/Invoices",
                    headers=self._headers(),
                    json={"Invoices": [xero_invoice]},
                )
                response.raise_for_status()
                data = response.json()

            invoices = data.get("Invoices", [])
            if invoices:
                xero_id = invoices[0].get("InvoiceID", "")
                logger.info("xero_invoice_synced", extra={"xero_id": xero_id, "fielded_id": request.invoice_id})
                return InvoiceSyncResult(
                    external_id=xero_id,
                    success=True,
                    provider_name=self.provider_name,
                )

            return InvoiceSyncResult(
                external_id="",
                success=False,
                provider_name=self.provider_name,
                error="No invoice returned from Xero",
            )

        except httpx.HTTPStatusError as exc:
            error_body = exc.response.text[:500] if exc.response else str(exc)
            logger.error(
                "xero_sync_failed",
                extra={"status": exc.response.status_code if exc.response else None, "body": error_body},
            )
            return InvoiceSyncResult(
                external_id="",
                success=False,
                provider_name=self.provider_name,
                error=f"Xero API error: {exc.response.status_code}" if exc.response else str(exc),
            )
        except httpx.RequestError as exc:
            logger.error("xero_network_error", extra={"error": str(exc)})
            return InvoiceSyncResult(
                external_id="",
                success=False,
                provider_name=self.provider_name,
                error=f"Xero network error: {exc}",
            )

    async def get_sync_status(self, external_id: str) -> dict[str, Any]:
        """Get invoice status from Xero."""
        if not self._access_token:
            return {"external_id": external_id, "status": "not_synced"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{_XERO_API_BASE}/Invoices/{external_id}",
                    headers=self._headers(),
                )
                response.raise_for_status()
                data = response.json()

            invoices = data.get("Invoices", [])
            if invoices:
                inv = invoices[0]
                return {
                    "external_id": external_id,
                    "status": inv.get("Status"),
                    "total": inv.get("Total"),
                    "amount_due": inv.get("AmountDue"),
                    "currency": inv.get("CurrencyCode"),
                    "date": inv.get("Date"),
                }

            return {"external_id": external_id, "status": "not_found"}

        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            logger.warning("xero_status_check_failed", extra={"error": str(exc)})
            return {"external_id": external_id, "status": "error", "error": str(exc)}

    async def _ensure_contact(self, name: str, email: str) -> str | None:
        """Find or create a Xero contact by email."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Search for existing contact
                search = await client.get(
                    f"{_XERO_API_BASE}/Contacts",
                    headers=self._headers(),
                    params={"where": f'EmailAddress=="{email}"'},
                )
                search.raise_for_status()
                data = search.json()
                contacts = data.get("Contacts", [])
                if contacts:
                    return contacts[0].get("ContactID")

                # Create new contact
                create = await client.post(
                    f"{_XERO_API_BASE}/Contacts",
                    headers=self._headers(),
                    json={"Contacts": [{"Name": name, "EmailAddress": email}]},
                )
                create.raise_for_status()
                created = create.json()
                new_contacts = created.get("Contacts", [])
                if new_contacts:
                    return new_contacts[0].get("ContactID")

        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            logger.error("xero_contact_error", extra={"error": str(exc)})

        return None

    def _build_xero_invoice(self, request: InvoiceSyncRequest, contact_id: str) -> dict[str, Any]:
        """Build a Xero invoice payload from a FIELDed invoice sync request."""
        line_items: list[dict[str, Any]] = []

        if request.line_items:
            for item in request.line_items:
                line_items.append(
                    {
                        "Description": item.get("description", request.description),
                        "Quantity": item.get("quantity", 1),
                        "UnitAmount": float(item.get("unit_price", request.amount)),
                        "AccountCode": item.get("account_code", "200"),  # Default: Sales
                        "TaxType": item.get("tax_type", "NONE"),
                    }
                )
        else:
            line_items.append(
                {
                    "Description": request.description,
                    "Quantity": 1,
                    "UnitAmount": float(request.amount),
                    "AccountCode": "200",
                    "TaxType": "NONE",
                }
            )

        invoice: dict[str, Any] = {
            "Type": "ACCREC",  # Accounts Receivable
            "Contact": {"ContactID": contact_id},
            "Date": request.invoice_date.isoformat(),
            "DueDate": (request.due_date or request.invoice_date).isoformat(),
            "InvoiceNumber": request.invoice_id,
            "Reference": f"FIELDed Invoice {request.invoice_id}",
            "LineItems": line_items,
            "CurrencyCode": request.currency,
            "Status": "AUTHORISED",
        }

        return invoice
