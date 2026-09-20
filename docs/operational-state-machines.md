# FIELDed — Operational State Machines

> **Status**: EXTENDS EXISTING [docs/state-machines.md](state-machines.md)  
> **Phase**: Architecture + Specification Only  
> **Last Updated**: 2026-09-19

---

## Overview

This document provides the complete specification of all operational state machines in FIELDed. State machines are **authoritative for transaction state**. The Business Brain may configure policy around them but does not replace them.

**Core principle**: No arbitrary state mutation. All transitions validated. Every transition recorded.

---

## 1. Enquiry State Machine

### 1.1 States

| State | Category | Description |
|---|---|---|
| `DRAFT` | Initial | Enquiry being composed, not yet submitted |
| `SUBMITTED` | Active | Sent to business, awaiting receipt confirmation |
| `RECEIVED` | Active | Business has seen the enquiry |
| `IN_REVIEW` | Active | Business is actively reviewing/assessing |
| `NEEDS_INFORMATION` | Active | Business needs more info from customer |
| `QUOTED` | Active | Business has provided a quote |
| `CUSTOMER_ACCEPTED` | Active | Customer accepted the quote |
| `BOOKING_PROPOSED` | Active | Business proposed a booking time |
| `BOOKED` | Active | Booking confirmed |
| `IN_PROGRESS` | Active | Service being delivered |
| `COMPLETED` | Terminal | Service delivered successfully |
| `DECLINED` | Terminal | Business declined the enquiry |
| `CANCELLED` | Terminal | Cancelled by customer or system |
| `EXPIRED` | Terminal | Timed out without action |
| `REJECTED` | Terminal | Customer rejected the quote |

### 1.2 Valid Transitions

```
DRAFT ──────────────────→ SUBMITTED
SUBMITTED ──────────────→ RECEIVED
RECEIVED ───────────────→ IN_REVIEW
RECEIVED ───────────────→ DECLINED
IN_REVIEW ──────────────→ NEEDS_INFORMATION
IN_REVIEW ──────────────→ QUOTED
IN_REVIEW ──────────────→ DECLINED
NEEDS_INFORMATION ──────→ IN_REVIEW (customer provided info)
QUOTED ─────────────────→ CUSTOMER_ACCEPTED
QUOTED ─────────────────→ REJECTED
CUSTOMER_ACCEPTED ──────→ BOOKING_PROPOSED
CUSTOMER_ACCEPTED ──────→ COMPLETED (if no booking needed)
BOOKING_PROPOSED ───────→ BOOKED
BOOKING_PROPOSED ───────→ CUSTOMER_ACCEPTED (reschedule)
BOOKED ─────────────────→ IN_PROGRESS
IN_PROGRESS ────────────→ COMPLETED
```

**Any active state** can transition to:
```
[ACTIVE_STATE] ─────────→ CANCELLED
[ACTIVE_STATE] ─────────→ EXPIRED (system-initiated)
```

### 1.3 Transition Authority

| Transition | Who Can Trigger | Authorization |
|---|---|---|
| DRAFT → SUBMITTED | Customer | `require_customer`, enquiry ownership |
| SUBMITTED → RECEIVED | Business | `require_business_role("staff")`, business membership |
| RECEIVED → IN_REVIEW | Business | `require_business_role("staff")` |
| RECEIVED → DECLINED | Business | `require_business_role("staff")` |
| IN_REVIEW → NEEDS_INFORMATION | Business | `require_business_role("staff")` |
| IN_REVIEW → QUOTED | Business | `require_business_role("staff")` |
| IN_REVIEW → DECLINED | Business | `require_business_role("staff")` |
| NEEDS_INFORMATION → IN_REVIEW | Customer | `require_customer`, enquiry ownership |
| QUOTED → CUSTOMER_ACCEPTED | Customer | `require_customer`, enquiry ownership |
| QUOTED → REJECTED | Customer | `require_customer`, enquiry ownership |
| CUSTOMER_ACCEPTED → BOOKING_PROPOSED | Business | `require_business_role("staff")` |
| BOOKING_PROPOSED → BOOKED | Customer | `require_customer`, enquiry ownership |
| BOOKED → IN_PROGRESS | Business | `require_business_role("staff")` |
| IN_PROGRESS → COMPLETED | Business | `require_business_role("staff")` |
| [ACTIVE] → CANCELLED | Customer or Business | Ownership/membership + Brain policy check |
| [ACTIVE] → EXPIRED | System | Automatic (time-based) |

### 1.4 Brain Interaction

The Business Brain **configures policy around** the enquiry state machine but does not control it:

