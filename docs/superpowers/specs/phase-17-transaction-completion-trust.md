# Phase 17 — Customer Transaction Completion + Trust + Settings

## 1. Objective

Complete the customer-to-business transaction lifecycle and close the remaining Business Network gaps without redesigning existing architecture.

Target lifecycle:

**Discover → Business Profile → Service Offer → Enquiry → Conversation → Quote → Accept → Booking → Payment where required → Confirmed Booking → Service → Completion → Review**

At the same time, complete the missing Business Settings experience using existing domain capabilities.

---

## 2. Existing Architecture — Preserve

Before changing anything, inspect and reuse the existing implementations for:

- User / CustomerProfile
- Business / BusinessProfile
- BusinessMember / roles / authorization
- ServiceCategory / ServiceOffer
- Enquiry / Conversation / Message
- Quote
- Booking
- ServiceExecution
- Invoice / InvoiceLineItem
- Financial Ledger
- Payment / PaymentAttempt
- Stripe provider / webhook
- Communications / Outbox
- Notifications
- Business Brain / BrainVersion
- AvailabilityEvaluator
- Audit infrastructure
- Public Business Network / Discovery

**No parallel domain workflows.**

---

## 3. Phase 17 Gap Analysis

### 3.1 Verified Existing Implementation

The full transaction state machine already exists in `enums.py`:

```
EnquiryStatus:  DRAFT → SUBMITTED → RECEIVED → IN_REVIEW → QUOTED → CUSTOMER_ACCEPTED → BOOKING_PROPOSED → BOOKED → IN_PROGRESS → COMPLETED
QuoteStatus:    DRAFT → ISSUED → ACCEPTED / DECLINED / EXPIRED
BookingStatus:  REQUESTED → PROPOSED → ACCEPTED → CONFIRMED → IN_PROGRESS → COMPLETED
ServiceExec:    SCHEDULED → IN_PROGRESS → COMPLETED + CANCELLED / NO_SHOW
PaymentStatus:  PENDING → PROCESSING → SUCCEEDED → REFUNDED / PARTIALLY_REFUNDED
```

**Already working transitions (no changes needed):**
- Enquiry → QUOTED: `quote/service.py:157`
- Quote acceptance: `quotes.py:155-168` (customer transition endpoint)
- Quote → Booking: `booking/service.py:72-209` (creates from accepted quote)
- Booking → Enquiry BOOKED: `booking/service.py:248-252`
- Booking → Enquiry COMPLETED: `booking/service.py:255-259`
- Booking → Service Execution: `service_execution/service.py:75-125`
- Execution → Invoice + Ledger: `service_execution/service.py:325-466` (idempotent)
- Outbox events: all services emit on transition
- Tenant isolation: all endpoints verify ownership server-side
- Brain evaluation: `enquiry/service.py:523-608`

### 3.2 Identified Gaps

| # | Gap | Severity | Resolution |
|---|-----|----------|------------|
| G1 | No Review domain — only `average_rating`/`review_count` aggregates | Critical | New `app/domain/review/` with model, eligibility, API, migration |
| G2 | Service-detail → enquiry routing broken — public API doesn't expose `business_id` | Critical | Add `business_id` to public response; fix frontend to use existing enquiry API |
| G3 | No customer-initiated payment flow — only business-initiated | Critical | See §4.3 (payment timing analysis) |
| G4 | Customer dashboard is a stub ("Coming in Phase 03") | Critical | Replace with real transaction view |
| G5 | Business settings page is empty (8-line placeholder) | Moderate | Build settings UI using existing backend APIs |
| G6 | No public availability endpoint for customers | Moderate | Add public endpoint reusing `AvailabilityEvaluator` |
| G7 | Customer payment endpoint must reuse existing invoice outstanding-balance validation | Moderate | Reuse existing `PaymentService.create_payment()`; no new financial calculation |
| G8 | Service execution completion doesn't cascade to booking/enquiry | Moderate | Add cascade in `service_execution/service.py` |
| G9 | No member management UI | Moderate | Add to business settings using existing `BusinessMember` infrastructure |

---

## 4. Implementation Specification

### 4.1 G1 — Review Domain (Trust Layer)

#### Review Trust Model

A review is trustworthy because it is attached to an actual FIELDed transaction:

