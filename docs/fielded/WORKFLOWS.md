# FIELDed — Workflows & State Machines

**Status**: Current State Baseline  
**Last Updated**: 2026-09-24

---

## Overview

FIELDed uses **explicit state machines** for all entity lifecycles. Every state transition is validated, recorded, and audited. No arbitrary state mutation is allowed.

---

## State Machines

### Enquiry Status

```
DRAFT → SUBMITTED → RECEIVED → IN_REVIEW → NEEDS_INFORMATION
                                              ↓
                                          IN_REVIEW
                                              ↓
                                          QUOTED → CUSTOMER_ACCEPTED → BOOKING_PROPOSED → BOOKED → IN_PROGRESS → COMPLETED

Terminal States: DECLINED, CANCELLED, EXPIRED, REJECTED
```

**Transitions**:

| From | To | Actor | Trigger |
|------|-----|-------|---------|
| DRAFT | SUBMITTED | Customer | Submit enquiry |
| DRAFT | CANCELLED | Customer | Cancel enquiry |
| SUBMITTED | RECEIVED | Business | Receive enquiry |
| SUBMITTED | EXPIRED | System | Timeout |
| SUBMITTED | CANCELLED | Customer | Cancel enquiry |
| RECEIVED | IN_REVIEW | Business | Start review |
| RECEIVED | DECLINED | Business | Decline enquiry |
| RECEIVED | EXPIRED | System | Timeout |
| IN_REVIEW | NEEDS_INFORMATION | Business | Request more info |
| IN_REVIEW | QUOTED | Business | Issue quote |
| IN_REVIEW | DECLINED | Business | Decline enquiry |
| IN_REVIEW | EXPIRED | System | Timeout |
| NEEDS_INFORMATION | IN_REVIEW | Business | Resume review |
| NEEDS_INFORMATION | DECLINED | Business | Decline enquiry |
| NEEDS_INFORMATION | EXPIRED | System | Timeout |
| QUOTED | CUSTOMER_ACCEPTED | Customer | Accept quote |
| QUOTED | EXPIRED | System | Timeout |
| QUOTED | CANCELLED | Customer | Cancel enquiry |
| CUSTOMER_ACCEPTED | BOOKING_PROPOSED | Business | Propose booking |
| CUSTOMER_ACCEPTED | CANCELLED | Customer | Cancel enquiry |
| BOOKING_PROPOSED | BOOKED | System | Booking confirmed |
| BOOKING_PROPOSED | CANCELLED | Customer | Cancel enquiry |
| BOOKED | IN_PROGRESS | Business | Start service |
| BOOKED | CANCELLED | Customer/Business | Cancel booking |
| IN_PROGRESS | COMPLETED | Business | Complete service |
| IN_PROGRESS | CANCELLED | Customer/Business | Cancel service |

---

### Quote Status

```
DRAFT → ISSUED → ACCEPTED
              → DECLINED
              → EXPIRED
```

**Transitions**:

| From | To | Actor | Trigger |
|------|-----|-------|---------|
| DRAFT | ISSUED | Business | Issue quote |
| ISSUED | ACCEPTED | Customer | Accept quote |
| ISSUED | DECLINED | Customer | Decline quote |
| ISSUED | EXPIRED | System | Timeout |

---

### Booking Status

```
REQUESTED → PROPOSED → ACCEPTED → CONFIRMED → IN_PROGRESS → COMPLETED

Terminal States: DECLINED, CANCELLED, EXPIRED, NO_SHOW
```

**Transitions**:

