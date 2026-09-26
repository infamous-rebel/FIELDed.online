# FIELDed

**Customer-to-business service network where every business operates through its own governed Business Brain.**

FIELDed connects customers who need services with businesses capable of delivering them. Customers describe what they need in plain English, discover businesses, initiate enquiries, receive quotes, book services, and leave reviews. Businesses manage their entire operation — services, pricing, policies, availability, enquiries, bookings, and reviews — through an AI-governed Business Brain.

---

## Core Product Concept

FIELDed is a two-sided platform where both sides are equally important:

- **Customer Network**: search, discover, enquire, communicate, book, pay, review
- **Business Operations Platform**: profile, Business Brain, service catalog, pricing, availability, policies, enquiry handling, quotes, bookings, service execution, payments, reviews

The critical distinction: **FIELDed is the system of record.** Stripe, Google Calendar, Resend, and Vonage are external infrastructure/adapters around FIELDed — not competing sources of truth.

---

## Customer Experience

1. **Discovery** — Search for businesses or describe what you need in natural language. AI interprets intent; the database remains the authority on results.
2. **Enquiry** — Initiate an enquiry against a service offer. Each enquiry has a dedicated conversation for bidirectional messaging.
3. **Conversation** — Communicate directly with the business. Ask questions, provide details, negotiate scope.
4. **Quote** — Receive a priced quote with amount, currency, and notes. Quotes retain brain version and pricing evidence for traceability.
5. **Booking** — Accept a quote and propose a booking with scheduled time. Bookings follow a governed lifecycle.
6. **Payment** — Pay for the service after completion. Payments use idempotency keys and are processed through Stripe.
7. **Service** — The business executes the service. Completion cascades through booking → enquiry → review eligibility.
8. **Review** — Leave a review for completed services. Eligibility is deterministic (completed execution + valid booking + correct customer).

---

## Business Experience

- **Profile & Services** — Manage business profile, service catalog, pricing models (FIXED, HOURLY, QUOTE_REQUIRED, STARTING_AT, CUSTOM), delivery modes, and categories.
- **Business Brain** — An AI-governed rule system covering identity, services, pricing, availability, qualification, policies, escalation, and communication. Brain versions follow a strict lifecycle: DRAFT → VALIDATING → REVIEW → APPROVED → ACTIVE → SUPERSEDED.
- **Interactive Co-Brain** — Conversational interface between the business owner and the Brain. AI proposes changes; the owner approves or rejects. Proposals carry confidence scores and reasoning summaries.
- **Enquiry Handling** — Receive, review, and progress enquiries through the lifecycle.
- **Quote & Booking** — Generate deterministic quotes from brain rules, manage bookings, and track service execution.
- **Communications Hub** — View all communications across email, SMS, WhatsApp, and voice channels.
- **Financial** — Invoices, payments, ledger entries, and commercial policy management.

---

## Business Network / Discovery

- Public business directory with searchable profiles
- Service category browsing
- AI-powered natural language discovery (when AI provider configured)
- Public business profiles with logo, description, services, contact info

---

## Transaction Lifecycle

```
Enquiry → Conversation → Quote → Booking → Payment → Service Execution → Review
```

Full state machines govern every transition:

| Entity | Lifecycle |
|--------|-----------|
| Enquiry | DRAFT → SUBMITTED → RECEIVED → IN_REVIEW → QUOTED → CUSTOMER_ACCEPTED → BOOKING_PROPOSED → BOOKED → IN_PROGRESS → COMPLETED |
| Quote | DRAFT → ISSUED → ACCEPTED / DECLINED / EXPIRED |
| Booking | REQUESTED → PROPOSED → ACCEPTED → CONFIRMED → IN_PROGRESS → COMPLETED |
| Payment | PENDING → PROCESSING → SUCCEEDED / FAILED / EXPIRED / CANCELLED |
| Service Execution | SCHEDULED → IN_PROGRESS → COMPLETED / CANCELLED / NO_SHOW |
| Review | Submitted for completed services (deterministic eligibility) |

---

## Business Brain & Interactive Co-Brain

The Business Brain is FIELDed's differentiating feature — a versioned, AI-governed rule system:

- **AI proposes** business knowledge (services, pricing, policies, availability, qualification, escalation)
- **Owners approve/reject** proposals through the interactive Co-Brain
- **Approved changes** enter governed Brain state with full traceability
- **Deterministic rules** remain authoritative — AI never silently mutates production state
- **Brain versions** are immutable after DRAFT; transactions retain the brain version that governed them
- **Configuration areas**: Identity, Services, Pricing, Availability, Qualification, Policies, Escalation, Communication

---

## AI Governance Model

**AI intelligence ≠ business authority.**