```
Completed ServiceExecution
        +
Valid Booking (not cancelled/declined)
        +
Correct Customer (owns the transaction)
        +
Correct Business (owns the execution)
        +
No existing review (UNIQUE constraint)
        ↓
Review eligible
```

Eligibility is **deterministic**. AI never determines review eligibility.

#### Model

```text
reviews table:
  id                    UUID PK
  business_id           UUID FK → businesses (CASCADE)
  customer_id           UUID FK → users (RESTRICT)
  service_execution_id  UUID FK → service_executions (RESTRICT), UNIQUE
  booking_id            UUID FK → bookings (RESTRICT)
  enquiry_id            UUID FK → enquiries (RESTRICT)
  service_offer_id      UUID FK → service_offers (RESTRICT)
  rating                INTEGER NOT NULL (1-5)
  title                 VARCHAR(200) NULL
  body                  TEXT NULL
  status                VARCHAR(50) NOT NULL DEFAULT 'visible'
  response_body         TEXT NULL
  responded_at          TIMESTAMPTZ NULL
  responded_by          UUID FK → users NULL
  created_at            TIMESTAMPTZ
  updated_at            TIMESTAMPTZ
  deleted_at            TIMESTAMPTZ NULL (soft-delete consistent with BaseModel)

  UNIQUE(service_execution_id) — one review per completed service
  INDEX(business_id, status)
  INDEX(customer_id)
```

#### Eligibility Rules (deterministic, in service.py)

1. Service execution must exist and be `COMPLETED`
2. Execution must NOT be `CANCELLED` or `NO_SHOW`
3. Customer must own the review (`customer_id == execution.customer_id`)
4. Business must match (`business_id == execution.business_id`)
5. Linked booking must NOT be `CANCELLED` or `DECLINED`
6. Linked enquiry must NOT be `DECLINED` or `CANCELLED`
7. No existing review for this execution (UNIQUE constraint)

#### Rating Aggregation

On review creation, recalculate `BusinessProfile.average_rating` and `review_count` using `AVG(rating)` and `COUNT(*)` across all visible reviews for the business. Database-driven, deterministic.

#### API Endpoints

```text
POST /my-reviews                              — Submit review (require_customer)
GET  /my-reviews                              — List customer's reviews
GET  /my-reviews/{id}                         — Get specific review
GET  /public/business/{slug}/reviews          — Public reviews for a business
POST /{business_id}/reviews/{id}/respond      — Business response (require_business_member)
```

#### Audit Events

- `REVIEW_SUBMITTED`
- `REVIEW_RESPONDED`

#### Files

- `backend/app/domain/review/__init__.py`
- `backend/app/domain/review/models.py`
- `backend/app/domain/review/schemas.py`
- `backend/app/domain/review/repository.py`
- `backend/app/domain/review/service.py`
- `backend/app/api/v1/reviews.py`
- `backend/alembic/versions/014_phase17_reviews.py`

---

### 4.2 G2 — Fix Service Detail → Enquiry

The existing Phase 16 service detail page redirects to a non-existent `/customer/enquiries/new` route because the public API doesn't expose `business_id`.

#### Backend Fix (`public.py`)

Add the minimum business identifier required by the existing enquiry API to the public response schema, following the existing public schema pattern.

Do not duplicate or expose additional internal business fields.

The identifier must allow the authenticated customer enquiry flow to resolve the selected business without introducing a second lookup/workflow.

For the service offer:

The public service-offer response must expose the minimum business identifier required to create an enquiry through the existing `EnquiryService`/API.

Follow the existing public schema conventions rather than assuming a particular inheritance structure.

#### Frontend Fix (`service/[offerSlug]/page.tsx`)

Replace the broken redirect with direct enquiry creation:

1. User clicks "Start Enquiry"
2. If not authenticated → redirect to login with return URL
3. If authenticated → show inline enquiry form (or navigate to customer enquiry flow with pre-filled context)
4. On submit → `POST /api/v1/enquiries/{business_id}/enquiries` with `service_offer_id` from loaded service detail
5. On success → redirect to `/customer/enquiries/{id}` (existing detail page)

Uses the **existing** `EnquiryService.create_enquiry()` — no new enquiry workflow.

---

### 4.3 G3 — Customer Payment Flow

#### Payment Timing Analysis

Inspection of the existing lifecycle reveals:

```text
Booking (CONFIRMED)
    ↓
ServiceExecution (created from confirmed booking)
    ↓
ServiceExecution (COMPLETED) → Invoice created atomically
    ↓
Payment (against invoice)
```

