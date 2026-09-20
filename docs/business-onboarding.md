# FIELDed — Business Onboarding Specification

> **Status**: SPECIFIED BUT NOT IMPLEMENTED  
> **Phase**: Architecture + Specification Only  
> **Last Updated**: 2026-09-19

---

## Overview

This document defines the future production onboarding experience for businesses joining FIELDed. Each step is explicitly classified as IMPLEMENTED, FUTURE, or BUSINESS BRAIN-DEPENDENT.

---

## Onboarding Journey

```
[1] SIGNUP
    │
    ▼
[2] BUSINESS CREATION
    │
    ▼
[3] BUSINESS IDENTITY
    │
    ▼
[4] BUSINESS PROFILE
    │
    ▼
[5] SERVICE OFFERS
    │
    ▼
[6] PRICING
    │
    ▼
[7] AVAILABILITY
    │
    ▼
[8] POLICIES
    │
    ▼
[9] TEAM / PERMISSIONS
    │
    ▼
[10] BUSINESS BRAIN CONFIGURATION
    │
    ▼
[11] REVIEW
    │
    ▼
[12] PUBLISH / ACTIVATE
```

---

## Step-by-Step Specification

### Step 1: Signup

| Attribute | Detail |
|---|---|
| **Status** | ✅ IMPLEMENTED |
| **Actor** | Business owner / prospective member |
| **Actions** | Register with email + password |
| **Output** | User account created, JWT tokens issued |
| **Validation** | Email format, password strength, uniqueness |
| **Notes** | Same signup flow as customers. Role differentiation happens at Step 2. |

**What exists**: Full registration flow with email verification, password hashing (bcrypt), JWT issuance.

---

### Step 2: Business Creation

| Attribute | Detail |
|---|---|
| **Status** | ✅ IMPLEMENTED |
| **Actor** | Authenticated user |
| **Actions** | Create a new business entity |
| **Input** | Business name, slug |
| **Output** | Business entity created; User becomes BusinessMember with role `owner` |
| **Validation** | Name uniqueness, slug format + uniqueness |
| **Notes** | Business created with status `PENDING`. BusinessBrain created automatically (1:1). |

**What exists**: Business creation API, BusinessMember auto-created with owner role, BusinessBrain auto-created.

---

### Step 3: Business Identity

| Attribute | Detail |
|---|---|
| **Status** | ✅ IMPLEMENTED |
| **Actor** | Business owner |
| **Actions** | Configure core business identity |
| **Input** | Business details (name update, contact info) |
| **Output** | Business identity configured |
| **Validation** | Required fields present, formats valid |
| **Notes** | Currently part of Business entity. Future: may include registration numbers, tax IDs, industry classifications. |

**What exists**: Business entity with name, slug.  
**Gaps**: Additional identity fields (registration numbers, industry codes, tax information) — FUTURE.

---

### Step 4: Business Profile

| Attribute | Detail |
|---|---|
| **Status** | ✅ IMPLEMENTED |
| **Actor** | Business owner/admin |
| **Actions** | Configure public-facing business profile |
| **Input** | Description, social links, address, service area, contact details, images (future) |
| **Output** | BusinessProfile configured with public_status |
| **Validation** | URL format for social links, string lengths, service area structure |
| **Notes** | BusinessProfile is separate from Business entity. Public status controls visibility. |

**What exists**: Full CRUD for BusinessProfile with social links (website, facebook, instagram, linkedin, twitter), address, service_area (JSONB), public_status.  
**Gaps**: Image upload (FUTURE), business hours display (FUTURE — separate from Brain availability).

---

### Step 5: Service Offers

| Attribute | Detail |
|---|---|
| **Status** | ✅ IMPLEMENTED |
| **Actor** | Business owner/admin |
| **Actions** | Create and configure service offerings |
| **Input** | Name, slug, description, category, delivery_mode, pricing_model, pricing_config, qualification_requirements, booking_rules, cancellation_policy, service_area |
| **Output** | ServiceOffer created with status DRAFT |
| **Validation** | Required fields, category exists, pricing model valid, slug unique per business |
| **Notes** | ServiceOffer is the transaction anchor. Each offer must be transitioned to ACTIVE to appear in search results. |

