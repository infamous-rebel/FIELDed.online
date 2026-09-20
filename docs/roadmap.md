# FIELDed — Roadmap

## Phase 00 — Architecture Contract [COMPLETE]
- [x] Technology stack selection
- [x] Repository structure
- [x] Architecture documentation
- [x] Domain model definition
- [x] AGENTS.md creation

## Phase 01 — Production Foundation [COMPLETE]
- [x] Backend: FastAPI app factory, config, logging, exceptions
- [x] Database: PostgreSQL, SQLAlchemy, Alembic, initial migration
- [x] Auth: bcrypt password hashing, JWT tokens, registration, login
- [x] Authorization: RBAC, tenant isolation, role dependencies
- [x] Domain models: Identity, Business Brain, Services
- [x] Adapter interfaces: AI, Email, Storage, SMS, Calendar
- [x] Frontend: Next.js 15, layouts, placeholder pages, API client
- [x] Testing: pytest, httpx, unit + integration + security tests
- [x] Docker: PostgreSQL + Redis for dev/test
- [x] CI: GitHub Actions workflow

## Phase 02 — Identity & Authorization [NEXT]
- [ ] Email verification flow
- [ ] Password reset
- [ ] Business registration flow
- [ ] Business member invitation
- [ ] Profile management (customer + business)
- [ ] Session management improvements

## Phase 03 — Business Profile + Service Offers
- [ ] Business profile CRUD
- [ ] Social links management
- [ ] Service category management
- [ ] Service Offer CRUD
- [ ] Publication state management
- [ ] Service area configuration

## Phase 04 — Business Brain
- [ ] Brain schema implementation
- [ ] Version creation and lifecycle
- [ ] Draft/review/approve/active workflow
- [ ] Rule management
- [ ] Brain version comparison

## Phase 05 — Customer Discovery
- [ ] Natural-language search input
- [ ] Intent extraction (AI)
- [ ] Structured search request
- [ ] Deterministic capability matching
- [ ] Location/service-area filtering
- [ ] Business result presentation

## Phase 06 — Enquiry + Messaging
- [ ] Enquiry state machine
- [ ] Conversation model
- [ ] Message model
- [ ] Inbox UI (customer + business)
- [ ] Unread state tracking
- [ ] System events in conversations

## Phase 07 — Quote Engine
- [ ] Quote model and lifecycle
- [ ] Pricing engine integration
- [ ] Quote approval workflow
- [ ] Customer acceptance/rejection
- [ ] Quote history

## Phase 08 — Scheduling + Booking
- [ ] Availability domain
- [ ] Slot proposal
- [ ] Booking state machine
- [ ] Rescheduling
- [ ] Cancellation
- [ ] Completion

## Phase 09 — Review/Trust
- [ ] Completion validation
- [ ] Review eligibility
- [ ] Rating and review submission
- [ ] Moderation
- [ ] Business rating aggregation

## Phase 10 — Notifications/Integrations
- [ ] Notification abstraction
- [ ] Email adapter implementation
- [ ] Calendar adapter implementation
- [ ] Notification preferences
- [ ] Webhook architecture

## Phase 11 — AI Orchestration
- [ ] Discovery AI implementation
- [ ] Enquiry AI
- [ ] Business Brain reasoning
- [ ] Quote assistance
- [ ] Response drafting
- [ ] Guardrails and evaluation

## Phase 12 — Production Hardening
- [ ] Security audit
- [ ] Authorization audit
- [ ] Tenant isolation audit
- [ ] Performance optimization
- [ ] Rate limiting
- [ ] Observability
- [ ] Backup/recovery
- [ ] Production deployment