| Brain Classification | Interaction |
|---|---|
| Qualification (D) | Determines what information is needed during NEEDS_INFORMATION |
| Pricing (B) | Determines quote generation during IN_REVIEW → QUOTED |
| Policy (E) | Determines cancellation eligibility for [ACTIVE] → CANCELLED |
| Escalation (J) | Determines when to escalate instead of transitioning |
| Communication (I) | Determines notifications sent on each transition |

### 1.5 Implementation Status

| Transition | Status |
|---|---|
| DRAFT → SUBMITTED | ✅ IMPLEMENTED |
| SUBMITTED → RECEIVED | ✅ IMPLEMENTED |
| RECEIVED → IN_REVIEW | ✅ IMPLEMENTED |
| IN_REVIEW → NEEDS_INFORMATION | ✅ IMPLEMENTED |
| IN_REVIEW → DECLINED | ✅ IMPLEMENTED |
| NEEDS_INFORMATION → IN_REVIEW | ✅ IMPLEMENTED |
| RECEIVED → DECLINED | ✅ IMPLEMENTED |
| QUOTED and beyond | 📋 SPECIFIED (awaiting Quote system) |
| CANCELLED from active states | 🔶 PARTIAL (customer cancel implemented) |
| EXPIRED (system) | 📋 SPECIFIED |

---

## 2. Booking State Machine

### 2.1 States

| State | Category | Description |
|---|---|---|
| `REQUESTED` | Initial | Customer requested a booking |
| `PROPOSED` | Active | Business proposed a time slot |
| `ACCEPTED` | Active | Customer accepted the proposal |
| `CONFIRMED` | Active | Booking confirmed by both parties |
| `IN_PROGRESS` | Active | Service being delivered |
| `COMPLETED` | Terminal | Service delivered |
| `DECLINED` | Terminal | Booking declined |
| `CANCELLED` | Terminal | Booking cancelled |
| `EXPIRED` | Terminal | Timed out |
| `RESCHEDULED` | Terminal | **Not a direct transition** — see Rescheduling Mechanism below |
| `NO_SHOW` | Terminal | Customer did not appear |

### 2.2 Valid Transitions

```
REQUESTED ─────────────→ PROPOSED
REQUESTED ─────────────→ DECLINED
PROPOSED ──────────────→ ACCEPTED
PROPOSED ──────────────→ DECLINED
ACCEPTED ──────────────→ CONFIRMED
ACCEPTED ──────────────→ CANCELLED
CONFIRMED ─────────────→ IN_PROGRESS
CONFIRMED ─────────────→ CANCELLED
IN_PROGRESS ───────────→ COMPLETED
IN_PROGRESS ───────────→ NO_SHOW
```

**Rescheduling Mechanism**: Rescheduling is NOT a direct state transition. Instead:
1. Original booking transitions: `CONFIRMED → CANCELLED` (reason: "rescheduled")
2. New booking is created with fresh lifecycle
3. New booking references original booking ID for audit trail

This preserves a clean, immutable lifecycle per booking instance.

**Any active state** can transition to:
```
[ACTIVE_STATE] ────────→ CANCELLED
[ACTIVE_STATE] ────────→ EXPIRED (system)
```

### 2.3 Transition Authority

| Transition | Who Can Trigger | Authorization |
|---|---|---|
| REQUESTED → PROPOSED | Business | `require_business_role("staff")` |
| REQUESTED → DECLINED | Business | `require_business_role("staff")` |
| PROPOSED → ACCEPTED | Customer | `require_customer`, booking ownership |
| PROPOSED → DECLINED | Customer | `require_customer`, booking ownership |
| ACCEPTED → CONFIRMED | System or Business | Auto-confirm or manual |
| CONFIRMED → IN_PROGRESS | Business | `require_business_role("staff")` |
| CONFIRMED → CANCELLED | Customer or Business | Policy check (Brain G) |
| IN_PROGRESS → COMPLETED | Business | `require_business_role("staff")` |
| IN_PROGRESS → NO_SHOW | Business | `require_business_role("staff")` |
| [ACTIVE] → CANCELLED | Customer or Business | Brain policy check |
| [ACTIVE] → EXPIRED | System | Automatic |

### 2.4 Brain Interaction

| Brain Classification | Interaction |
|---|---|
| Availability (C) | Validates proposed time slots |
| Booking (F) | Configures booking creation rules |
| Cancellation (G) | Determines cancellation eligibility + fees |
| Rescheduling (H) | Determines rescheduling eligibility + fees |
| Policy (E) | General policy constraints |
| Communication (I) | Notifications on transitions |
| Escalation (J) | When to escalate instead of auto-transition |

