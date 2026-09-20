# FIELDed — Customer Journey Specification

> **Status**: SPECIFIED BUT NOT IMPLEMENTED (phases indicated per step)  
> **Phase**: Architecture + Specification Only  
> **Last Updated**: 2026-09-19

---

## Overview

This document specifies the complete customer-side journey on FIELDed, from anonymous visitor to completed service with review. Every step identifies its implementation status, required data, authorization, and failure states.

### Status Legend

| Status | Meaning |
|---|---|
| ✅ IMPLEMENTED | Functionally working in current codebase |
| 🔶 PARTIAL | Partially implemented, gaps identified |
| 📋 SPECIFIED | Specified but not yet implemented |
| 🔮 FUTURE | Not yet specified or implemented |

---

## Journey Map

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          CUSTOMER JOURNEY                                    │
│                                                                              │
│  [1] ANONYMOUS VISITOR                                                       │
│       │                                                                      │
│       ▼                                                                      │
│  [2] NATURAL-LANGUAGE DISCOVERY ──→ [3] BROWSE RESULTS                     │
│       │                                    │                                 │
│       ▼                                    ▼                                 │
│  [4] SERVICE OFFER SELECTION                                                   │
│       │                                                                      │
│       ▼                                                                      │
│  [5] AUTHENTICATION ──→ preserves discovery context                          │
│       │                                                                      │
│       ▼                                                                      │
│  [6] ENQUIRY CREATION ──→ [7] CONVERSATION                                  │
│                              │                                               │
│                              ▼                                               │
│                         [8] QUOTE/PROPOSAL                                   │
│                              │                                               │
│                              ▼                                               │
│                         [9] CUSTOMER ACCEPTANCE                              │
│                              │                                               │
│                              ▼                                               │
│                         [10] BOOKING PROPOSAL                                │
│                              │                                               │
│                              ▼                                               │
│                         [11] BOOKING CONFIRMED                               │
│                              │                                               │
│                              ▼                                               │
│                         [12] SERVICE IN PROGRESS                             │
│                              │                                               │
│                              ▼                                               │
│                         [13] COMPLETION                                      │
│                              │                                               │
│                              ▼                                               │
│                         [14] REVIEW ELIGIBILITY                              │
│                              │                                               │
│                              ▼                                               │
│                         [15] REVIEW SUBMITTED                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Step-by-Step Specification

### Step 1: Anonymous Visitor

| Attribute | Detail |
|---|---|
| **Status** | ✅ IMPLEMENTED |
| **Entry Condition** | User arrives at FIELDed without authentication |
| **Available Actions** | View landing page, browse public business profiles, search |
| **Required Data** | None |
| **Authorization** | None required |
| **Exit Condition** | User performs a search or navigates to a business profile |
| **Failure States** | Page load failure → error page |

**What exists**: Landing page, public business profile pages (`/business/[slug]`), search page.

---

### Step 2: Natural-Language Discovery

| Attribute | Detail |
|---|---|
| **Status** | 🔶 PARTIAL |
| **Entry Condition** | User enters natural language search query |
| **Available Actions** | Type search query, submit |
| **Required Data** | Search text (string) |
| **Authorization** | None required (anonymous access permitted) |
| **Exit Condition** | Search results displayed OR no results found |
| **Failure States** | AI interpretation fails → keyword fallback; No matching businesses → empty state |

**Pipeline**:
```
User: "I need a plumber in Leeds for a blocked drain"
    │
    ▼
DiscoveryInterpreter.interpret()
    │ StubAIProvider extracts: category=plumbing, location=Leeds
    ▼
DiscoveryIntent:
    {
        "intent": "service_search",
        "service_category": "plumbing",
        "location": "Leeds",
        "keywords": ["blocked drain"]
    }
    │
    ▼
DiscoveryMatchingService.match()
    │ Queries: ACTIVE businesses + ACTIVE ServiceOffers in plumbing category
    ▼
DiscoveryResult: [MatchedBusiness, ...]
```

