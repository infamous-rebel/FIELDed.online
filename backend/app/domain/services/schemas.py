"""Service Offer domain Pydantic schemas.

Used for API request/response validation and data transfer.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

# --- ServiceCategory schemas ---


class ServiceCategoryBase(BaseModel):
    """Base service category fields."""

    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255)
    description: str | None = None


class ServiceCategoryCreate(ServiceCategoryBase):
    """Schema for creating a service category."""

    parent_id: uuid.UUID | None = None


class ServiceCategoryRead(ServiceCategoryBase):
    """Schema for service category response."""

    id: uuid.UUID
    parent_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ServiceCategoryTree(ServiceCategoryRead):
    """Category with nested children for tree display."""

    children: list[ServiceCategoryTree] = []


# --- ServiceOffer schemas ---


class ServiceOfferBase(BaseModel):
    """Base service offer fields."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    delivery_mode: str = Field(default="on_site")
    pricing_model: str = Field(default="quote_required")
    pricing_config: dict | None = None
    qualification_requirements: dict | None = None
    booking_rules: dict | None = None
    cancellation_policy: dict | None = None
    service_area: dict | None = None


class ServiceOfferCreate(ServiceOfferBase):
    """Schema for creating a service offer."""

    category_id: uuid.UUID | None = None


class ServiceOfferUpdate(BaseModel):
    """Schema for partial service offer update."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    delivery_mode: str | None = None
    pricing_model: str | None = None
    pricing_config: dict | None = None
    qualification_requirements: dict | None = None
    booking_rules: dict | None = None
    cancellation_policy: dict | None = None
    service_area: dict | None = None
    category_id: uuid.UUID | None = None


class ServiceOfferRead(ServiceOfferBase):
    """Schema for service offer response."""

    id: uuid.UUID
    business_id: uuid.UUID
    category_id: uuid.UUID | None = None
    slug: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ServiceOfferPublic(BaseModel):
    """Public-facing service offer (limited fields)."""

    id: str
    name: str
    slug: str
    description: str | None = None
    delivery_mode: str
    pricing_model: str
    category: ServiceCategoryRead | None = None
    status: str

    model_config = {"from_attributes": True}


class ServiceOfferTransitionRequest(BaseModel):
    """Request to transition a service offer's status."""

    target_status: str = Field(
        pattern=r"^(active|paused|archived)$",
        description="Target lifecycle status",
    )
