# FIELDed — System Architecture

**Status**: Current State Baseline  
**Last Updated**: 2026-09-24

---

## Architecture Overview

FIELDed follows a **monorepo architecture** with separate frontend and backend applications, connected through a REST API. The system is designed around **domain-driven design** principles with clear separation of concerns, provider-agnostic adapters, and deterministic business logic.

---

## Technology Stack

### Backend
- **Language**: Python 3.12
- **Framework**: FastAPI
- **ORM**: SQLAlchemy 2.0 (async)
- **Database**: PostgreSQL 16
- **Migrations**: Alembic
- **Authentication**: bcrypt + PyJWT
- **Validation**: Pydantic
- **Testing**: pytest + httpx

### Frontend
- **Language**: TypeScript (strict mode)
- **Framework**: Next.js 15 (App Router)
- **Styling**: Tailwind CSS 4
- **Build**: Turborepo (monorepo)

### Infrastructure
- **Database**: PostgreSQL 16
- **Cache**: Redis 7+ (optional for development)
- **Deployment**: Vercel (frontend), Docker/Cloud Run (backend)
- **CI/CD**: GitHub Actions
- **Containerization**: Docker + Docker Compose

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         CLIENTS                              │
│  (Web Browser, Mobile App - Future)                         │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (Next.js 15)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Public Pages │  │Customer Pages│  │Business Pages│      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         API Client (fetch/axios)                     │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────┘
                         │ REST API (JSON)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  BACKEND (FastAPI)                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Middleware Stack                         │  │