### 2.5 Implementation Status

| Component | Status |
|---|---|
| BookingStatus enum | ✅ IMPLEMENTED (defined in common enums) |
| Transition map | ✅ IMPLEMENTED (defined in common enums) |
| Booking entity | 📋 SPECIFIED (not yet created) |
| Booking service | 📋 SPECIFIED |
| Booking API | 📋 SPECIFIED |
| Brain integration | 📋 SPECIFIED (Brain-dependent) |

---

## 3. BrainVersion State Machine

### 3.1 States

| State | Category | Description |
|---|---|---|
| `DRAFT` | Initial | Being edited |
| `VALIDATING` | Processing | System validation in progress |
| `REVIEW` | Pending | Awaiting human approval |
| `APPROVED` | Pending | Approved, ready for activation |
| `ACTIVE` | Live | Currently governing the business |
| `SUPERSEDED` | Terminal | Replaced by newer version |

### 3.2 Valid Transitions

```
Standard path:
DRAFT ──────────────────→ VALIDATING
VALIDATING ─────────────→ REVIEW (validation passed)
VALIDATING ─────────────→ DRAFT (validation failed)
REVIEW ─────────────────→ APPROVED (approved by owner)
REVIEW ─────────────────→ DRAFT (rejected, needs changes)
APPROVED ───────────────→ ACTIVE (activated by owner)
ACTIVE ─────────────────→ SUPERSEDED (new version activated)

Shortcut path (manual rules only):
DRAFT ──────────────────→ REVIEW (skip validation for manually-created rules)
```

**Note**: The DRAFT → REVIEW shortcut is allowed for manually-created rules that do not need system validation. AI-generated rules must follow the standard path through VALIDATING.

### 3.3 Transition Authority

| Transition | Who Can Trigger | Authorization |
|---|---|---|
| DRAFT → VALIDATING | System or admin+ | `BRAIN_CREATE_RULE` |
| DRAFT → REVIEW | Owner | `BRAIN_CREATE_RULE` (manual rules only) |
| VALIDATING → REVIEW | System | Automatic on validation success |
| VALIDATING → DRAFT | System | Automatic on validation failure |
| REVIEW → APPROVED | Owner | `BRAIN_APPROVE` |
| REVIEW → DRAFT | Owner | `BRAIN_APPROVE` (rejection) |
| APPROVED → ACTIVE | Owner | `BRAIN_ACTIVATE` |
| ACTIVE → SUPERSEDED | System | Automatic when new version activates |

### 3.4 Implementation Status

| Component | Status |
|---|---|
| BrainVersionStatus enum | ✅ IMPLEMENTED |
| Transition map | ✅ IMPLEMENTED |
| BrainService.transition_version() | ✅ IMPLEMENTED |
| API endpoints | 📋 SPECIFIED |

---

## 4. ServiceOffer State Machine

### 4.1 States

| State | Category | Description |
|---|---|---|
| `DRAFT` | Initial | Being configured |
| `ACTIVE` | Live | Visible to customers, bookable |
| `PAUSED` | Suspended | Temporarily unavailable |
| `ARCHIVED` | Terminal | No longer available |

### 4.2 Valid Transitions

```
DRAFT ──────────────────→ ACTIVE
ACTIVE ─────────────────→ PAUSED
ACTIVE ─────────────────→ ARCHIVED
PAUSED ─────────────────→ ACTIVE
PAUSED ─────────────────→ ARCHIVED
```

### 4.3 Transition Authority

| Transition | Who Can Trigger | Authorization |
|---|---|---|
| DRAFT → ACTIVE | Business admin+ | `SERVICE_TRANSITION` |
| ACTIVE → PAUSED | Business admin+ | `SERVICE_TRANSITION` |
| ACTIVE → ARCHIVED | Business owner | `SERVICE_TRANSITION` |
| PAUSED → ACTIVE | Business admin+ | `SERVICE_TRANSITION` |
| PAUSED → ARCHIVED | Business owner | `SERVICE_TRANSITION` |

### 4.4 Implementation Status

| Component | Status |
|---|---|
| ServiceOfferStatus enum | ✅ IMPLEMENTED |
| Transition map | ✅ IMPLEMENTED |
| ServiceOfferService.transition_offer() | ✅ IMPLEMENTED |
| API endpoints | ✅ IMPLEMENTED |

---

## 5. Supporting State Machines

### 5.1 BusinessStatus

| State | Description | Status |
|---|---|---|
| `PENDING` | Newly created, not yet active | ✅ Column exists |
| `ACTIVE` | Operating normally | 📋 No transition logic |
| `SUSPENDED` | Temporarily suspended | 📋 No transition logic |
| `DEACTIVATED` | Permanently closed | 📋 No transition logic |