**What exists**: StubAIProvider (keyword-based), DiscoveryInterpreter, DiscoveryMatchingService.  
**Gaps**: Real AI provider, semantic intent understanding, service area filtering (pass-through).

---

### Step 3: Browse Results

| Attribute | Detail |
|---|---|
| **Status** | 🔶 PARTIAL |
| **Entry Condition** | Discovery results returned from backend |
| **Available Actions** | View business cards, sort, filter, select a business |
| **Required Data** | DiscoveryResult from Step 2 |
| **Authorization** | None required |
| **Exit Condition** | User selects a business/service offer OR refines search |
| **Failure States** | No results → empty state with suggestions; Network error → retry prompt |

**Data available per result**:
- Business name, description, ratings
- Service offer name, description, pricing model
- Service category
- Location/service area

**What exists**: Backend returns structured results.  
**Gaps**: Ranking algorithm (currently simple match), sorting, filtering UI.

---

### Step 4: Service Offer Selection

| Attribute | Detail |
|---|---|
| **Status** | 🔶 PARTIAL |
| **Entry Condition** | User views a business profile or search result |
| **Available Actions** | View service offer details, select a service offer |
| **Required Data** | Business profile + active ServiceOffers |
| **Authorization** | None required (public data) |
| **Exit Condition** | User selects a specific ServiceOffer to enquire about |
| **Failure States** | No active offers → message business; Business not found → 404 |

**Data available per ServiceOffer**:
- Name, slug, description
- Delivery mode (on_site, remote, in_store)
- Pricing model + pricing_config
- Qualification requirements
- Booking rules
- Cancellation policy
- Service area

**What exists**: Public API for business profile + service offers by slug.  
**Gaps**: Service offer detail page, selection flow leading to enquiry.

---

### Step 5: Authentication (Context-Preserving)

| Attribute | Detail |
|---|---|
| **Status** | ✅ IMPLEMENTED |
| **Entry Condition** | User attempts action requiring authentication (enquire, message) |
| **Available Actions** | Login, Register, Continue as guest (where permitted) |
| **Required Data** | Email + password (login); Name, email, password (register) |
| **Authorization** | N/A — this IS the authorization step |
| **Exit Condition** | User authenticated with valid JWT tokens |
| **Failure States** | Invalid credentials → error; Account exists → login prompt; Rate limit → wait |

**Critical requirement**: Discovery context (search query, selected business, selected service offer) must be preserved across authentication. After login, user returns to the exact point they left off.

**Implementation approach**:
- Store discovery context in URL params or session storage
- After authentication, redirect to original destination with context preserved
- Do NOT lose the user's place in the journey

**What exists**: Register, login, logout, refresh, verify-email, forgot-password, reset-password. JWT tokens stored in localStorage.  
**Gaps**: Context preservation across auth redirect (frontend flow).

---

### Step 6: Enquiry Creation

| Attribute | Detail |
|---|---|
| **Status** | ✅ IMPLEMENTED |
| **Entry Condition** | Authenticated customer selects a ServiceOffer and initiates enquiry |
| **Available Actions** | Compose enquiry message, submit |
| **Required Data** | `business_id`, `service_offer_id`, `subject`, `message` |
| **Authorization** | `require_customer` — must have CustomerProfile |
| **Exit Condition** | Enquiry created with status DRAFT → SUBMITTED; Conversation created atomically |
| **Failure States** | Invalid business/offer → 404; Missing data → 400; Service not active → 422 |

**Atomic creation**: Enquiry + Conversation created in same database transaction. If either fails, both roll back.

**Enquiry data**:
```
{
    "business_id": UUID,
    "service_offer_id": UUID,
    "customer_id": UUID (from auth),
    "reference_number": "ENQ-XXXXXX",
    "subject": str,
    "message": str,
    "status": "SUBMITTED",
    "metadata": {}
}
```

**What exists**: Full enquiry creation with atomic conversation, reference number generation, status management.  
**Gaps**: AI-assisted enquiry drafting, qualification pre-check via Brain.

---

### Step 7: Conversation

