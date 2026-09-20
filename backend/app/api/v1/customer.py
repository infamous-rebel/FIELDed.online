"""Customer profile API endpoints.

Provides CRUD operations for the authenticated customer's profile.
Customers can only access and modify their own profile.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.domain.identity.models import CustomerProfile, User
from app.exceptions import AuthorizationError
from app.security.authorization import get_current_user

router = APIRouter()


# --- Schemas ---


class CustomerProfileRead(BaseModel):
    id: str
    user_id: str
    first_name: str
    last_name: str
    phone: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    status: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class CustomerProfileUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, max_length=100)


# --- Helpers ---


def _profile_to_response(profile: CustomerProfile) -> CustomerProfileRead:
    """Convert a CustomerProfile model to the response schema."""
    return CustomerProfileRead(
        id=str(profile.id),
        user_id=str(profile.user_id),
        first_name=profile.first_name,
        last_name=profile.last_name,
        phone=profile.phone,
        address_line1=profile.address_line1,
        address_line2=profile.address_line2,
        city=profile.city,
        state=profile.state,
        postal_code=profile.postal_code,
        country=profile.country,
        status=profile.status,
        created_at=profile.created_at.isoformat(),
        updated_at=profile.updated_at.isoformat(),
    )


# --- Endpoints ---


@router.get("/profile", response_model=CustomerProfileRead)
async def get_profile(
    user: Annotated[User, Depends(get_current_user)],
) -> CustomerProfileRead:
    """Get the current customer's profile.

    Customers can only access their own profile.
    """
    if user.customer_profile is None:
        raise AuthorizationError("Customer profile required")

    return _profile_to_response(user.customer_profile)


@router.put("/profile", response_model=CustomerProfileRead)
async def update_profile(
    body: CustomerProfileUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CustomerProfileRead:
    """Update the current customer's profile.

    Customers can only modify their own profile.
    Only provided fields are updated (partial update semantics).
    """
    if user.customer_profile is None:
        raise AuthorizationError("Customer profile required")

    profile = user.customer_profile

    # Update only provided fields
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(profile, field, value)

    await db.flush()
    await db.refresh(profile)

    return _profile_to_response(profile)