### 5.2 BusinessProfileStatus

| State | Description | Status |
|---|---|---|
| `INCOMPLETE` | Profile not fully configured | ✅ Implemented |
| `ACTIVE` | Public-facing and complete | ✅ Implemented |
| `SUSPENDED` | Profile suspended | ✅ Column exists |

### 5.3 CustomerProfileStatus

| State | Description | Status |
|---|---|---|
| `INCOMPLETE` | Profile not fully set up | ✅ Implemented |
| `ACTIVE` | Active customer | ✅ Implemented |
| `SUSPENDED` | Account suspended | 📋 No transition logic |

---

## 6. Transition Recording

Every state transition must record:

| Field | Description |
|---|---|
| `actor_id` | Who initiated the transition (User UUID or SYSTEM) |
| `timestamp` | When the transition occurred |
| `previous_state` | State before transition |
| `new_state` | State after transition |
| `reason` | Why the transition occurred (optional but recommended) |
| `correlation_id` | Cross-service correlation |
| `request_id` | HTTP request that triggered it |
| `brain_version_id` | Brain version governing this transition (if applicable) |

This is stored as an `AuditEvent` with `change_type: TRANSITIONED`.

---

## 7. Transition Validation Pattern

All state transitions follow this pattern:

```python
def transition(enquiry, new_status, actor, reason=None):
    # 1. Validate transition is allowed
    if new_status not in VALID_TRANSITIONS[enquiry.status]:
        raise StateTransitionError(
            f"Cannot transition from {enquiry.status} to {new_status}"
        )

    # 2. Validate actor has permission
    validate_transition_authorization(enquiry, new_status, actor)

    # 3. Evaluate Brain rules (if applicable)
    brain_result = evaluate_brain_rules(enquiry, new_status)
    if brain_result.outcome == "DENY":
        raise DomainError(f"Brain policy prohibits this transition: {brain_result.reason}")
    if brain_result.outcome == "ESCALATE":
        # Create escalation instead of transitioning
        create_escalation(enquiry, brain_result)
        return

    # 4. Record previous state
    previous_status = enquiry.status

    # 5. Apply transition
    enquiry.status = new_status

    # 6. Record audit event
    create_audit_event(
        event_type="enquiry_transitioned",
        resource=enquiry,
        previous_state=previous_status,
        new_state=new_status,
        actor=actor,
        reason=reason,
        brain_version_id=get_active_brain_version(enquiry.business_id)
    )

    # 7. Log
    logger.info("enquiry_transitioned", ...)
```

---

## 8. Brain + State Machine Boundary

```
┌─────────────────────────────────────────────────────────────┐
│                    STATE MACHINE (Authority)                  │
│                                                               │
│  Defines: WHAT states exist, WHAT transitions are valid       │
│  Controls: Actual transaction state                           │
│  Enforces: Valid transition paths                             │
│  Records: Every transition as audit event                     │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              BUSINESS BRAIN (Configuration)              │ │
│  │                                                          │ │
│  │  Configures: POLICY around transitions                  │ │
│  │  - When can cancellation happen? (Policy E, Cancel G)  │ │
│  │  - What fee applies? (Policy E)                         │ │
│  │  - What information is needed? (Qualification D)        │ │
│  │  - Who must approve? (Human Approval O)                 │ │
│  │  - When to escalate? (Escalation J)                     │ │
│  │                                                          │ │
│  │  Does NOT: Change state, define states, allow invalid   │ │
│  │            transitions, or replace the state machine     │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

**The state machine says**: "You can go from CONFIRMED to CANCELLED"
**The Brain says**: "If you cancel within 24 hours, there's a 50% fee. If within 4 hours, cancellation requires owner approval."

---

## 9. Expiration Logic

Expirable states and their timeout rules:

| State Machine | Expirable State | Default Timeout | Brain Configurable? |
|---|---|---|---|
| Enquiry | SUBMITTED | 72 hours | Yes (Policy E) |
| Enquiry | NEEDS_INFORMATION | 7 days | Yes (Policy E) |
| Enquiry | QUOTED | Quote validity period | Yes (Pricing B) |
| Booking | REQUESTED | 24 hours | Yes (Booking F) |
| Booking | PROPOSED | 48 hours | Yes (Booking F) |
| Booking | CONFIRMED | No expiry | N/A |

Expiration is a **system transition** to EXPIRED state. It is:
- Automatic (no human trigger)
- Configurable via Brain
- Audited like any other transition
- Reversible only by creating a new transaction (not by un-expiring)