**What exists**: Full CRUD for ServiceOffers, lifecycle transitions (DRAFT → ACTIVE → PAUSED → ARCHIVED), category assignment, JSONB configuration fields.  
**Gaps**: Bulk import (FUTURE), service offer templates (FUTURE), AI-assisted service description (FUTURE).

---

### Step 6: Pricing

| Attribute | Detail |
|---|---|
| **Status** | 🔶 PARTIALLY IMPLEMENTED |
| **Actor** | Business owner/admin |
| **Actions** | Configure pricing for each service offer |
| **Input** | Pricing model, base prices, surcharges, discounts |
| **Output** | Pricing configuration stored |
| **Validation** | Price > 0, valid currency, model-compatible configuration |
| **Notes** | Currently: pricing_config stored as JSONB on ServiceOffer. Future: Brain Pricing classification (B) governs pricing rules. |

**Currently implemented**:
- Pricing model selection (fixed, hourly, per_unit, custom_quote)
- Pricing configuration as JSONB on ServiceOffer
- Basic price validation

**Future (Business Brain-dependent)**:
- Pricing classification rules for dynamic pricing
- Surcharges (weekend, holiday, urgency)
- Volume discounts
- Customer-type pricing
- Quote thresholds
- Price floor/cap rules

---

### Step 7: Availability

| Attribute | Detail |
|---|---|
| **Status** | 🔮 FUTURE |
| **Actor** | Business owner/admin |
| **Actions** | Configure when services are available |
| **Input** | Operating hours, notice periods, capacity limits, blackout dates |
| **Output** | Availability configuration stored |
| **Validation** | Time format, valid days, capacity > 0 |
| **Notes** | Entirely dependent on Brain Availability classification (C). No availability system exists yet. |

**Future (Business Brain-dependent)**:
- Operating hours per day of week
- Minimum notice periods
- Maximum advance booking window
- Capacity limits (per day, per slot)
- Blackout periods / holidays
- Buffer time between bookings
- Location-specific availability

---

### Step 8: Policies

| Attribute | Detail |
|---|---|
| **Status** | 🔶 PARTIALLY IMPLEMENTED |
| **Actor** | Business owner/admin |
| **Actions** | Configure business policies |
| **Input** | Cancellation policy, terms, refund policy |
| **Output** | Policy configuration stored |
| **Validation** | Required fields, valid timeframes |
| **Notes** | Currently: cancellation_policy on ServiceOffer (JSONB). Future: Brain Policy classification (E) provides comprehensive policy governance. |

**Currently implemented**:
- Cancellation policy as JSONB on ServiceOffer
- Basic terms in business profile

**Future (Business Brain-dependent)**:
- Comprehensive cancellation windows with fees
- Refund policies with conditions
- Modification policies
- Terms of service
- Guarantee policies
- Complaint handling procedures

---

### Step 9: Team / Permissions

| Attribute | Detail |
|---|---|
| **Status** | 🔶 PARTIALLY IMPLEMENTED |
| **Actor** | Business owner |
| **Actions** | Invite team members, assign roles |
| **Input** | User email, role (owner/admin/staff) |
| **Output** | BusinessMember created with specified role |
| **Validation** | User exists or invitation sent, role valid, not already member |
| **Notes** | Basic member management exists. Future: granular permissions, Brain-specific permissions. |

**Currently implemented**:
- BusinessMember creation with roles (owner/admin/staff)
- Role hierarchy (owner=3 > admin=2 > staff=1)
- `require_business_role()` dependency for authorization

**Future**:
- Member invitation flow (email invitation → accept → join)
- Granular Brain permissions (BRAIN_VIEW, BRAIN_CREATE_RULE, BRAIN_APPROVE, etc.)
- Approval policy configuration per role
- Activity logging per member
- Member removal / role change

---

### Step 10: Business Brain Configuration