| From | To | Actor | Trigger |
|------|-----|-------|---------|
| REQUESTED | PROPOSED | Business | Propose booking |
| REQUESTED | DECLINED | Business | Decline booking |
| REQUESTED | CANCELLED | Customer | Cancel booking |
| REQUESTED | EXPIRED | System | Timeout |
| PROPOSED | ACCEPTED | Customer | Accept booking |
| PROPOSED | DECLINED | Customer | Decline booking |
| PROPOSED | CANCELLED | Customer | Cancel booking |
| PROPOSED | EXPIRED | System | Timeout |
| ACCEPTED | CONFIRMED | Business | Confirm booking |
| ACCEPTED | CANCELLED | Customer/Business | Cancel booking |
| ACCEPTED | EXPIRED | System | Timeout |
| CONFIRMED | IN_PROGRESS | Business | Start service |
| CONFIRMED | COMPLETED | Business | Complete service (no start) |
| CONFIRMED | CANCELLED | Customer/Business | Cancel booking |
| CONFIRMED | NO_SHOW | Business | Customer no-show |
| IN_PROGRESS | COMPLETED | Business | Complete service |
| IN_PROGRESS | CANCELLED | Customer/Business | Cancel service |

---

### Brain Version Status

```
DRAFT → VALIDATING → REVIEW → APPROVED → ACTIVE → SUPERSEDED
```

**Transitions**:

| From | To | Actor | Trigger |
|------|-----|-------|---------|
| DRAFT | VALIDATING | System | Start validation |
| DRAFT | REVIEW | Owner | Manual review (skip validation) |
| VALIDATING | REVIEW | System | Validation passed |
| VALIDATING | DRAFT | System | Validation failed |
| REVIEW | APPROVED | Owner | Approve version |
| REVIEW | DRAFT | Owner | Reject version |
| APPROVED | ACTIVE | Owner | Activate version |
| ACTIVE | SUPERSEDED | System | New version activated |

---

### Service Offer Status

```
DRAFT → ACTIVE → PAUSED → ACTIVE
              → ARCHIVED
```

**Transitions**:

| From | To | Actor | Trigger |
|------|-----|-------|---------|
| DRAFT | ACTIVE | Business | Activate offer |
| DRAFT | ARCHIVED | Business | Archive offer |
| ACTIVE | PAUSED | Business | Pause offer |
| ACTIVE | ARCHIVED | Business | Archive offer |
| PAUSED | ACTIVE | Business | Resume offer |
| PAUSED | ARCHIVED | Business | Archive offer |

---

### Service Execution Status

```
SCHEDULED → IN_PROGRESS → COMPLETED

Terminal States: CANCELLED, NO_SHOW
```

**Transitions**:

| From | To | Actor | Trigger |
|------|-----|-------|---------|
| SCHEDULED | IN_PROGRESS | Business | Start execution |
| SCHEDULED | CANCELLED | Business | Cancel execution |
| SCHEDULED | NO_SHOW | Business | Customer no-show |
| IN_PROGRESS | COMPLETED | Business | Complete execution |
| IN_PROGRESS | CANCELLED | Business | Cancel execution |

---

### Invoice Status

```
DRAFT → ISSUED → VOID
```

**Transitions**:

| From | To | Actor | Trigger |
|------|-----|-------|---------|
| DRAFT | ISSUED | Business | Issue invoice |
| DRAFT | VOID | Business | Void invoice |
| ISSUED | VOID | Business | Void invoice |

---

### Invoice Payment Status

```
UNPAID → PARTIALLY_PAID → PAID
       → FAILED
       → REFUNDED
       → PARTIALLY_REFUNDED → REFUNDED
```

---

### Payment Status

```
PENDING → PROCESSING → SUCCEEDED → REFUNDED
                              → PARTIALLY_REFUNDED → REFUNDED

Terminal States: FAILED, EXPIRED, CANCELLED, REFUNDED
```

**Transitions**:

| From | To | Actor | Trigger |
|------|-----|-------|---------|
| PENDING | PROCESSING | System | Start processing |
| PENDING | FAILED | System | Processing failed |
| PENDING | EXPIRED | System | Timeout |
| PENDING | CANCELLED | Customer | Cancel payment |
| PROCESSING | SUCCEEDED | System | Payment succeeded |
| PROCESSING | FAILED | System | Processing failed |
| PROCESSING | EXPIRED | System | Timeout |
| PROCESSING | CANCELLED | System | Cancelled |
| SUCCEEDED | REFUNDED | Business | Full refund |
| SUCCEEDED | PARTIALLY_REFUNDED | Business | Partial refund |
| PARTIALLY_REFUNDED | REFUNDED | Business | Full refund |

