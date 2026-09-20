# FIELDed — Architecture

## Overview

FIELDed is a customer-to-business service network built as a monorepo with clear backend/frontend separation.

## Technology Stack

| Layer | Technology | Justification |
|-------|-----------|---------------|
| Backend | Python 3.12 + FastAPI | Async, typed, OpenAPI, mature ecosystem |
| Frontend | Next.js 15 + TypeScript | SSR/SSG for SEO, App Router, Vercel-ready |
| Database | PostgreSQL 16 | Relational integrity, constraints, JSONB |
| ORM | SQLAlchemy 2.0 (async) | Mature, typed, complex relationship support |
| Migrations | Alembic | Standard Python migration tool |
| Auth | bcrypt + PyJWT | Self-hosted, adapter pattern for future swap |
| Cache | Redis (adapter) | Sessions, caching, future job queue |
| Testing | pytest + httpx / Vitest | Industry standard |
| Monorepo | Turborepo | Manages backend + frontend |
| CI | GitHub Actions | Standard, well-supported |
| Styling | Tailwind CSS 4 | Utility-first, Next.js ecosystem |

## System Architecture

```
                    Internet
                       |
                 Next.js Frontend
                       |
                FastAPI Backend (/api/v1)
                       |
          +------------+------------+
          |            |            |
     PostgreSQL     Redis     Object Storage
          |            |            |
          +----- Adapter Layer -----+
                   |
          AI / Email / SMS / Calendar
```

## Key Principles

1. **Provider-agnostic**: All external services behind adapter interfaces
2. **Deterministic domain logic**: AI proposes, rules decide
3. **Tenant isolation**: Enforced at repository layer
4. **Explicit state machines**: All lifecycle transitions validated
5. **Async-first**: I/O-bound operations use async/await
6. **Schema-first**: Database constraints enforce invariants

## Repository Structure

```
FIELDed/
├── backend/          # Python FastAPI application
├── frontend/         # Next.js application
├── docker/           # Docker Compose for dev/test
├── docs/             # Architecture documentation
├── .github/          # CI/CD workflows
├── AGENTS.md         # Engineering rules for AI sessions
└── turbo.json        # Monorepo configuration
```

## Backend Architecture

```
app/
├── main.py           # App factory, lifecycle, exception handlers
├── config.py         # Pydantic Settings (env-based)
├── database.py       # SQLAlchemy async engine + sessions
├── exceptions.py     # Exception hierarchy
├── logging.py        # Structured JSON logging
├── middleware/       # Request ID, correlation ID, tenant
├── api/              # Route handlers (versioned)
├── domain/           # Domain models, schemas, services, repositories
├── security/         # Password, JWT, authorization
└── adapters/         # Abstract interfaces for external services
```

## Frontend Architecture

```
src/app/
├── (public)/         # Landing, search, login, signup, business profiles
├── (customer)/       # Customer dashboard, enquiries, bookings
└── (business)/       # Business dashboard, services, brain, enquiries
```