**The existing architecture is POST-SERVICE payment.** Invoices are created during service execution completion (`service_execution/service.py:325-466`). A confirmed booking does NOT have an invoice. The `PaymentService.create_payment()` requires an `invoice_id`.

This is the authoritative existing lifecycle. Phase 17 implements the customer payment flow against this lifecycle.

#### Customer Payment Endpoint

```text
POST /my-bookings/{booking_id}/pay
  Auth: require_customer
  Body: { payment_method: str, idempotency_key: str }
```

The exact router/module placement must follow the existing API convention after inspection. Do not create a parallel customer-payment router solely to satisfy this proposed path.

Reuse the existing payments/payment service architecture and authorization patterns.

Logic:
1. Verify customer owns the booking
2. Find the booking's service execution
3. Find the invoice for the execution (created at completion)
4. If no invoice exists (service not yet completed) → reject with "Payment not yet available — service must be completed first"
5. Validate payment amount matches invoice outstanding balance
6. Create payment via existing `PaymentService.create_payment()`
7. Auto-process via existing flow

#### Payment Amount Validation (G7)

The existing `PaymentService.create_payment()` already validates:
- Amount > 0
- Currency matches invoice
- Amount ≤ outstanding balance (invoice total - net paid + refunds)

This is the **one authoritative financial calculation**. No duplicate needed.

What's missing is the customer-facing endpoint that resolves the booking → execution → invoice chain.

#### Constraints

- Reuse existing `PaymentService`, `InvoiceService`, Stripe adapter
- Preserve idempotency (idempotency_key unique constraint)
- Preserve tenant isolation
- Do not create a second invoice/payment system

---

### 4.4 G4 — Customer Transaction Experience

Replace the customer dashboard stub with a real transaction view.

#### Dashboard (`customer/dashboard/page.tsx`)

Summary cards:
- Active enquiries count
- Upcoming bookings count
- Pending payments (invoices with outstanding balance)
- Completed services count

Recent activity (last 2-3 items, not an infinite feed — see §6):
- Most recent enquiry/booking/payment status

Quick actions:
- Browse network
- View enquiries
- View bookings

#### Transaction History (`customer/transactions/page.tsx`)

Unified list showing the linked chain:

```text
Service Offer → Enquiry → Quote → Booking → Payment → Service → Review
```

Each row:
- Service offer name
- Enquiry reference + status
- Quote amount (if quoted)
- Booking status + date
- Payment status (if invoiced)
- Service execution status
- Review status (submitted / eligible / not yet)

Links to authoritative domain entity detail pages.

---

### 4.5 G5 — Business Settings

Build the settings page using existing backend capabilities.

#### Identity Tab

- Business name, slug, description
- Contact info (phone, email)
- Public visibility (`public_status`)
- Service area
- Logo URL, cover image URL
- Social links (website, facebook, instagram, linkedin)

Uses existing `PUT /businesses/{id}/profile` API.

#### Members Tab

- Member list (name, email, role)
- Invite member (by email, with role)
- Role changes
- Remove/deactivate member

Uses existing `BusinessMember` model. If invitation infrastructure doesn't exist yet, add the minimum required:
- `POST /businesses/{id}/members/invite` — create pending member invitation
- `POST /members/accept-invitation/{token}` — accept and activate membership
- Email notification for invitations (invited person may not be on FIELDed yet)

**Do not create a parallel membership/invitation/RBAC subsystem.**

#### Communications Tab

Expose existing communication configuration:
- Channel preferences
- Template overview (read-only link to full communications page)

Do not duplicate Business Brain rules.

#### Payments Tab

Expose existing payment status:
- Payment provider configured (yes/no)
- Recent payment summary (link to full payments page)

#### Security Tab

- Account settings link
- Password change (if endpoint exists)

#### Boundary: Settings ≠ Brain

Settings manage **identity/account/integration preferences**. Business Brain manages **operational rules**:
- pricing, availability, qualification
- booking rules, cancellation, rescheduling
- payment requirements, escalation, operational policies

No duplication.

---

### 4.6 G6 — Public Availability

Add customer-safe public availability endpoint.

```text
GET /public/business/{slug}/availability?service_offer_id={id}
  Auth: none (public)
  Response: { available: bool, next_available: datetime | null, lead_time_hours: int | null }
```

