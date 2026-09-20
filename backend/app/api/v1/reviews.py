"""Review API endpoints.

Customer-facing:
    POST /my-reviews          — Submit review
    GET  /my-reviews          — List customer's reviews
    GET  /my-reviews/{id}     — Get specific review

Public:
    GET  /public/business/{slug}/reviews — Public reviews for a business

Business-facing:
    POST /businesses/{business_id}/reviews/{id}/respond — Business response

All authorization is server-side.  Review eligibility is deterministic.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.domain.identity.models import User
from app.domain.review.repository import ReviewRepository
from app.domain.review.schemas import (
    PublicReviewListRead,
    PublicReviewRead,
    ReviewCreate,
    ReviewListRead,
    ReviewRead,
    ReviewRespondRequest,
)
from app.domain.review.service import (
    ReviewEligibilityError,
    ReviewNotFoundError,
    ReviewService,
)
from app.exceptions import NotFoundError, ValidationError
from app.security.authorization import (
    get_current_user,
    require_business_member,
    require_customer,
)

router = APIRouter()


# --- Customer endpoints ---


@router.post(
    "/my-reviews",
    response_model=ReviewRead,
    status_code=201,
)
async def submit_review(
    body: ReviewCreate,
    user: Annotated[User, Depends(require_customer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReviewRead:
    """Submit a review for a completed service.

    Eligibility is deterministic — the service verifies the full
    transaction chain before allowing submission.
    """
    service = ReviewService(db)
    try:
        review = await service.submit_review(
            customer_id=user.id,
            service_execution_id=body.service_execution_id,
            rating=body.rating,
            title=body.title,
            body=body.body,
        )
    except ReviewEligibilityError as exc:
        raise ValidationError(message=str(exc)) from exc

    await db.refresh(review)
    return ReviewRead.model_validate(review)


@router.get("/my-reviews", response_model=ReviewListRead)
async def list_my_reviews(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ReviewListRead:
    """List all reviews submitted by the authenticated customer."""
    repo = ReviewRepository(db)
    reviews = await repo.get_by_customer(user.id, limit=limit, offset=offset)
    return ReviewListRead(
        items=[ReviewRead.model_validate(r) for r in reviews],
        total=len(reviews),
    )


@router.get(
    "/my-reviews/{review_id}",
    response_model=ReviewRead,
)
async def get_my_review(
    review_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReviewRead:
    """Get a specific review owned by the authenticated customer."""
    repo = ReviewRepository(db)
    review = await repo.get_by_id(review_id)
    if review is None or review.customer_id != user.id:
        raise NotFoundError("Review not found")
    return ReviewRead.model_validate(review)


# --- Public endpoint ---


@router.get(
    "/public/business/{slug}/reviews",
    response_model=PublicReviewListRead,
)
async def get_public_business_reviews(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PublicReviewListRead:
    """Get visible reviews for a business (public, no auth required)."""
    from app.domain.identity.repository import BusinessRepository

    business_repo = BusinessRepository(db)
    business = await business_repo.get_by_slug(slug)
    if business is None:
        raise NotFoundError("Business not found")

    review_repo = ReviewRepository(db)
    reviews = await review_repo.get_visible_by_business_slug(slug, limit=limit, offset=offset)

    # Get aggregate rating
    avg_rating, _ = await review_repo.get_average_rating_for_business(business.id)

    return PublicReviewListRead(
        items=[PublicReviewRead.model_validate(r) for r in reviews],
        total=len(reviews),
        average_rating=avg_rating,
    )


# --- Business response endpoint ---


@router.post(
    "/businesses/{business_id}/reviews/{review_id}/respond",
    response_model=ReviewRead,
)
async def respond_to_review(
    business_id: uuid.UUID,
    review_id: uuid.UUID,
    body: ReviewRespondRequest,
    user: Annotated[User, Depends(require_business_member)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReviewRead:
    """Add a business response to a review.

    Requires authenticated business membership.  The review must
    belong to the specified business.
    """
    service = ReviewService(db)
    try:
        review = await service.respond_to_review(
            business_id=business_id,
            review_id=review_id,
            responder_id=user.id,
            response_body=body.response_body,
        )
    except ReviewNotFoundError as exc:
        raise NotFoundError(message=str(exc)) from exc

    await db.refresh(review)
    return ReviewRead.model_validate(review)
