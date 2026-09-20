# FIELDed — Deployment

## Local Development

### Prerequisites
- Python 3.12+
- Node.js 20+
- Docker (for PostgreSQL and Redis)

### Setup

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

## Environment Boundaries

| Variable | Development | Staging | Production |
|----------|------------|---------|------------|
| APP_ENV | development | staging | production |
| APP_DEBUG | true | false | false |
| Database | Local PostgreSQL | Managed PostgreSQL | Managed PostgreSQL |
| Secrets | Default values OK | Must be set | Must be set |

## Docker Compose

### Development (`docker/docker-compose.yml`)
- PostgreSQL 16 (persistent volume)
- Redis 7 (persistent volume)

### Test (`docker/docker-compose.test.yml`)
- PostgreSQL 16 (tmpfs, isolated)
- Separate database: `fielded_test`

## CI/CD

GitHub Actions workflow (`.github/workflows/ci.yml`):
1. **Backend Lint**: ruff check + format
2. **Backend Test**: unit + integration + security (with PostgreSQL service)
3. **Frontend Build**: npm install + next build

## Configuration

All configuration via environment variables. Pydantic Settings validates at startup.

Key variables:
- `APP_ENV` — environment boundary
- `APP_SECRET_KEY` — application secret
- `DATABASE_URL` — PostgreSQL connection string
- `JWT_SECRET_KEY` — JWT signing key
- `BACKEND_CORS_ORIGINS` — allowed CORS origins

Production validation:
- `APP_SECRET_KEY` cannot be default value
- `JWT_SECRET_KEY` cannot be default value

## Future Deployment Targets

The architecture supports deployment to:
- Vercel (frontend) + Railway/Fly.io (backend + PostgreSQL)
- AWS (ECS/Fargate + RDS)
- Google Cloud (Cloud Run + Cloud SQL)
- Any platform with Docker support

Provider-specific deployment guides will be added when deployment target is selected.