| Attribute | Detail |
|---|---|
| **Status** | ✅ IMPLEMENTED |
| **Entry Condition** | Enquiry exists with active conversation |
| **Available Actions** | Send message, view message history, transition enquiry status |
| **Required Data** | Conversation ID, message content |
| **Authorization** | Customer: own conversations only; Business: own business enquiries only |
| **Exit Condition** | Enquiry progresses to QUOTED state |
| **Failure States** | Unauthorized access → 403; Invalid sender_type → 403; Enquiry in terminal state → 422 |

**Message model**:
```
{
    "conversation_id": UUID,
    "sender_id": UUID,
    "sender_type": "customer" | "business",
    "content": str,
    "message_type": "text" | "system" | "image" (future),
    "delivered_at": datetime,
    "read_at": datetime | null
}
```

**Server-side validation**: sender_type verified against authenticated identity. Customer cannot impersonate business; business cannot impersonate customer.

**What exists**: Message sending, listing, conversation retrieval, sender validation, enquiry status transitions during conversation.  
**Gaps**: Read receipts, typing indicators, file attachments, AI-assisted message drafting.

---

### Step 8: Quote/Proposal

| Attribute | Detail |
|---|---|
| **Status** | 📋 SPECIFIED BUT NOT IMPLEMENTED |
| **Entry Condition** | Business has sufficient information to provide a quote |
| **Available Actions** | Business creates quote; Customer views quote |
| **Required Data** | Enquiry ID, line items, total price, validity period, terms |
| **Authorization** | Business: `require_business_role("staff")` for own enquiries; Customer: view own quotes only |
| **Exit Condition** | Quote sent to customer; Enquiry transitions to QUOTED |
| **Failure States** | Invalid data → 400; Unauthorized → 403; Enquiry not in quotable state → 422 |

**Quote structure** (proposed):
```
Quote
├── id: UUID
├── enquiry_id: UUID FK
├── business_id: UUID FK
├── customer_id: UUID FK
├── items: QuoteItem[] (description, quantity, unit_price, total)
├── subtotal: number
├── tax: number
├── total: number
├── currency: str
├── validity_days: int
├── terms: str
├── status: DRAFT | SENT | VIEWED | ACCEPTED | REJECTED | EXPIRED
├── brain_version_id: UUID (governing pricing rules)
├── created_by: UUID
├── created_at: datetime
└── expires_at: datetime
```

**Brain integration**: Quote creation evaluates Pricing classification rules. If Brain requires approval for quotes above threshold, quote enters REQUIRE_APPROVAL state.

**What exists**: Quote entity mentioned in domain model docs.  
**Gaps**: Full Quote model, service, API, state machine, Brain pricing integration.

---

### Step 9: Customer Acceptance

| Attribute | Detail |
|---|---|
| **Status** | 📋 SPECIFIED BUT NOT IMPLEMENTED |
| **Entry Condition** | Customer receives a quote |
| **Available Actions** | Accept quote, Reject quote, Request modification (via conversation) |
| **Required Data** | Quote ID, acceptance/rejection decision |
| **Authorization** | `require_customer` — only the quote's customer can accept/reject |
| **Exit Condition** | Quote ACCEPTED → Enquiry transitions to CUSTOMER_ACCEPTED; Quote REJECTED → Enquiry transitions to REJECTED |
| **Failure States** | Quote expired → 422; Not customer's quote → 403; Quote not in SENT/VIEWED state → 422 |

**Acceptance flow**:
```
Customer accepts quote
    │
    ▼
Validate: Quote belongs to customer, quote is in SENT/VIEWED state, not expired
    │
    ▼
Quote status → ACCEPTED
    │
    ▼
Enquiry status → CUSTOMER_ACCEPTED
    │
    ▼
Brain evaluates: Does this enquiry proceed to booking?
    │ (Booking classification rules)
    ▼
If booking required → Booking proposal flow
If no booking needed → Enquiry can proceed to COMPLETED directly
```

---

### Step 10: Booking Proposal

