# FIELDed — State Machines

## Enquiry Lifecycle

```
DRAFT → SUBMITTED → RECEIVED → IN_REVIEW → NEEDS_INFORMATION
                                               ↓
                              IN_REVIEW ←──────┘
                                 ↓
                              QUOTED → CUSTOMER_ACCEPTED → BOOKING_PROPOSED → BOOKED → IN_PROGRESS → COMPLETED
```

### Terminal States
- **COMPLETED** — Service delivered successfully
- **DECLINED** — Business declined the enquiry
- **CANCELLED** — Customer or system cancelled
- **EXPIRED** — Timed out without action
- **REJECTED** — Customer rejected the quote

### Transition Rules
- Every transition records: actor, timestamp, previous_state, new_state, reason, correlation_id
- No arbitrary state mutation — all transitions validated
- Terminal states have no outgoing transitions

## Booking Lifecycle

```
REQUESTED → PROPOSED → ACCEPTED → CONFIRMED → IN_PROGRESS → COMPLETED
```

### Terminal States
- **COMPLETED** — Service delivered
- **DECLINED** — Booking declined
- **CANCELLED** — Booking cancelled
- **EXPIRED** — Timed out
- **RESCHEDULED** — Moved to new time
- **NO_SHOW** — Customer did not appear

## Business Brain Version Lifecycle

```
DRAFT → VALIDATING → REVIEW → APPROVED → ACTIVE → SUPERSEDED
```

### Rules
- Only one version can be ACTIVE per business at any time
- When a new version becomes ACTIVE, the previous ACTIVE version becomes SUPERSEDED
- Historical transactions reference the Brain version that governed them
- SUPERSEDED is terminal — no further transitions

### Immutability Enforcement
- BrainVersions are mutable **only** in DRAFT status
- REVIEW, APPROVED, ACTIVE, and SUPERSEDED versions are immutable — any mutation attempt raises `DomainError`
- Immutability is enforced at the service/domain layer via `BrainService._ensure_mutable()`
- Both configuration updates and rule additions check mutability before proceeding
- The correct modification path for a non-DRAFT version is to create a new DRAFT version

## Implementation Pattern

State machines are implemented as:
1. Enum class defining all valid states
2. Transition map (dict) defining allowed transitions per state
3. Domain service method that validates transitions before applying
4. Audit event recorded on every successful transition