AI can understand, propose, explain, and assist. AI does not automatically become business authority.

The execution pattern is ALWAYS:
```
AI proposal → structured schema → validation → deterministic rules → authorization → execution → audit
```

**AI may**: interpret, classify, extract, summarize, recommend, draft  
**AI must not**: set prices without validation, determine availability without checking constraints, override policies, authorize customers, change transaction state, determine review eligibility

Owner-approved or explicitly delegated capabilities may execute automatically where deterministic policy permits. All meaningful automated actions produce appropriate evidence/audit records.

---

## Agent / Capability / Permission / Delegation Architecture

FIELDed implements an agent-based capability system:

- **Agent Capabilities** — Declarative capability definitions (what an agent can do)
- **Agent Delegations** — Owner-approved delegation of capabilities to agents
- **Agent Execution Logs** — Audit trail for all automated agent actions
- **Approval Policy** — Deterministic governance of when automation is permitted

---

## Communications Architecture

FIELDed supports multiple communication channels through a unified orchestration layer:

### Email / Resend
Transactional email delivery with delivery tracking via webhooks. Adapter: `ResendEmailProvider`.

### SMS / WhatsApp / Voice / Vonage
Multi-channel communication through the Vonage Messages API and Voice API:
- **SMS** — Vonage Messages API (JWT authentication)
- **WhatsApp** — Vonage Messages API (WhatsApp channel)
- **Voice** — Vonage Voice API with NCCO call behavior

All channels share the same Vonage Application and credentials. Adapter pattern allows switching providers.

### Call Agent
AI-powered outbound voice calls with deterministic conversation governance:
- Call authorized (policy check) → Call initiated → AI agent conducts conversation → Outcome recorded → Escalation to human if needed
- NCCO webhooks for call behavior; event webhooks for status tracking

---

## Google Calendar Automation

Per-business Google Calendar integration via OAuth 2.0:
- Each business connects their own Google Calendar through the FIELDed UI
- OAuth tokens encrypted at rest using Fernet symmetric encryption
- Bookings automatically synced to business calendars on confirmation
- Calendar events cancelled on booking cancellation
- Calendar failure does NOT invalidate the booking (FIELDed remains authoritative)

---

## Unified Booking Automation

Confirmed bookings trigger downstream operations through the event/outbox architecture:

```
BOOKING_CONFIRMED → Calendar sync + Service execution auto-creation
BOOKING_CANCELLED → Calendar cancel + Mark service execution N/A
BOOKING_COMPLETED  → Payment prep tracking
BOOKING_IN_PROGRESS → Ensure service execution exists
```

Each operation is independently tracked in `booking_automation_status` with its own status, attempt count, and retry scheduling. Failures are isolated — a calendar sync failure does not affect communication delivery or booking state.

---

## Stripe / Payments / Commercial Policy

- **Stripe Connect** for business onboarding and direct charges
- **Payment lifecycle**: PENDING → PROCESSING → SUCCEEDED / FAILED with idempotency keys
- **Invoice generation** on service completion
- **Ledger entries** for financial tracking
- **Commercial policies** for platform fee configuration
- **Stripe webhooks** for payment event processing
- **Refund processing** with partial refund support

---

## Outbox / Event-Driven Architecture

FIELDed uses the **transactional outbox pattern** for reliable event processing:

1. Domain operations create `OutboxEvent` records in the same database transaction
2. Background worker polls every 5 seconds, claims events with `SELECT ... FOR UPDATE SKIP LOCKED`
3. Events processed through `OrchestrationService` (communications) and `BookingAutomationService` (calendar, execution, payment prep)
4. Each downstream operation is independently retryable and idempotent
5. Failures are tracked but do not corrupt authoritative state

Event types: `ENQUIRY_*`, `QUOTE_*`, `BOOKING_*`, `PAYMENT_*`, `BUSINESS_*`, `COMMUNICATION_*`, `REVIEW_*`

---

## Tenant Isolation

Tenant isolation is enforced at the repository layer:
- Every query is scoped to the authenticated user's tenant
- Businesses never access another business's data
- Customers only access their own data
- Authorization is resolved server-side from authenticated identity and database relationships
- Cross-tenant access is impossible by design

---

## Authentication / Authorization

- **Password hashing**: bcrypt
- **JWT** with access/refresh token rotation
- **Role-based access control**: OWNER, ADMIN, STAFF
- **Server-side authorization** on every protected resource
- **Rate limiting** on authentication endpoints
- **CORS** configured explicitly

---

## Production Architecture

