"""HubSpot CRM provider.

Implements the CRMProvider interface using the HubSpot CRM API.
Syncs FIELDed customers/contacts and logs interactions.

Configuration:
    CRM_PROVIDER=hubspot
    CRM_API_KEY=<HubSpot private app access token>

Uses HubSpot CRM API v3 for contact management and engagement logging.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.adapters.crm.base import (
    ContactSyncRequest,
    ContactSyncResult,
    CRMProvider,
)

logger = logging.getLogger(__name__)

_HUBSPOT_API_BASE = "https://api.hubapi.com/crm/v3"


class HubSpotCRMProvider(CRMProvider):
    """HubSpot CRM integration provider."""

    def __init__(self, access_token: str) -> None:
        self._access_token = access_token

    @property
    def provider_name(self) -> str:
        return "hubspot"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    async def sync_contact(self, request: ContactSyncRequest) -> ContactSyncResult:
        """Sync a contact to HubSpot.

        Creates or updates a HubSpot contact using the FIELDed
        contact ID as an idempotent identifier stored in a
        custom property.
        """
        if not self._access_token:
            logger.warning("HubSpot CRM provider selected but CRM_API_KEY is empty.")
            return ContactSyncResult(
                external_id="",
                success=False,
                provider_name=self.provider_name,
                error="HubSpot credentials not configured",
            )

        properties: dict[str, str] = {
            "email": request.email,
            "firstname": request.name.split(" ")[0] if request.name else "",
            "lastname": " ".join(request.name.split(" ")[1:])
            if request.name and len(request.name.split(" ")) > 1
            else "",
            "fielded_contact_id": request.contact_id,
        }
        if request.phone:
            properties["phone"] = request.phone
        if request.company:
            properties["company"] = request.company

        # Try to find existing contact by fielded_contact_id
        existing_id = await self._find_contact_by_fielded_id(request.contact_id)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if existing_id:
                    # Update existing contact
                    response = await client.patch(
                        f"{_HUBSPOT_API_BASE}/objects/contacts/{existing_id}",
                        headers=self._headers(),
                        json={"properties": properties},
                    )
                else:
                    # Create new contact
                    response = await client.post(
                        f"{_HUBSPOT_API_BASE}/objects/contacts",
                        headers=self._headers(),
                        json={"properties": properties},
                    )

                response.raise_for_status()
                data = response.json()

            hubspot_id = data.get("id", "")
            logger.info("hubspot_contact_synced", extra={"hubspot_id": hubspot_id, "fielded_id": request.contact_id})
            return ContactSyncResult(
                external_id=hubspot_id,
                success=True,
                provider_name=self.provider_name,
            )

        except httpx.HTTPStatusError as exc:
            error_body = exc.response.text[:500] if exc.response else str(exc)
            logger.error(
                "hubspot_sync_failed",
                extra={"status": exc.response.status_code if exc.response else None, "body": error_body},
            )
            return ContactSyncResult(
                external_id="",
                success=False,
                provider_name=self.provider_name,
                error=f"HubSpot API error: {exc.response.status_code}" if exc.response else str(exc),
            )
        except httpx.RequestError as exc:
            logger.error("hubspot_network_error", extra={"error": str(exc)})
            return ContactSyncResult(
                external_id="",
                success=False,
                provider_name=self.provider_name,
                error=f"HubSpot network error: {exc}",
            )

    async def log_interaction(self, contact_external_id: str, interaction: dict[str, Any]) -> bool:
        """Log an interaction as a HubSpot engagement/note.

        Creates a note engagement on the HubSpot contact.
        """
        if not self._access_token or not contact_external_id:
            return False

        note_body = interaction.get("body", "")
        interaction_type = interaction.get("type", "note")
        subject = interaction.get("subject", f"FIELDed: {interaction_type}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Create a note engagement
                response = await client.post(
                    f"{_HUBSPOT_API_BASE}/objects/notes",
                    headers=self._headers(),
                    json={
                        "properties": {
                            "hs_note_body": f"[{subject}] {note_body}",
                            "hs_timestamp": interaction.get("timestamp", ""),
                        },
                    },
                )
                response.raise_for_status()
                note_data = response.json()
                note_id = note_data.get("id", "")

                # Associate the note with the contact
                if note_id:
                    assoc_response = await client.put(
                        f"{_HUBSPOT_API_BASE}/objects/notes/{note_id}/associations/contact/{contact_external_id}/note_to_contact",
                        headers=self._headers(),
                    )
                    assoc_response.raise_for_status()

            logger.info("hubspot_interaction_logged", extra={"contact": contact_external_id, "type": interaction_type})
            return True

        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            logger.error("hubspot_interaction_error", extra={"error": str(exc)})
            return False

    async def _find_contact_by_fielded_id(self, contact_id: str) -> str | None:
        """Find a HubSpot contact by the FIELDed contact ID property."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{_HUBSPOT_API_BASE}/objects/contacts/search",
                    headers=self._headers(),
                    json={
                        "filterGroups": [
                            {
                                "filters": [
                                    {
                                        "propertyName": "fielded_contact_id",
                                        "operator": "EQ",
                                        "value": contact_id,
                                    }
                                ]
                            }
                        ],
                        "limit": 1,
                    },
                )
                response.raise_for_status()
                data = response.json()

            results = data.get("results", [])
            if results:
                return results[0].get("id")

        except httpx.HTTPStatusError as exc:
            # 400 may mean the custom property doesn't exist yet
            if exc.response and exc.response.status_code == 400:
                logger.info("hubspot_fielded_contact_id_property_not_found")
            else:
                logger.warning("hubspot_search_error", extra={"error": str(exc)})
        except httpx.RequestError as exc:
            logger.warning("hubspot_search_network_error", extra={"error": str(exc)})

        return None
