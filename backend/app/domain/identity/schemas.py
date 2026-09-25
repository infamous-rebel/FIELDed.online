"""Identity domain Pydantic schemas.

Used for API request/response validation and data transfer.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

# --- User schemas ---


class UserBase(BaseModel):
    """Base user fields."""

    email: EmailStr


class UserCreate(UserBase):
    """Schema for user registration."""

    password: str = Field(min_length=8, max_length=128)


class UserRead(UserBase):
    """Schema for user response."""

    id: uuid.UUID
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Customer Profile schemas ---


class CustomerProfileBase(BaseModel):
    """Base customer profile fields."""

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, max_length=100)


class CustomerProfileCreate(CustomerProfileBase):
    """Schema for creating a customer profile."""

    pass


class CustomerProfileUpdate(BaseModel):
    """Schema for partial customer profile update."""

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, max_length=100)


class CustomerProfileRead(CustomerProfileBase):
    """Schema for customer profile response."""

    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Business schemas ---


class BusinessBase(BaseModel):
    """Base business fields."""

    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class BusinessCreate(BusinessBase):
    """Schema for creating a business."""

    currency: str = Field(default="GBP", min_length=3, max_length=3, description="ISO 4217 currency code")


class BusinessRead(BusinessBase):
    """Schema for business response."""

    id: uuid.UUID
    currency: str = "GBP"
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Business Profile schemas ---


class BusinessProfileBase(BaseModel):
    """Base business profile fields."""

    description: str | None = Field(default=None, max_length=2000)
    logo_url: str | None = None
    cover_image_url: str | None = None
    website: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    facebook_url: str | None = None
    instagram_url: str | None = None
    linkedin_url: str | None = None


class BusinessProfileRead(BusinessProfileBase):
    """Schema for business profile response."""

    id: uuid.UUID
    business_id: uuid.UUID
    average_rating: float | None = None
    review_count: int = 0
    is_verified: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Business Member schemas ---


class BusinessMemberBase(BaseModel):
    """Base business member fields."""

    role: str = Field(default="staff")


class BusinessMemberCreate(BusinessMemberBase):
    """Schema for adding a member to a business."""

    user_id: uuid.UUID
    business_id: uuid.UUID


class BusinessMemberRead(BusinessMemberBase):
    """Schema for business member response."""

    id: uuid.UUID
    user_id: uuid.UUID
    business_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