```
                ┌──────────────────────┐
                │      FIELDed UI      │
                │   Cloudflare Worker  │
                └──────────┬───────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │    FIELDed API       │
                │      Cloud Run       │
                └──────────┬───────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
       Neon DB          Groq AI          Stripe
                                              │
                                              ▼
                                       Stripe Webhooks
          │
          ├──────────────► Resend
          │                 Email
          │
          ├──────────────► Vonage
          │                 SMS / WhatsApp / Voice
          │
          └──────────────► Google Calendar
                            Booking Automation
```

| Layer | Technology | Domain |
|-------|-----------|--------|
| Frontend | Next.js 15 + vinext → Cloudflare Workers | `https://fielded.online` |
| Backend | Python 3.12 + FastAPI → Cloud Run (Docker) | Cloud Run URL |
| Database | PostgreSQL 16 (Neon) | — |
| AI | Groq (OpenAI-compatible API) | — |
| Payments | Stripe Connect | — |
| Email | Resend | — |
| SMS / WhatsApp / Voice | Vonage | — |
| Calendar | Google Calendar API (OAuth) | — |
| CI/CD | GitHub Actions → Cloudflare Workers + Cloud Run | — |

---

## AI Provider Architecture & Groq's Role

AI operations use a provider-agnostic interface:

```python
AIProvider (abstract)
├── GroqProvider (Groq API — OpenAI-compatible)
├── OpenAIProvider (OpenAI API)
└── StubAIProvider (Mock/Testing)
```

**Groq** is the production AI provider, used through its OpenAI-compatible API endpoint. Different workloads can use dedicated API keys:

| Workload | Purpose | Override Variable |
|----------|---------|-------------------|
| Discovery | Natural language search interpretation | `DISCOVERY_AI_API_KEY` |
| Brain | Business Brain conversational AI | `BRAIN_AI_API_KEY` |
| Call Agent | Voice call agent AI | `CALL_AGENT_AI_API_KEY` |

Each workload falls back to the global `AI_API_KEY` when no workload-specific key is set.

---

## Deployment Architecture

- **Frontend**: Cloudflare Workers via `npx @vinext/cloudflare deploy`
- **Backend**: Docker container on Google Cloud Run via `cloudbuild.yaml`
- **Database**: Neon PostgreSQL (managed, serverless)
- **Secrets**: GCP Secret Manager (backend), Wrangler Secrets (frontend)
- **CI/CD**: GitHub Actions (lint → test → build → deploy)

---

## Environment Configuration

All configuration via environment variables. Pydantic Settings validates at startup.

| Category | Key Variables | Secret? |
|----------|--------------|---------|
| Core | `APP_SECRET_KEY`, `JWT_SECRET_KEY`, `DATABASE_URL` | Yes |
| AI | `AI_PROVIDER`, `AI_API_KEY`, `AI_BASE_URL`, `AI_MODEL` | Key is secret |
| Payments | `PAYMENT_PROVIDER`, `PAYMENT_API_KEY`, `PAYMENT_WEBHOOK_SECRET` | Keys are secret |
| Email | `EMAIL_PROVIDER`, `EMAIL_API_KEY`, `RESEND_WEBHOOK_SECRET` | Keys are secret |
| SMS/WhatsApp/Voice | `SMS_PROVIDER`, `VOICE_PROVIDER`, `WHATSAPP_PROVIDER`, `VONAGE_*` | Keys are secret |
| Calendar | `CALENDAR_PROVIDER`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` | Secret is secret |
| Frontend | `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | No (browser-safe) |

See `.env.example` for the complete variable list and [docs/fielded/PRODUCTION-CONFIGURATION.md](docs/fielded/PRODUCTION-CONFIGURATION.md) for the production readiness checklist.

---

## Webhook Architecture

All provider webhooks use signature verification:

| Provider | Endpoint | Verification |
|----------|----------|-------------|
| Stripe | `/api/v1/webhooks/payments/stripe` | `PAYMENT_WEBHOOK_SECRET` |
| Resend | `/api/v1/webhooks/communications/resend` | `RESEND_WEBHOOK_SECRET` |
| Vonage SMS | `/api/v1/webhooks/communications/vonage_sms` | `VONAGE_WEBHOOK_SECRET` |
| Vonage WhatsApp | `/api/v1/webhooks/communications/vonage_whatsapp` | `VONAGE_WEBHOOK_SECRET` |
| Vonage Voice | `/api/v1/webhooks/voice/vonage` | Application-level |
| Google Calendar | `/api/v1/calendar/oauth/callback` | OAuth state parameter |

All webhook URLs use the `PUBLIC_BASE_URL` prefix.

---

## Testing Status

