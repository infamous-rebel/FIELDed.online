# FIELDed — Domain Model

## Canonical Entities

### Identity
- **User** — Authentication identity. Has email, hashed password, active/verified flags.
- **CustomerProfile** — 1:1 with User. Name, phone, address.
- **Business** — A business entity. Has name, slug.
- **BusinessMember** — Links User to Business with a role (owner/admin/staff).
- **BusinessProfile** — 1:1 with Business. Public-facing info, social links, ratings.

### Business Brain
- **BusinessBrain** — 1:1 with Business. Container for versioned configurations.
- **BrainVersion** — Versioned snapshot of brain config. Status lifecycle: DRAFT → ACTIVE → SUPERSEDED.
- **BusinessRule** — Structured rule within a Brain version (pricing, policy, qualification, etc.).

### Services
- **ServiceCategory** — Hierarchical classification (e.g., "Home Services" → "Electrical").
- **ServiceOffer** — The transaction anchor. Defines what a business provides, pricing model, delivery mode, qualification requirements, booking rules, cancellation policy, service area.

### Transaction (Phase 06+)
- **Enquiry** — Customer request for a specific business/service. Has explicit state machine.
- **Conversation** — 1:1 with Enquiry. Contains messages and system events.
- **Message** — Individual communication within a conversation.
- **Quote** — Price proposal for an enquiry. Has lifecycle.
- **Booking** — Scheduled service appointment. Has explicit state machine.

### Trust (Phase 09+)
- **Review** — Customer review of completed service.
- **Rating** — Numeric rating component.
- **ReviewEligibility** — Derived from completed FIELDed transaction.

### Platform (Phase 10+)
- **Notification** — Internal notification abstraction.
- **AuditEvent** — Trace record of meaningful actions.
- **Evidence** — Supporting data for audit events.

## Key Relationships

```
User ──1:1── CustomerProfile
User ──1:N── BusinessMember ──N:1── Business
Business ──1:1── BusinessProfile
Business ──1:1── BusinessBrain ──1:N── BrainVersion ──1:N── BusinessRule
Business ──1:N── ServiceOffer ──N:1── ServiceCategory
```

## Rules

- User ≠ Customer ≠ Business. One identity may have multiple roles.
- No duplicate concepts (no "lead", "request", "case" alongside "enquiry").
- ServiceOffer is the bridge between customer intent and business capability.
- AI must never claim a business provides a service without a matching ServiceOffer.