| Attribute | Detail |
|---|---|
| **Status** | 🔮 FUTURE |
| **Actor** | Business owner/admin (with AI assistance) |
| **Actions** | Configure Brain rules across all classifications |
| **Input** | Natural language instructions OR structured rule forms |
| **Output** | BrainVersion in DRAFT status with configured rules |
| **Validation** | Rule schema validation, conflict detection |
| **Notes** | This is the core Brain configuration step. AI assists via proposal pipeline. All changes require approval before activation. |

**Future workflow**:
```
Business owner describes how they operate (natural language)
    │
    ▼
AI proposes structured rules per classification
    │
    ▼
Owner reviews, edits, approves proposals
    │
    ▼
Rules added to DRAFT BrainVersion
    │
    ▼
Version validation → conflict detection
    │
    ▼
Owner satisfied → submit for review → approve → activate
```

**Alternatively**: Owner can configure rules manually through structured forms without AI assistance.

---

### Step 11: Review

| Attribute | Detail |
|---|---|
| **Status** | 🔮 FUTURE |
| **Actor** | Business owner |
| **Actions** | Review complete configuration before publishing |
| **Input** | Summary of all configuration |
| **Output** | Confirmation to proceed or return to edit |
| **Validation** | All required sections complete, at least one ACTIVE ServiceOffer |
| **Notes** | Pre-publish checklist ensuring business is ready to receive enquiries. |

**Review checklist**:
- [ ] Business identity complete
- [ ] Business profile complete with public_status = ACTIVE
- [ ] At least one ServiceOffer in ACTIVE status
- [ ] Pricing configured for all active offers
- [ ] Availability configured (when Brain available)
- [ ] Policies configured
- [ ] Brain version approved and active (when Brain available)
- [ ] At least one team member with owner role

---

### Step 12: Publish / Activate

| Attribute | Detail |
|---|---|
| **Status** | 🔶 PARTIALLY IMPLEMENTED |
| **Actor** | Business owner |
| **Actions** | Make business visible to customers |
| **Input** | Confirmation to publish |
| **Output** | BusinessProfile public_status → ACTIVE; ServiceOffers transitioned to ACTIVE |
| **Validation** | All review checklist items satisfied |
| **Notes** | Currently: individual status transitions exist. Future: coordinated publish flow that activates everything together. |

**Currently implemented**:
- BusinessProfile public_status can be set to ACTIVE
- ServiceOffer lifecycle transitions (DRAFT → ACTIVE)
- Business status column exists (PENDING → ACTIVE)

**Future**:
- Coordinated publish that activates profile + offers + Brain simultaneously
- Unpublish that pauses everything
- Business status transition logic (PENDING → ACTIVE → SUSPENDED → DEACTIVATED)

---

## Implementation Status Matrix

| Step | Component | Status | Dependency |
|---|---|---|---|
| 1 | Signup | ✅ IMPLEMENTED | — |
| 2 | Business creation | ✅ IMPLEMENTED | — |
| 3 | Business identity | ✅ IMPLEMENTED | — |
| 4 | Business profile | ✅ IMPLEMENTED | — |
| 5 | Service offers | ✅ IMPLEMENTED | — |
| 6 | Pricing (basic) | 🔶 PARTIAL | Brain for advanced |
| 7 | Availability | 🔮 FUTURE | Brain classification C |
| 8 | Policies (basic) | 🔶 PARTIAL | Brain for comprehensive |
| 9 | Team (basic) | 🔶 PARTIAL | Brain for granular permissions |
| 10 | Brain configuration | 🔮 FUTURE | Brain core implementation |
| 11 | Review checklist | 🔮 FUTURE | All above |
| 12 | Publish/Activate | 🔶 PARTIAL | Coordinated flow |

---

## Onboarding Principles

1. **Progressive disclosure**: Don't overwhelm — guide through steps sequentially
2. **Save progress**: Every step saves independently; owner can return later
3. **AI assistance available**: At every configuration step, AI can help (L3 — requires approval)
4. **No step skipped**: Each step has minimum requirements before proceeding
5. **Preview available**: Owner can preview how their business appears to customers
6. **No fake data**: Every piece of data is real — no placeholder content
7. **Brain is optional initially**: Business can start with basic configuration and add Brain rules later
