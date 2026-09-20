# FIELDed — AGENTS.md

## Product Definition

FIELDed is a customer-to-business service network where customers describe what they need in plain English, discover businesses capable of fulfilling it, initiate service enquiries, communicate with businesses, receive quotes/proposals, book services, and later review completed services — while every business operates through its own governed Business Brain.

Two sides are equally important:
- **Customer Network**: search, discover, enquire, communicate, book, review
- **Business Operations Platform**: profile, Business Brain, Service Offers, pricing, availability, policies, enquiry handling, quotes, bookings, reviews

## Architectural Principles

1. **AI intelligence != business authority.** AI may interpret, classify, extract, summarize, recommend, or draft. AI must NOT independently control price, availability, policy, authorization, booking state, review eligibility, business capability, permissions, or transaction state.

2. **Deterministic domain logic is authoritative.** Every critical decision flows through validated domain rules and the Business Brain.

3. **Provider-agnostic architecture.** No hardcoded dependencies on any single AI provider, cloud vendor, email service, storage provider, or payment system. All external services sit behind adapter interfaces.

4. **Tenant isolation is foundational.** Businesses never access another business's data. Customers only access their own data. Authorization is resolved server-side from authenticated identity and database relationships.

5. **Explicit state machines.** Enquiry lifecycle, booking lifecycle, and Business Brain versioning all use explicit state machines with validated transitions. No arbitrary state mutation.

6. **Schema-first domain model.** Domain entities are defined with strong typing, database constraints, and schema validation. No casual creation of duplicate or overlapping concepts.

## Domain Boundaries

### Identity
User, CustomerProfile, Business, BusinessMember, Role, Session, AuthenticationIdentity

### Discovery
BusinessProfile, ServiceOffer, ServiceCategory, BusinessCapability, Availability, Location, SearchRequest, SearchResult

### Transaction
Enquiry, EnquiryParticipant, Conversation, Message, Quote, QuoteItem, Proposal, Booking, ServiceExecution, Cancellation, Reschedule

### Business Brain
BusinessBrain, BrainVersion, BusinessRule, PricingRule, PolicyRule, QualificationRule, AvailabilityRule, EscalationRule, CommunicationPolicy

### Trust
Review, Rating, ReviewEligibility, ServiceCompletion

### Platform
Notification, AuditEvent, Evidence, WebhookEvent, Integration, ExternalAccount

## AI Authority Limitations

The execution pattern is ALWAYS:
```
AI proposal -> structured schema -> validation -> deterministic rules -> authorization -> execution -> audit
```

AI must NOT:
- Set or change prices without business rule validation
- Determine availability without checking deterministic constraints
- Override business policies
- Authorize customers or grant permissions
- Change booking/transaction state directly
- Determine review eligibility
- Claim a business provides a service without a matching ServiceOffer

## Business Brain Rules

- Versioned configuration: DRAFT -> VALIDATING -> REVIEW -> APPROVED -> ACTIVE -> SUPERSEDED
- Never silently mutate an ACTIVE Business Brain
- Historical transactions must reference the Brain version that governed them
- Brain areas: Identity, Services, Pricing, Availability, Qualification, Policies, Escalation, Communication

## Tenant Isolation Requirements

- Every database query must be tenant-scoped
- Authorization is resolved server-side, never trusted from frontend
- Cross-tenant access is impossible by design (repository-level enforcement)
- Security tests must verify cross-tenant isolation

## State Machine Rules

- All state transitions must be explicit and validated
- Every transition records: actor, timestamp, previous state, new state, reason, correlation_id, audit event
- No endpoint may mutate state without going through the state machine validator

## Testing Requirements

- Unit tests: pricing, policies, availability, permissions, state transitions, review eligibility, matching
- Integration tests: database, auth, messaging, quotes, bookings, Business Brain, notifications
- Security tests: cross-tenant access, privilege escalation, IDOR, unauthorized messages/reviews/brain access
- AI evaluation: intent extraction, hallucination prevention, prompt injection, malformed output
- E2E: customer signup -> search -> enquiry -> quote -> booking -> completion -> review

## Security Requirements

- Password hashing: bcrypt
- JWT with access/refresh token rotation
- Server-side authorization on every protected resource
- Input validation on all endpoints
- Rate limiting on authentication endpoints
- CORS configured explicitly
- No secrets in code — environment variables only
- Database constraints for data integrity
- Audit trail for all meaningful actions

## Coding Conventions

- Python: type hints everywhere, async/await for I/O, Pydantic for validation
- TypeScript: strict mode, no `any`, typed API responses
- File naming: snake_case (Python), kebab-case (TypeScript/Next.js)
- One domain concept per file — no god-files
- Repository pattern for database access
- Service layer for business logic
- Adapter pattern for external services
- Structured JSON logging with request/correlation IDs

## Immutable Rules

1. **Do not rewrite existing architecture without justification.**
2. **Do not invent domain entities** — use the canonical model or propose changes through documentation first.
3. **Do not bypass deterministic domain logic with AI.**
4. **Do not use mock behavior as production behavior.**
5. **Inspect existing implementation before modifying it.**
6. **Do not create duplicate overlapping concepts** (e.g., "lead", "request", "case", "job" alongside "enquiry") without explicitly documented boundaries.
7. **Do not choose technologies simply because they are fashionable.**
8. **Do not hardcode provider-specific dependencies.**

## Technology Stack

- Backend: Python 3.12 + FastAPI
- Frontend: Next.js 15 + TypeScript
- Database: PostgreSQL 16
- ORM: SQLAlchemy 2.0 (async)
- Migrations: Alembic
- Auth: bcrypt + PyJWT (adapter pattern)
- Cache: Redis (adapter pattern)
- Testing: pytest + httpx (backend), Vitest (frontend)
- Monorepo: Turborepo
- CI: GitHub Actions
- Styling: Tailwind CSS 4
