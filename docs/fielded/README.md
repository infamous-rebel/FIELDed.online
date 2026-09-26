# FIELDed — Current State Documentation

**Purpose**: Canonical current-state baseline for the FIELDed platform.

**Last Updated**: 2026-09-26

**Scope**: Evidence-based documentation of what FIELDed currently is, how it works, what exists, what works E2E, what is partial, and what is not yet implemented.

---

## Document Index

| Document | Purpose |
|----------|---------|
| [PRODUCT.md](PRODUCT.md) | Product definition — what FIELDed currently is |
| [FEATURES.md](FEATURES.md) | Complete feature inventory with status classifications |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture overview |
| [ARCHITECTURE-DIAGRAMS.md](ARCHITECTURE-DIAGRAMS.md) | Mermaid architecture diagrams |
| [BUSINESS-BRAIN.md](BUSINESS-BRAIN.md) | Business Brain deep dive |
| [AI-ARCHITECTURE.md](AI-ARCHITECTURE.md) | AI provider architecture |
| [E2E.md](E2E.md) | End-to-end transaction walkthrough |
| [INTEGRATIONS.md](INTEGRATIONS.md) | External integrations inventory |
| [DATA-MODEL.md](DATA-MODEL.md) | Database schema and entity relationships |
| [API-MAP.md](API-MAP.md) | Complete API endpoint map |
| [WORKFLOWS.md](WORKFLOWS.md) | State machines and workflow documentation |
| [EXTENSIBILITY.md](EXTENSIBILITY.md) | Architecture extension points |
| [GAPS.md](GAPS.md) | Architecture and implementation gaps |
| [VERIFICATION.md](VERIFICATION.md) | Test coverage and verification status |
| [SPECIFICATIONS.md](SPECIFICATIONS.md) | Specification implementation status |
| [PRODUCTION-CONFIGURATION.md](PRODUCTION-CONFIGURATION.md) | Production readiness checklist and configuration guide |
| [E2E-READINESS.md](E2E-READINESS.md) | E2E testing readiness assessment |

---

## Classification System

Every feature and specification is classified using these exact states:

| Status | Meaning |
|--------|---------|
| **A. FULLY WORKING** | Implemented and verified through actual executable path/E2E test |
| **B. WORKING — TARGETED** | Implemented and verified for specific operation/path, not complete E2E |
| **C. PARTIAL** | Some implementation works, but important part is missing/disconnected/mocked |
| **D. IMPLEMENTED — UNVERIFIED** | Code/API/UI exists, insufficient evidence that real operation works |
| **E. STUB/MOCK** | Capability exists only through mock, stub, fake, or placeholder |
| **F. NOT IMPLEMENTED** | Required capability/specification is absent |
| **G. BLOCKED BY EXTERNAL CREDENTIAL/PROVIDER** | Implementation exists but cannot verify due to external provider unavailability |

---

## Quick Summary

### Technology Stack
- **Backend**: Python 3.12 + FastAPI
- **Frontend**: Next.js 15 + TypeScript
- **Database**: PostgreSQL 16
- **ORM**: SQLAlchemy 2.0 (async)
- **Migrations**: Alembic (22 migrations)
- **Auth**: bcrypt + PyJWT
- **AI Providers**: Groq (OpenAI-compatible), OpenAI, Mock/Stub
- **Payments**: Stripe Connect adapter (stub for dev/test)
- **Communications**: Vonage (SMS/WhatsApp/Voice), Resend (Email), Twilio (legacy), Stub providers
- **Calendar**: Google Calendar API (OAuth, per-business)
- **Deployment**: Cloudflare Workers (frontend, vinext), Docker/Cloud Run (backend)
- **CI/CD**: GitHub Actions

### Repository Statistics
- **Backend Python files**: ~222
- **Frontend TypeScript files**: ~62
- **Database migrations**: 22
- **Domain modules**: 22 (+ `common` shared utilities)
- **API route modules**: 26
- **Test files**: 69 (unit, integration, security, e2e, performance, frontend)

### Key Numbers
- **Backend routes**: ~80 endpoints
- **Frontend pages**: ~30 routes
- **Database models**: 56 tables
- **Domain services**: ~30
- **Repositories**: ~25
- **Total unit tests**: 818 (0 failures)

---

## What FIELDed Currently Is

FIELDed is a **customer-to-business service network** with two equally important sides:

### Customer Side
- Search and discover businesses
- Browse service offers
- Initiate enquiries
- Communicate with businesses
- Receive quotes
- Book services
- Make payments
- Leave reviews

### Business Side
- Business profile management
- Service catalog management
- Business Brain (AI-governed rule system)
- Enquiry handling
- Quote generation
- Booking management
- Service execution tracking
- Payment processing
- Review management
- Communications hub

### Business Brain
The Business Brain is FIELDed's differentiating feature — a versioned, AI-governed rule system where:
- AI proposes business knowledge (services, pricing, policies, availability)
- Owners approve/reject proposals
- Approved changes enter governed Brain state
- Deterministic rules remain authoritative
- AI never silently mutates production state

---

## How to Use This Documentation

1. **New to FIELDed?** Start with [PRODUCT.md](PRODUCT.md) and [E2E.md](E2E.md)
2. **Understanding architecture?** Read [ARCHITECTURE.md](ARCHITECTURE.md) and review [ARCHITECTURE-DIAGRAMS.md](ARCHITECTURE-DIAGRAMS.md)
3. **What works?** Check [FEATURES.md](FEATURES.md) for status of every feature
4. **What's missing?** See [GAPS.md](GAPS.md) for identified gaps
5. **Extending the system?** Review [EXTENSIBILITY.md](EXTENSIBILITY.md)
6. **Testing status?** Check [VERIFICATION.md](VERIFICATION.md)

---

## Important Distinctions

This documentation strictly separates:
- **Currently implemented product** vs **intended/future product**
- **Tested and verified** vs **implemented but unverified**
- **Real providers** vs **mocks/stubs**
- **Current architecture** vs **future extension points**

No feature is counted as "working" merely because:
- A route exists
- A component exists
- Tests exist
- A database model exists
- A button exists
- An API returns HTTP 200
- A mock provider returns successfully

---

## Running FIELDed Locally

```bash
# 1. Start infrastructure (PostgreSQL, Redis)
docker compose -f docker/docker-compose.yml up -d

# 2. Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example ../.env
uvicorn app.main:app --reload

# 3. Frontend
cd frontend
npm install
npm run dev
```

### Required Services
- PostgreSQL 16
- Redis 7+ (optional for development)

### Environment Variables (by name only)
See [E2E.md](E2E.md) for complete environment variable documentation.

---

## Documentation Quality

This documentation:
- Describes **current reality**
- Distinguishes implementation from intention
- Distinguishes tested from untested
- Distinguishes real providers from mocks
- Includes evidence
- Avoids marketing language
- Avoids unsupported claims
- Avoids invented features
- Avoids representing future architecture as current
- Contains no secrets or credentials

---

## For Future AI Agents

This documentation package is designed to allow future AI agents to understand FIELDed without rediscovering the system. Every claim is traceable to actual code, tests, or verified behavior.

When modifying this documentation:
1. Verify claims against actual implementation
2. Update status classifications when features change
3. Maintain the distinction between current and future
4. Never represent intended behavior as current behavior