| Attribute | Detail |
|---|---|
| **Status** | 📋 SPECIFIED BUT NOT IMPLEMENTED |
| **Entry Condition** | Quote accepted; Brain rules indicate booking is required/appropriate |
| **Available Actions** | Business proposes time slot; Customer accepts/declines/reschedules |
| **Required Data** | Enquiry ID, proposed date/time, duration, location |
| **Authorization** | Business: propose; Customer: accept/decline own bookings |
| **Exit Condition** | Booking created with status REQUESTED/PROPOSED |
| **Failure States** | Time slot unavailable → reject; Customer not qualified → reject; Conflict with Brain rules → escalate |

**Booking proposal flow**:
```
Business proposes booking
    │
    ▼
Brain evaluates Availability classification:
    ├── Is the proposed time within operating hours?
    ├── Does it satisfy minimum notice?
    ├── Is there capacity?
    └── Does it conflict with existing bookings?
    │
    ▼
If all checks pass → Booking created (status: PROPOSED)
    │
    ▼
Customer receives proposal
    │
    ▼
Customer accepts → Booking status: ACCEPTED → CONFIRMED
Customer declines → Booking status: DECLINED
Customer requests reschedule → New proposal cycle
```

**Booking state machine**:
```
REQUESTED → PROPOSED → ACCEPTED → CONFIRMED → IN_PROGRESS → COMPLETED
                                                      │
                                          DECLINED ←──┤
                                          CANCELLED ←─┤
                                          EXPIRED ←───┤
                                          RESCHEDULED ┤
                                          NO_SHOW ←───┘
```

---

### Step 11: Booking Confirmed

| Attribute | Detail |
|---|---|
| **Status** | 📋 SPECIFIED BUT NOT IMPLEMENTED |
| **Entry Condition** | Customer accepts booking proposal |
| **Available Actions** | View booking details, prepare for service |
| **Required Data** | Booking with CONFIRMED status |
| **Authorization** | Customer: own bookings; Business: own business bookings |
| **Exit Condition** | Service start time arrives OR business marks IN_PROGRESS |
| **Failure States** | Booking cancelled by either party → CANCELLED state |

**Notifications** (FUTURE):
- Confirmation sent to customer (email/SMS)
- Confirmation sent to business
- Reminder sent before service time (per Communication classification)

---

### Step 12: Service In Progress

| Attribute | Detail |
|---|---|
| **Status** | 📋 SPECIFIED BUT NOT IMPLEMENTED |
| **Entry Condition** | Business begins service delivery |
| **Available Actions** | Business updates progress; Customer views status |
| **Required Data** | Booking/Enquiry in IN_PROGRESS state |
| **Authorization** | Business: update own bookings; Customer: view own |
| **Exit Condition** | Business marks service as complete |
| **Failure States** | Service cannot be completed → ESCALATE; Customer cancels → CANCELLED |

**Brain integration**: Fulfilment classification (K) defines completion criteria. Business Brain may require evidence before completion is permitted.

---

### Step 13: Completion

| Attribute | Detail |
|---|---|
| **Status** | 📋 SPECIFIED BUT NOT IMPLEMENTED |
| **Entry Condition** | Business marks service as complete |
| **Available Actions** | Business confirms completion; System validates against Brain rules |
| **Required Data** | Completion confirmation, evidence (if required by Brain) |
| **Authorization** | Business: `require_business_role("staff")` for own bookings |
| **Exit Condition** | Enquiry/Booking status → COMPLETED |
| **Failure States** | Completion criteria not met → DENY; Missing evidence → REQUIRE_INFORMATION |

**Completion validation**:
```
Business marks complete
    │
    ▼
Brain evaluates Fulfilment classification (K):
    ├── Are completion criteria satisfied?
    ├── Is required evidence provided?
    ├── Do quality gates pass?
    └── Is handover confirmed?
    │
    ▼
If all satisfied → Status → COMPLETED
If not → REQUIRE_INFORMATION or DENY
```

---

### Step 14: Review Eligibility