| Category | Count | Status |
|----------|-------|--------|
| Unit test files | 33 | ✅ All passing |
| Integration test files | 27 | ✅ All passing |
| Security test files | 4 | ✅ All passing |
| Frontend test files | 1 | ✅ All passing |
| E2E test files | 3 | Browser + visual regression |
| Performance test files | 1 | Benchmark suite |
| **Total test files** | **69** | |
| **Total unit tests** | **818** | ✅ 0 failures |

Test categories: state machines, authorization, tenant isolation, pricing, booking lifecycle, payment processing, brain governance, communication orchestration, booking automation, calendar sync, JWT handling, rate limiting, URL validation.

---

## Database

- **56 tables** across **22 domain modules**
- **22 Alembic migrations** (001–022)
- Managed through Alembic with automatic migration on startup
- Tenant isolation enforced at repository layer
- Evidence tracking via JSONB fields on quotes, bookings, payments

---

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker (for local PostgreSQL and Redis)

### Local Development

```bash
# 1. Start infrastructure
docker compose -f docker/docker-compose.yml up -d

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example ../.env
uvicorn app.main:app --reload

# 3. Frontend
cd frontend
npm install
npm run dev
```

### Running Tests

```bash
# Backend unit tests (818 tests)
cd backend
pytest tests/unit/

# Backend integration tests (requires PostgreSQL)
pytest tests/integration/

# Backend security tests
pytest tests/security/

# Frontend tests
cd frontend
npm test
```

---

## Current Limitations / Configuration Required

### Configuration Required Before Operational

The following adapters are implemented but require real external credentials before they can process live transactions:

| Integration | What's Needed |
|-------------|---------------|
| **Stripe** | API key, webhook secret, Connect client ID |
| **Resend** | API key, verified sending domain, webhook secret |
| **Vonage** | Application ID, private key, phone numbers, webhook URLs |
| **Google Calendar** | OAuth client credentials, redirect URI, encryption key |
| **Groq** | API key per workload |

### Not Yet Verified Live

- Real payment processing (Stripe adapter exists, unit-tested, not verified with live credentials)
- Real email delivery (Resend adapter exists, unit-tested, not verified with live credentials)
- Real SMS/WhatsApp/Voice (Vonage adapters exist, unit-tested, not verified with live credentials)
- Real calendar sync (Google Calendar adapter exists, unit-tested, not verified with live OAuth flow)
- Real AI processing (Groq adapter exists, unit-tested, not verified with live API calls E2E)

### Not Yet Implemented

- WhatsApp Cloud API (Vonage WhatsApp adapter exists but not live-verified)
- Push notifications (stub provider only)
- Platform admin dashboard
- 2FA/MFA
- OAuth/social login
- Mobile apps

---

## Documentation

### Comprehensive Current-State Documentation

- [Product Definition](docs/fielded/PRODUCT.md) — What FIELDed currently is
- [Architecture](docs/fielded/ARCHITECTURE.md) — System architecture overview
- [Architecture Diagrams](docs/fielded/ARCHITECTURE-DIAGRAMS.md) — Mermaid diagrams
- [Business Brain](docs/fielded/BUSINESS-BRAIN.md) — Brain deep dive
- [AI Architecture](docs/fielded/AI-ARCHITECTURE.md) — AI provider architecture
- [Integrations](docs/fielded/INTEGRATIONS.md) — External integrations inventory
- [Production Configuration](docs/fielded/PRODUCTION-CONFIGURATION.md) — Production readiness checklist
- [Data Model](docs/fielded/DATA-MODEL.md) — Database schema
- [API Map](docs/fielded/API-MAP.md) — Complete API endpoint map
- [Workflows](docs/fielded/WORKFLOWS.md) — State machines and workflows
- [Features](docs/fielded/FEATURES.md) — Complete feature status
- [E2E Walkthrough](docs/fielded/E2E.md) — End-to-end transaction guide
- [Extensibility](docs/fielded/EXTENSIBILITY.md) — Extension points
- [Gaps](docs/fielded/GAPS.md) — Architecture and implementation gaps
- [Real Gaps](docs/fielded/REAL-GAPS.md) — Evidence-based gap analysis
- [Verification](docs/fielded/VERIFICATION.md) — Test coverage
- [Specifications](docs/fielded/SPECIFICATIONS.md) — Specification status
- [E2E Readiness](docs/fielded/E2E-READINESS.md) — E2E testing readiness

### Additional Documentation

- [Deployment](docs/deployment.md) — Production deployment instructions
- [Business Brain Specification](docs/business-brain-specification.md)
- [AI Governance](docs/ai-governance.md)
- [Authorization Model](docs/authorization-model.md)
- [Customer Journey](docs/customer-journey.md)
- [Testing Strategy](docs/testing-strategy.md)
- [Security](docs/security.md)
- [Domain Model](docs/domain-model.md)
- [Database](docs/database.md)