---

### Business Status

```
PENDING → ACTIVE → SUSPENDED → ACTIVE
                 → DEACTIVATED
```

**Transitions**:

| From | To | Actor | Trigger |
|------|-----|-------|---------|
| PENDING | ACTIVE | Owner | Activate business |
| PENDING | DEACTIVATED | Owner | Deactivate business |
| ACTIVE | SUSPENDED | Platform | Suspend business |
| ACTIVE | DEACTIVATED | Owner | Deactivate business |
| SUSPENDED | ACTIVE | Platform | Reactivate business |
| SUSPENDED | DEACTIVATED | Platform | Deactivate business |

---

### Business Profile Status

```
INCOMPLETE → ACTIVE → SUSPENDED → ACTIVE
```

---

### Customer Profile Status

```
INCOMPLETE → ACTIVE → SUSPENDED
```

---

### Brain Conversation Status

```
ACTIVE → ARCHIVED
```

---

### Brain Proposal Status

```
PENDING → APPROVED → APPLIED
       → EDITED → APPLIED
       → REJECTED
```

---

### Call Status

```
REQUESTED → AUTHORIZED → QUEUED → INITIATING → RINGING → CONNECTED → IN_PROGRESS → COMPLETED

Terminal States: FAILED, NO_ANSWER, BUSY, DECLINED, CANCELLED, EXPIRED, ESCALATED
```

---

### Communication Status

```
PENDING → QUEUED → SENT → DELIVERED
                    → FAILED
                    → BOUNCED
                    → REJECTED
                    → CANCELLED
```

---

### Outbox Event Status

```
PENDING → PROCESSING → PROCESSED
                     → RETRYABLE → PROCESSING
                     → FAILED
```

---

## Cascade Workflows

### Enquiry → Quote → Booking → Execution → Completion

1. Enquiry created (status: SUBMITTED)
2. Business issues quote (enquiry → QUOTED)
3. Customer accepts quote (enquiry → CUSTOMER_ACCEPTED, quote → ACCEPTED)
4. Booking created (status: REQUESTED → BOOKED)
5. Enquiry → BOOKED
6. Service execution created (status: SCHEDULED)
7. Execution started (execution → IN_PROGRESS, booking → IN_PROGRESS, enquiry → IN_PROGRESS)
8. Execution completed (execution → COMPLETED, booking → COMPLETED, enquiry → COMPLETED)
9. Invoice generated
10. Ledger entries created
11. Review eligible

### Payment → Invoice → Ledger

1. Payment initiated (status: PENDING)
2. Payment processed (status: PROCESSING)
3. Payment succeeded (status: SUCCEEDED)
4. Invoice payment status updated (→ PAID)
5. Ledger entries created
6. Audit event recorded

### Brain Proposal → Application

1. Conversation message sent
2. AI generates proposal (status: PENDING)
3. Owner reviews proposal
4. Owner approves (status: APPROVED)
5. Proposal applied to brain state (status: APPLIED)
6. Brain version updated or new version created

---

## Event Workflows

### Outbox Event Processing

1. Domain event occurs (e.g., enquiry created)
2. Outbox event created (status: PENDING)
3. Outbox worker picks up event (status: PROCESSING)
4. Orchestration service processes event
5. Notifications/communications sent
6. Outbox event marked processed (status: PROCESSED)
7. If failed, retry (status: RETRYABLE)

### Notification Delivery

1. Notification created
2. Outbox event created
3. Outbox worker processes event
4. Notification delivered via configured channel
5. Notification marked as read (when user reads)

---

## Summary

FIELDed uses **explicit, validated state machines** for all entity lifecycles. Every transition is:

- **Validated**: Only allowed transitions permitted
- **Recorded**: Transition recorded with actor, timestamp, reason
- **Audited**: Audit event generated
- **Cascaded**: Related entities updated appropriately

This ensures **data integrity**, **traceability**, and **governance** across the entire platform.