| Attribute | Detail |
|---|---|
| **Status** | 🔮 FUTURE |
| **Entry Condition** | Enquiry/Booking in COMPLETED state |
| **Available Actions** | System determines if customer can review |
| **Required Data** | Completed transaction reference |
| **Authorization** | System-evaluated (deterministic) |
| **Exit Condition** | Customer marked as eligible/not eligible for review |
| **Failure States** | Not eligible → no review option shown |

**Eligibility rules** (deterministic, NOT AI-controlled):
- Transaction must be in COMPLETED state
- Customer must be the original enquirer
- No prior review exists for this transaction
- Review window has not expired (configurable, default: 30 days)
- Customer account is in good standing (not suspended)

**Critical**: Review eligibility is determined by deterministic rules, not AI judgment. This prevents manipulation.

---

### Step 15: Review Submission

| Attribute | Detail |
|---|---|
| **Status** | 🔮 FUTURE |
| **Entry Condition** | Customer is review-eligible |
| **Available Actions** | Submit rating (1-5), write review text |
| **Required Data** | Transaction reference, rating (1-5), review text |
| **Authorization** | `require_customer` — only eligible customer can review |
| **Exit Condition** | Review submitted; Business rating aggregated |
| **Failure States** | Not eligible → 403; Invalid rating → 400; Review window expired → 422 |

**Review structure** (proposed):
```
Review
├── id: UUID
├── enquiry_id: UUID FK
├── booking_id: UUID FK | null
├── customer_id: UUID FK
├── business_id: UUID FK
├── service_offer_id: UUID FK
├── rating: int (1-5)
├── review_text: str
├── status: SUBMITTED | VISIBLE | HIDDEN | FLAGGED
├── submitted_at: datetime
└── moderated_at: datetime | null
```

---

## Failure + Edge Case Handling

| Scenario | Handling |
|---|---|
| Customer abandons journey at any point | Enquiry remains in current state; Expiration rules apply per Brain |
| Authentication expires mid-journey | Re-authentication required; Context preserved via URL/session |
| Business doesn't respond | Escalation per Brain (J); Auto-expire per Brain policy |
| Quote expires | Quote status → EXPIRED; Customer notified; Enquiry can remain active |
| Booking cancelled by business | Cancellation policy applied (Brain E/G); Refund if applicable |
| Customer no-show | Brain rules determine NO_SHOW handling |
| Dispute after completion | Escalation flow; Review can be flagged; Human mediation |
| Business goes offline | Enquiries paused; Customers notified; New enquiries blocked |

---

## Data Flow Summary

```
Customer Input
    │
    ├── Discovery Intent (AI-interpreted, schema-validated)
    │
    ├── Enquiry (customer-authored message)
    │
    ├── Conversation Messages (customer + business)
    │
    ├── Quote (business-authored, Brain-validated pricing)
    │
    ├── Booking Proposal (business-proposed, Brain-validated availability)
    │
    ├── Completion (business-confirmed, Brain-validated criteria)
    │
    └── Review (customer-authored, eligibility-verified)
```

---

## Implementation Status Summary

| Step | Feature | Status |
|---|---|---|
| 1 | Anonymous browsing | ✅ IMPLEMENTED |
| 2 | Natural-language search | 🔶 PARTIAL (stub AI) |
| 3 | Browse results | 🔶 PARTIAL (basic results) |
| 4 | Service offer selection | 🔶 PARTIAL (public API exists) |
| 5 | Authentication | ✅ IMPLEMENTED |
| 6 | Enquiry creation | ✅ IMPLEMENTED |
| 7 | Conversation/messaging | ✅ IMPLEMENTED |
| 8 | Quote/proposal | 📋 SPECIFIED |
| 9 | Customer acceptance | 📋 SPECIFIED |
| 10 | Booking proposal | 📋 SPECIFIED |
| 11 | Booking confirmation | 📋 SPECIFIED |
| 12 | Service in progress | 📋 SPECIFIED |
| 13 | Completion | 📋 SPECIFIED |
| 14 | Review eligibility | 🔮 FUTURE |
| 15 | Review submission | 🔮 FUTURE |