Logic:
1. Resolve business by slug (existing pattern)
2. Verify service offer is ACTIVE
3. Use existing `AvailabilityEvaluator` with the service offer + brain version
4. Return only customer-safe information
5. Never expose raw Brain rules, internal staff info, or JSONB config

Reuses existing `AvailabilityEvaluator` — does not create a second availability engine.

---

### 4.7 G8 — Service Completion Cascade

When a service execution completes, cascade to booking and enquiry:

```text
ServiceExecution → COMPLETED
       ↓
Booking → COMPLETED (via existing BookingService.transition_booking)
       ↓
Enquiry → COMPLETED (already handled in booking/service.py:255-259)
       ↓
Review becomes eligible (via G1 eligibility check)
```

Implementation in `service_execution/service.py`:
- After execution transitions to COMPLETED
- Load the linked booking
- If booking is IN_PROGRESS or CONFIRMED, transition to COMPLETED via `BookingService.transition_booking()`
- This cascades to enquiry automatically

Ensure idempotency — if booking is already COMPLETED, skip.

---

### 4.8 G9 — Business Dashboard Enhancement

Enhance the existing dashboard with real data:

- Active enquiries (already shown)
- Pending quotes count
- Upcoming bookings count
- Active service executions count
- Pending payments / revenue summary
- Recent activity (last 2-3 events, not infinite feed)
- Quick actions

Uses existing authoritative data from domain services. No duplicate analytics calculations.

---

## 5. Audit Trail

### Principle: Audit is implemented alongside each feature, not as a final retrofit.

Each work stream includes its own audit integration:
- Review → review audit events
- Payment → payment audit events
- Settings → settings audit events
- Members → member audit events
- Completion cascade → completion audit events
- Notifications → corresponding outbox/event entries

Step 13 in the implementation order is **audit coverage verification only** — confirming all Phase 17 events are covered, not implementing them.

### Backend Audit

Use the existing audit-event mechanism and existing `AuditEventType` definitions. Where audit events are propagated through the existing outbox/event infrastructure, follow that established pattern. Do not create a second audit mechanism.

At minimum:
- Review submission / response
- Booking state changes (already exists)
- Payment state changes (already exists)
- Service completion + cascade
- Business settings changes
- Member invitation / role change / removal
- Communication setting changes

Do **not** create a new audit subsystem.

### Audit vs UI Activity

```text
Domain Action
      ↓
Authoritative Audit Event
      ↓
 ┌───────────────┐
 ↓               ↓
Notification    UI Activity
```

**Backend audit** records are persistent per retention policy. They record actor, tenant, entity, action, timestamp, state, provenance.

**UI activity** shows only:
- A small number of recent events (2-3)
- Or a short recent time window
- Does not continuously accumulate historical activity

Older events disappear from normal UI surfaces while remaining in the authoritative audit infrastructure.

Do not build a global audit explorer as part of Phase 17.

---

## 6. Contextual History

Where operational history is genuinely useful, show it contextually and human-readable:

**Booking:** "Booking confirmed → Customer accepted quote → Booking proposed"

**Member:** "Member invited → Role changed → Member deactivated"

**Payment:** "Payment initiated → Payment succeeded → Refund issued"

**Review:** "Review submitted → Business response added"

Do not expose raw database audit payloads to ordinary users.

---

## 7. Notifications

Use the **existing communications/outbox/notification infrastructure**. Do not create a separate notification system.

Important events that should generate notifications:
- Member invitation (email — invited person may not be on FIELDed)
- Role change / membership removal (transactional notifications, including email where permitted by existing communication policy/configuration, with in-app notification for active users where supported)
- Booking confirmation
- Quote acceptance
- Payment success/failure
- Review submission
- Review response

Architecture:

```
Authoritative Domain Action
        ↓
Existing Audit/Event Mechanism
        ↓
Existing Outbox/Event Infrastructure
        ↓
Notification where applicable
```

The authoritative domain action must produce its existing audit/event record.

Notifications must derive from the established event/outbox mechanism where applicable.

Do not introduce a new synchronous Action → Audit → Notification pipeline.
Do not create a parallel notification or audit subsystem.

The UI activity model remains:

```
Backend Audit
    ↓
Recent / contextual UI activity

UI activity is not the audit system.
```

### Notification Retention

