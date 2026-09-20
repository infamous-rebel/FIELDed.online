# FIELDed — Authorization Model

## Overview

Authorization is resolved server-side from authenticated identity and database relationships. The frontend never controls access decisions.

## Role Hierarchy

### System Roles
- `customer` — Can search, enquire, book, review
- `business_owner` — Full control of a business
- `business_admin` — Manage business operations
- `business_staff` — Handle enquiries and bookings
- `platform_admin` — FIELDed platform management

### Business Member Roles
- `owner` (level 3) — Full control, can manage Brain, activate versions
- `admin` (level 2) — Manage services, handle enquiries
- `staff` (level 1) — View and respond to enquiries

## Dependencies

### get_current_user
Extracts JWT from Authorization header, resolves User from database. Returns 401 if invalid.

### require_customer
Ensures user has a CustomerProfile. Returns 403 if not.

### require_business_member
Ensures user has at least one BusinessMember record. Returns 403 if not.

### require_business_role(minimum_role)
Factory that creates a dependency checking role level for a specific business. Returns 403 if insufficient role.

### tenant_scope(model_class)
Factory that creates a tenant-scoped query helper. Ensures queries only return records within the user's tenant boundary.

### Brain Authorization Dependencies

Future Brain API endpoints must use the following reusable FastAPI dependencies (defined in `app/domain/business/auth.py`):

- `require_brain_access` — READ access: any business member (staff+) can read the Brain. Verifies business exists, user is a member, and returns the Brain (creating it if needed).
- `require_brain_modify` — MODIFY access: admin+ role required. For creating/editing versions and rules.
- `require_brain_approve` — APPROVE/ACTIVATE access: owner only. For approving and activating Brain versions.
- `require_brain_version_access` — Resolves a BrainVersion within a tenant-scoped Brain, verifying the version belongs to the referenced business's brain.
- `require_brain_version_modify` — Same as above but requires admin+ role.

These dependencies enforce:
1. Business existence verification
2. User membership verification (tenant isolation)
3. Role hierarchy enforcement (owner > admin > staff)
4. Version-to-brain ownership verification

## Tenant Isolation Rules

1. Customer can only see: their own profile, enquiries, conversations, quotes, bookings, reviews
2. Business member can only see: their business's data
3. Business A cannot see Business B's: customers, enquiries, messages, quotes, Brain, bookings, audit records
4. Authorization checked at repository layer, not just API layer

## Implementation

```python
# Example: tenant-scoped query
async def get_enquiry(enquiry_id, user, db):
    if user.customer_profile:
        # Customer: only their own enquiries
        result = await db.execute(
            select(Enquiry).where(
                Enquiry.id == enquiry_id,
                Enquiry.customer_id == user.id,
            )
        )
    elif user.business_memberships:
        business_ids = [m.business_id for m in user.business_memberships]
        result = await db.execute(
            select(Enquiry).where(
                Enquiry.id == enquiry_id,
                Enquiry.business_id.in_(business_ids),
            )
        )
```