│  │  CORS → Rate Limit → Request ID → Correlation → Tenant│ │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              API Routes (v1)                          │  │
│  │  auth, customer, businesses, enquiries, quotes,      │  │
│  │  bookings, payments, brain, communications, etc.     │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Domain Services                          │  │
│  │  identity, enquiry, quote, booking, payment, brain,  │  │
│  │  communication, review, service_execution, etc.      │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Repositories                             │  │
│  │  (Data access layer - tenant-scoped)                 │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Adapter Layer                            │  │
│  │  AI, Email, SMS, Voice, WhatsApp, Push, Payment      │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Outbox Worker (Background)               │  │
│  │  (Processes outbox events for notifications/comms)   │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  PostgreSQL  │  │    Redis     │  │  External    │
│   (Database) │  │   (Cache)    │  │  Providers   │
└──────────────┘  └──────────────┘  └──────────────┘
```

---

## Backend Architecture

### Layered Architecture

The backend follows a **layered architecture** pattern:

1. **API Layer** (`app/api/`): HTTP request handling, routing, validation
2. **Domain Layer** (`app/domain/`): Business logic, domain services, state machines
3. **Repository Layer** (`app/domain/*/repository.py`): Data access, tenant-scoped queries
4. **Adapter Layer** (`app/adapters/`): External service integrations
5. **Infrastructure Layer** (`app/main.py`, `app/database.py`, `app/config.py`): Application setup

### Domain Modules

The backend is organized into **15 domain modules**:

| Module | Purpose | Key Entities |
|--------|---------|--------------|
| `identity` | User authentication, customer profiles, businesses, members | User, CustomerProfile, Business, BusinessMember |
| `enquiry` | Customer enquiries and conversations | Enquiry, Conversation, Message |
| `quote` | Quote generation and pricing | Quote |
| `booking` | Service bookings and availability | Booking |
| `payment` | Payment processing and refunds | Payment, PaymentAttempt |
| `invoice` | Invoice generation and management | Invoice |
| `ledger` | Financial ledger entries | LedgerEntry |
| `service_execution` | Service execution tracking | ServiceExecution |
| `review` | Customer reviews and ratings | Review |
| `business` | Business Brain and rules | BusinessBrain, BrainVersion, BusinessRule, BrainConversation, BrainMessage, BrainProposal |
| `discovery` | Business/service discovery | (uses identity and services modules) |
| `communication` | Communications and notifications | Communication, Notification, OutboxEvent, Template |
| `voice` | Voice call agent | Call, CallSession, CallAttempt, Escalation, Campaign |
| `notification` | In-app notifications | Notification |
| `outbox` | Transactional outbox pattern | OutboxEvent |
| `services` | Service offers and categories | ServiceOffer, ServiceCategory |

### Middleware Stack

The backend uses a **middleware stack** for cross-cutting concerns:

1. **CORSMiddleware**: Cross-origin resource sharing
2. **RateLimitMiddleware**: API rate limiting
3. **RequestIdMiddleware**: Request ID generation and tracking
4. **CorrelationIdMiddleware**: Correlation ID for distributed tracing
5. **TenantMiddleware**: Tenant resolution and isolation

### Provider Factory

External services are accessed through a **ProviderFactory** that resolves configured adapters:

```python
ProviderFactory
├── email_provider (EmailProvider)
├── sms_provider (SMSProvider)
├── voice_provider (VoiceProvider)
├── whatsapp_provider (WhatsAppProvider)
├── push_provider (PushProvider)
└── payment_provider (PaymentProvider)
```

Providers are selected via environment variables and injected into domain services.

### Outbox Worker

The backend includes a **background outbox worker** that processes outbox events for notifications and communications:

- Polls every 15 seconds
- Processes pending outbox events
- Sends notifications via configured providers
- Handles retries for failed events
- Runs inside the FastAPI process (no separate worker needed)

---

## Frontend Architecture

### App Router Structure

The frontend uses **Next.js 15 App Router** with the following structure:

```
src/app/
├── (public)/              # Public pages (no auth required)
│   ├── page.tsx          # Landing page
│   ├── login/            # Login page
│   ├── signup/           # Signup page
│   ├── search/           # Business search
│   ├── network/          # Business network
│   ├── business/[slug]/  # Public business profile
│   └── members/          # Member invitation acceptance
├── (customer)/           # Customer pages (auth required)
│   ├── customer/
│   │   ├── dashboard/    # Customer dashboard
│   │   ├── enquiries/    # Customer enquiries
│   │   ├── bookings/     # Customer bookings
│   │   ├── quotes/       # Customer quotes
│   │   ├── payments/     # Customer payments
│   │   ├── transactions/ # Transaction history
│   │   ├── history/      # Service history
│   │   ├── profile/      # Customer profile
│   │   └── account/      # Account settings
│   └── customer-nav.tsx  # Customer navigation
└── (business)/           # Business pages (auth required)
    ├── business/
    │   ├── dashboard/    # Business dashboard
    │   ├── enquiries/    # Business enquiries
    │   ├── bookings/     # Business bookings
    │   ├── quotes/       # Business quotes
    │   ├── payments/     # Business payments
    │   ├── services/     # Service offers
    │   ├── brain/        # Business Brain
    │   ├── finance/      # Finance page
    │   ├── schedule/     # Schedule page
    │   ├── operations/   # Operations page
    │   ├── communications/ # Communications hub
    │   ├── profile/      # Business profile
    │   ├── settings/     # Business settings
    │   └── onboarding/   # Business onboarding
    └── business-nav.tsx  # Business navigation
```

### Component Library

The frontend includes a **component library** in `src/components/ui/`:

- Avatar
- Badge
- Button
- Card
- EmptyState
- Input
- LoadingSkeleton
- And more...

### API Integration

The frontend communicates with the backend via **REST API calls**:

- Base URL: Configured via `NEXT_PUBLIC_API_URL` environment variable
- Authentication: JWT tokens stored in localStorage/cookies
- Request/Response: JSON format
- Error Handling: Centralized error handling

---

## Database Architecture

### Schema Organization

The database schema is organized by domain:

- **Identity**: users, customer_profiles, businesses, business_profiles, business_members
- **Services**: service_offers, service_categories
- **Enquiry**: enquiries, conversations, messages
- **Quote**: quotes
- **Booking**: bookings
- **Payment**: payments, payment_attempts, payment_webhooks
- **Invoice**: invoices
- **Ledger**: ledger_entries
- **Service Execution**: service_executions
- **Review**: reviews
- **Business Brain**: business_brains, brain_versions, business_rules, brain_conversations, brain_messages, brain_proposals
- **Communication**: communications, notifications, communication_templates, outbox_events
- **Voice**: calls, call_sessions, call_attempts, escalations, campaigns, campaign_recipients
- **Invitations**: business_invitations

### Migrations

Database schema is managed through **Alembic migrations**:

- 16 migrations total
- Sequential numbering (001-016)
- Each migration is idempotent
- Migrations are reversible (up/down)

### Tenant Isolation

**Tenant isolation** is enforced at the repository layer:

- Every query is scoped to the authenticated user's tenant
- Businesses never access another business's data
- Customers only access their own data
- Authorization is resolved server-side from authenticated identity

---

## API Architecture

### REST API Design

The API follows **REST conventions**:

- Base path: `/api/v1/`
- Resource-oriented URLs
- Standard HTTP methods (GET, POST, PUT, PATCH, DELETE)
- JSON request/response bodies
- Standard HTTP status codes

### API Route Organization

API routes are organized by domain:

```
/api/v1/
├── /health                    # Health check
├── /auth                      # Authentication
├── /customer                  # Customer operations
├── /businesses                # Business operations
│   ├── /{business_id}/enquiries
│   ├── /{business_id}/brain
│   ├── /{business_id}/brain-conversations
│   └── ...
├── /categories                # Service categories
├── /public                    # Public operations
├── /discovery                 # Discovery/search
├── /enquiries                 # Enquiry operations
├── /communications            # Communication operations
├── /voice                     # Voice call operations
├── /payments                  # Payment operations
└── /reviews                   # Review operations
```

### Authentication & Authorization

- **Authentication**: JWT tokens (access + refresh)
- **Authorization**: Role-based access control (RBAC)
- **Tenant Isolation**: Repository-level enforcement
- **Server-Side**: All authorization resolved server-side

---

## AI Provider Architecture

### Provider Abstraction

All AI operations use a **provider-agnostic interface**:

```python
AIProvider (abstract)
├── GroqProvider (Groq API)
├── OpenAIProvider (OpenAI API)
└── StubAIProvider (Mock/Testing)
```

### Workload-Specific Providers

Different AI workloads can use different providers/keys:

- **Discovery**: Natural language search interpretation
- **Brain**: Business Brain conversational AI
- **Call Agent**: Voice call agent AI

Each workload can have dedicated API keys and base URLs, with fallback to global configuration.

### AI Governance

AI intelligence is separated from business authority:

- **AI Can**: Interpret, classify, extract, summarize, recommend, draft
- **AI Cannot**: Set prices, determine availability, override policies, authorize users, change transaction state

All AI proposals flow through deterministic validation and owner approval.

---

## Business Brain Architecture

### Brain Structure

Each business has a **BusinessBrain** with versioned configurations:

```
BusinessBrain
└── BrainVersion (multiple, one ACTIVE)
    ├── identity_config
    ├── services_config
    ├── pricing_config
    ├── availability_config
    ├── qualification_config
    ├── policies_config
    ├── escalation_config
    ├── communication_config
    └── BusinessRule (multiple)
```

### Brain Lifecycle

Brain versions follow a strict lifecycle:

```
DRAFT → VALIDATING → REVIEW → APPROVED → ACTIVE → SUPERSEDED
```

### Interactive Co-Brain

The Brain includes an **interactive co-brain** layer:

```
BrainConversation
├── BrainMessage (multiple)
└── BrainProposal (multiple)
    └── Lifecycle: PENDING → APPROVED/REJECTED → APPLIED
```

### Governance

- AI generates proposals
- Owner approves/rejects proposals
- Approved proposals applied to Brain state
- Brain versions are immutable after DRAFT
- Transactions retain brain version for traceability

---

## Communication Architecture

### Channels

FIELDed supports multiple communication channels:

- **EMAIL**: Resend adapter
- **SMS**: Twilio adapter
- **VOICE**: Twilio adapter
- **WHATSAPP**: Stub (not yet implemented)
- **PUSH**: Stub (not yet implemented)
- **IN_APP**: Internal notification system

### Orchestration

Communications are orchestrated through:

1. **Policy Engine**: Determines if communication is allowed
2. **Template System**: Template-based message generation
3. **Outbox Pattern**: Transactional outbox for reliable delivery
4. **Provider Adapters**: Channel-specific delivery

### Voice Call Agent

The voice call agent provides AI-powered voice calls:

1. Call requested
2. Call authorized (policy check)
3. Call queued
4. Call initiated via Twilio
5. AI agent conducts conversation
6. Call outcome recorded
7. Escalation to human if needed

---

## Payment Architecture

### Provider Abstraction

Payments use a **provider-agnostic interface**:

```python
PaymentProvider (abstract)
├── StripePaymentProvider (Stripe API)
└── StubPaymentProvider (Mock/Testing)
```

### Payment Flow

1. Payment initiated with idempotency key
2. Payment attempt created
3. Payment processed through provider
4. Provider webhook received
5. Payment status updated
6. Invoice balance updated
7. Ledger entries created

### Refund Flow

1. Refund requested
2. Refund processed through provider
3. Refund webhook received
4. Payment status updated
5. Ledger entries created

---

## Deployment Architecture

### Development

```bash
# Infrastructure
docker compose -f docker/docker-compose.yml up -d

# Backend
cd backend
uvicorn app.main:app --reload

# Frontend
cd frontend
npm run dev
```

### Production

- **Frontend**: Vercel (automatic deployments from Git)
- **Backend**: Docker container on Cloud Run (or similar)
- **Database**: Managed PostgreSQL (Neon, Supabase, or similar)
- **Cache**: Managed Redis (optional)

### CI/CD

GitHub Actions workflow:

1. **Backend Lint**: Ruff linting and formatting
2. **Backend Test**: Unit, integration, security tests
3. **Frontend Build**: Build and verify frontend

---

## Security Architecture

### Authentication

- **Password Hashing**: bcrypt
- **JWT Tokens**: Access + refresh tokens
- **Token Rotation**: Refresh token rotation
- **Token Revocation**: Token blacklisting

### Authorization

- **Role-Based Access Control**: OWNER, ADMIN, STAFF roles
- **Tenant Isolation**: Repository-level enforcement
- **Server-Side**: All authorization resolved server-side

### Middleware

- **CORS**: Configured explicitly
- **Rate Limiting**: Auth endpoint protection
- **Request ID**: Request tracking
- **Correlation ID**: Distributed tracing
- **Tenant Middleware**: Tenant resolution

### Audit Trail

- **Audit Events**: All meaningful actions logged
- **Evidence Tracking**: Transaction evidence preserved
- **Immutable Records**: Historical records never modified

---

## Extension Points

The architecture supports extension in these areas:

- **New Service Categories**: Add to service_categories table
- **New Service Types**: Extend ServiceOffer model
- **New Business Types**: Extend Business model
- **New Payment Providers**: Implement PaymentProvider interface
- **New Communication Providers**: Implement channel provider interface
- **New AI Providers**: Implement AIProvider interface
- **New AI Workloads**: Add workload-specific resolvers
- **New Brain Rules**: Extend BusinessRule model
- **New Audit Events**: Add to AuditEventType enum

See [EXTENSIBILITY.md](EXTENSIBILITY.md) for detailed extension point documentation.

---

## Architecture Principles

1. **AI intelligence != business authority**: AI proposes, deterministic rules authorize
2. **Deterministic domain logic is authoritative**: Critical decisions flow through validated domain rules
3. **Provider-agnostic architecture**: No hardcoded dependencies on external providers
4. **Tenant isolation is foundational**: Repository-level enforcement
5. **Explicit state machines**: All lifecycles use validated state machines
6. **Schema-first domain model**: Strong typing, database constraints, validation
7. **Append-oriented evidence**: Historical records never overwritten
8. **Audit trail for all actions**: Every meaningful action generates audit events