Normal UI surfaces recent/unread notifications. Historical audit records remain separate. Do not allow notifications to become an infinite activity feed.

---

## 8. Authorization & Tenant Isolation

Every new endpoint and UI action must verify:
- Authenticated user
- Correct customer/business relationship
- Business membership + appropriate role
- Resource ownership
- Tenant/business isolation

Especially verify for: reviews, payments, member management, settings, public availability, booking access.

Never rely solely on frontend restrictions.

---

## 9. Communications Continuity

Verify Phase 17 events integrate with existing:
- Communication policy
- Customer preferences
- Suppression/DNC
- Transactional outbox
- Provider adapters
- Audit/provenance

Do not bypass existing communications governance.

---

## 10. Testing

### Unit Tests

**Reviews (`test_phase17_reviews.py`):**
- Eligible completed transaction → review succeeds
- Cancelled execution → review rejected
- Incomplete service → review rejected
- Wrong customer → rejected
- Wrong business → rejected
- Duplicate review → rejected
- Rating 1-5 valid, 0/6 rejected
- Rating aggregation correctness
- Business response: authorized → allowed, non-member → rejected

**Transaction Flow (`test_phase17_transaction_flow.py`):**
- Service execution completion cascades to booking COMPLETED
- Booking COMPLETED cascades to enquiry COMPLETED
- Payment amount validation against invoice
- Payment amount mismatch → rejected

### Integration Tests

**Transaction (`test_phase17_transaction.py`):**
- Full happy path: enquiry → quote → accept → booking → execution → complete → review
- Cancelled enquiry → no review allowed
- Cross-tenant review attempt → rejected
- Public review retrieval
- Slug-to-ID resolution for enquiry creation
- Customer payment against invoice
- Failed payment → no confirmation

**Availability (`test_phase17_availability.py`):**
- Public availability returns safe data
- Does not expose Brain internals
- Respects existing deterministic evaluator

**Members:**
- Invitation authorization
- Role authorization
- Removal/deactivation
- Tenant isolation

### Regression

- Run targeted Phase 17 unit/security/integration tests and directly affected existing tests
- **Do not run the full backend unit/security/regression suites unless explicitly requested**
- Run `npx next build` — frontend must compile

### Execution Discipline

After each implementation step, run only the targeted tests directly affected by that step and any directly affected existing tests.

Do not accumulate unrelated test execution into intermediate steps.

Do not run the full backend unit/security/regression suites unless explicitly requested.

---

## 11. Deferred Items

Do not pull unrelated deferred work into Phase 17:
- Physical/live Stripe transaction testing
- Stripe.js frontend confirmation
- Externally reachable Stripe webhook testing
- True geographic distance calculation
- Replacement of StubAIProvider with a production LLM
- Advanced business-hours management
- Customer notification-preference UI
- WebSocket/streaming voice
- Review moderation/flagging
- Internationalization
- Advanced analytics

---

## 12. Implementation Order

```text
1. Inspect existing lifecycle/infrastructure (DONE — this spec)
        ↓
2. Enums + migration (Review table, audit events)
        ↓
3. Review domain (model, schemas, repository, service with eligibility)
        ↓
4. Review API (router, endpoints, mount)
        ↓
5. Fix service-detail → enquiry (public API + frontend)
        ↓
6. Customer payment endpoint (at correct lifecycle point — post-service)
        ↓
7. Service completion cascade (execution → booking → enquiry)
        ↓
8. Public availability (reuse existing evaluator)
        ↓
9. Customer dashboard + transaction history
        ↓
10. Business settings shell + existing capabilities
        ↓
11. Member management/invitation backend + UI where genuinely missing
        ↓
12. Complete settings integration
        ↓
13. Business dashboard enhancement
        ↓
14. Audit + notification coverage verification
        ↓
15. Targeted tests
        ↓
16. Frontend build verification
```

**Step 14 is verification only.** Audit and notification integration must be implemented alongside the relevant features, not postponed until Step 14.

---

## 13. Implementation Rules

