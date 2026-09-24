"""Seed the platform service-category taxonomy.

Usage:
    python -m app.seed.service_categories

Idempotent: existing categories (matched by slug) are left unchanged,
missing ones are inserted. Safe to run on every deployment.

The category list is the canonical taxonomy referenced by the discovery
interpreter's classification map (app/adapters/ai/stub.py) and the
discovery docs. Categories are platform reference data — this seed never
touches business-owned data.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Register related mappers first: ServiceOffer references Business via
# relationship(), so identity models must be in the registry before
# SQLAlchemy configures mappers on first use.
import app.domain.identity.models  # noqa: F401,E402
from app.config import get_settings
from app.database import build_engine
from app.domain.services.models import ServiceCategory  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Canonical platform taxonomy (slug, name, description).
# Must stay aligned with the discovery interpreter's category map.
#
# The taxonomy is intentionally broad: FIELDed is a service-agnostic
# platform and businesses may offer any legitimate service worldwide.
# These seed categories provide useful defaults for discovery; the
# POST /categories endpoint lets businesses create additional
# categories on the fly for services not covered here.
SERVICE_CATEGORIES: list[tuple[str, str, str]] = [
    # Original trade categories (discovery stub keyword map references these slugs)
    ("electrical", "Electrical", "Electrical installation, repair, and maintenance work."),
    ("plumbing", "Plumbing", "Plumbing installation, repair, and maintenance work."),
    ("legal", "Legal Services", "Legal advice, contracts, and representation."),
    ("accounting", "Accounting", "Bookkeeping, tax preparation, and financial services."),
    ("cleaning", "Cleaning", "Residential and commercial cleaning services."),
    ("painting", "Painting", "Interior and exterior painting and decorating."),
    ("repair", "Repair & Maintenance", "General repairs and property maintenance."),
    ("inspection", "Inspection", "Property, safety, and compliance inspections."),
    # Broad service-agnostic categories
    ("professional-services", "Professional Services", "Consulting, advisory, and professional business services."),
    (
        "technology-digital",
        "Technology & Digital",
        "Software development, IT, digital marketing, and technology services.",
    ),
    ("health-wellness", "Health & Wellness", "Healthcare, therapy, fitness, and wellness services."),
    ("education-training", "Education & Training", "Teaching, tutoring, coaching, and professional development."),
    ("creative-media", "Creative & Media", "Design, photography, video production, and creative services."),
    ("events-hospitality", "Events & Hospitality", "Event planning, catering, venue, and hospitality services."),
    ("transport-logistics", "Transport & Logistics", "Delivery, freight, moving, and logistics services."),
    (
        "real-estate-property",
        "Real Estate & Property",
        "Property management, real estate, and property-related services.",
    ),
    ("manufacturing-industrial", "Manufacturing & Industrial", "Manufacturing, fabrication, and industrial services."),
    ("personal-services", "Personal Services", "Personal care, lifestyle, and household services."),
]


async def seed_service_categories(session: AsyncSession) -> tuple[int, int]:
    """Upsert the canonical categories. Returns (created, existing) counts."""
    result = await session.execute(select(ServiceCategory.slug).where(ServiceCategory.deleted_at.is_(None)))
    existing_slugs = set(result.scalars().all())

    created = 0
    for slug, name, description in SERVICE_CATEGORIES:
        if slug in existing_slugs:
            continue
        session.add(ServiceCategory(slug=slug, name=name, description=description))
        created += 1

    await session.flush()
    return created, len(SERVICE_CATEGORIES) - created


async def main() -> None:
    """Run the seed against the configured database."""
    settings = get_settings()
    engine = build_engine(settings.database_url)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        created, existing = await seed_service_categories(session)
        await session.commit()

    await engine.dispose()
    logger.info(
        "Service category seed complete. Created %d, already present %d.",
        created,
        existing,
    )


if __name__ == "__main__":
    asyncio.run(main())
