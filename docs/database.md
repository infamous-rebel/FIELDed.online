# FIELDed — Database

## Strategy

- **Engine**: PostgreSQL 16
- **Driver**: asyncpg (async PostgreSQL adapter)
- **ORM**: SQLAlchemy 2.0 with async sessions
- **Migrations**: Alembic with async support

## Conventions

### Primary Keys
- UUID (v4) for all entities
- Generated at application level via `uuid.uuid4()`

### Timestamps
- `created_at` — set on insert, immutable
- `updated_at` — auto-updated on every modification
- `deleted_at` — nullable, enables soft delete

### All tables include:
```sql
id UUID PRIMARY KEY
created_at TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
deleted_at TIMESTAMPTZ NULL
```

### JSONB Usage
Flexible configuration data stored as JSONB:
- Brain version config areas (identity, pricing, policies, etc.)
- Service offer pricing_config, qualification_requirements, booking_rules
- Business rule rule_data

### Constraints
- Database-level UNIQUE constraints where applicable
- Foreign keys with explicit ON DELETE behavior (CASCADE or SET NULL)
- CHECK constraints for enum-like string columns (future)
- **Partial unique index** on `brain_versions(brain_id)` WHERE `status = 'active' AND deleted_at IS NULL` — enforces at most one ACTIVE BrainVersion per business at the database level (migration 006)

## Tenant Isolation
- No row-level security (RLS) — isolation enforced at repository layer
- Every query must be scoped to the authenticated user's tenant
- Cross-tenant access is impossible by design

## Migration Management
- Migrations live in `backend/alembic/versions/`
- Sequential naming: `001_initial_schema.py`, `002_add_xxx.py`
- Always test migrations against a fresh database
- Never modify a migration that has been applied in staging/production

## Connection Pooling
- Pool size: configurable (default 20)
- Max overflow: configurable (default 10)
- Pool pre-ping enabled for connection health checks