1. **Additive changes only.**
2. Reuse existing domain services.
3. Reuse existing repositories.
4. Reuse existing authorization/RBAC.
5. Reuse existing Business Brain.
6. Reuse existing AvailabilityEvaluator.
7. Reuse existing payment/invoice logic.
8. Reuse existing communications/outbox.
9. Reuse existing audit infrastructure.
10. Reuse existing member/invitation infrastructure.
11. No duplicate state machines.
12. No duplicate business-rule engines.
13. No duplicate payment/invoice calculations.
14. No parallel notification system.
15. No new audit subsystem.
16. AI never becomes authoritative for deterministic business decisions.
17. Preserve tenant isolation.
18. Preserve idempotency.
19. Make the smallest architectural change necessary to close each genuine gap.
20. Before implementing where existing architecture is ambiguous, **inspect first and follow the existing authoritative pattern.**

---

## 14. Settings Completeness Matrix

### Business Identity
| Capability | Backend | Frontend | Status |
|-----------|---------|----------|--------|
| Business profile | `PUT /businesses/{id}/profile` | `/business/profile` | ✓ |
| Public visibility | `public_status` field | Profile page | ✓ |
| Contact info | Profile API | Profile page | ✓ |
| Service areas | `service_area` JSONB | Profile page | ✓ |
| Categories | Via ServiceOffer | Services page | ✓ |
| Logo/cover/social | URL fields | Profile page | ✓ |

### Services
| Capability | Backend | Frontend | Status |
|-----------|---------|----------|--------|
| Service Offers CRUD | `service_offers` API | `/business/services` | ✓ |
| Pricing | `pricing_config` | Services page | ✓ |
| Availability | Brain rules | Brain page | △ Brain-governed |
| Booking rules | Brain rules | Brain page | △ Brain-governed |

### Members
| Capability | Backend | Frontend | Status |
|-----------|---------|----------|--------|
| Member list | `BusinessMember` model | **No UI** | △ Settings |
| Invite member | May need endpoint | **No UI** | △ Settings |
| Role changes | May need endpoint | **No UI** | △ Settings |
| Remove member | May need endpoint | **No UI** | △ Settings |

### Trust
| Capability | Backend | Frontend | Status |
|-----------|---------|----------|--------|
| Reviews | **Phase 17 new** | **Phase 17 new** | △ This phase |
| Rating aggregates | `average_rating` on profile | Network page | ✓ |
| Review eligibility | **Phase 17 new** | N/A | △ This phase |

---

## 15. Files Summary

### New Files

| File | Purpose |
|------|---------|
| `backend/app/domain/review/__init__.py` | Package init |
| `backend/app/domain/review/models.py` | Review model |
| `backend/app/domain/review/schemas.py` | Pydantic schemas |
| `backend/app/domain/review/repository.py` | Data access |
| `backend/app/domain/review/service.py` | Business logic + eligibility |
| `backend/app/api/v1/reviews.py` | API endpoints |
| `backend/alembic/versions/014_phase17_reviews.py` | Migration |
| `backend/tests/unit/test_phase17_reviews.py` | Review unit tests |
| `backend/tests/unit/test_phase17_transaction_flow.py` | Transaction flow tests |
| `backend/tests/integration/test_phase17_transaction.py` | Integration tests |
| `backend/tests/integration/test_phase17_availability.py` | Availability tests |
| `frontend/src/app/(customer)/customer/transactions/page.tsx` | Unified transaction history |

### Modified Files

| File | Change |
|------|--------|
| `backend/app/domain/common/enums.py` | Add REVIEW_SUBMITTED, REVIEW_RESPONDED audit events |
| `backend/app/api/v1/public.py` | Add business_id to responses; public availability; public reviews |
| `backend/app/api/v1/payments.py` | Add customer payment endpoint |
| `backend/app/api/router.py` | Mount reviews router |
| `backend/app/domain/service_execution/service.py` | Add booking completion cascade |
| `backend/tests/conftest.py` | Import Review model |
| `frontend/src/lib/api-client.ts` | Add review, availability, payment API functions |
| `frontend/src/app/(public)/business/[slug]/services/[offerSlug]/page.tsx` | Fix enquiry creation |
| `frontend/src/app/(customer)/customer/dashboard/page.tsx` | Replace stub |
| `frontend/src/app/(business)/business/dashboard/page.tsx` | Enhance metrics |
| `frontend/src/app/(business)/business/settings/page.tsx` | Build settings UI |

---

## 16. Completion Gate

> A customer can discover a service, enquire, communicate, receive and accept a quote, book, pay when required, receive the service, have the service completed, and then submit a valid review — while the business can manage the corresponding lifecycle and every important transition remains authorized, deterministic, tenant-safe, and auditable.
