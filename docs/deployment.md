# FIELDed — Deployment

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

| Layer | Technology | URL |
|-------|-----------|-----|
| Frontend | Next.js 15 + vinext → Cloudflare Workers | `https://fielded.online` |
| Backend | Python 3.12 + FastAPI → Cloud Run (Docker) | `https://fielded-api-meftvuaodq-uc.a.run.app` |
| Database | PostgreSQL 16 (Neon) | — |
| Payments | Stripe | — |
| AI | Groq (OpenAI-compatible API) | — |
| Email | Resend | — |
| SMS / WhatsApp / Voice | Vonage | — |
| Calendar | Google Calendar API (OAuth) | — |
| CI/CD | GitHub Actions | — |

FIELDed is the system of record. Stripe, Google Calendar, Resend, and Vonage are external adapters — none of them override FIELDed's authoritative state.

---

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

---

## Environment Boundaries

| Variable | Development | Production |
|----------|------------|------------|
| `APP_ENV` | `development` | `production` |
| `APP_DEBUG` | `true` | `false` |
| Database | Local PostgreSQL (Docker) | Neon (managed PostgreSQL) |
| Secrets | Default values OK | Must be set (GCP Secret Manager) |
| Providers | All `mock` | Real providers configured |

---

## Docker Compose

### Development (`docker/docker-compose.yml`)
- PostgreSQL 16 (persistent volume)
- Redis 7 (persistent volume)

### Test (`docker/docker-compose.test.yml`)
- PostgreSQL 16 (tmpfs, isolated)
- Separate database: `fielded_test`

---

## CI/CD

GitHub Actions workflow (`.github/workflows/ci.yml`):

1. **Backend Lint** — ruff check + format
2. **Backend Test** — unit + integration + security (with PostgreSQL service)
3. **Frontend Build** — vinext build (Cloudflare Workers)
4. **Frontend Deploy** — `npx @vinext/cloudflare deploy` (main branch only)

Required GitHub secrets:
- `CLOUDFLARE_API_TOKEN` — Cloudflare API token with Workers edit permission
- `CLOUDFLARE_ACCOUNT_ID` — Cloudflare account identifier

---

## Frontend Deployment (Cloudflare Workers)

The frontend is a Next.js 15 application built with [vinext](https://github.com/nicolo-ribaudo/vinext) and deployed to Cloudflare Workers.

### Configuration
- `frontend/wrangler.jsonc` — Cloudflare Workers deployment config
- `frontend/next.config.ts` — Next.js configuration (standalone output)
- `frontend/package.json` — Scripts: `dev`, `build`, `deploy`

### Deploy

```bash
cd frontend

# Authenticate
npx wrangler login

# Deploy to production
npm run deploy

# Deploy preview
npm run deploy:preview
```

### Custom Domain

After first deploy, attach the custom domain:

```bash
npx wrangler custom-domain add fielded.online fielded-frontend
npx wrangler custom-domain add www.fielded.online fielded-frontend
```

### Frontend Environment Variables

Only `NEXT_PUBLIC_*` variables are exposed to the browser. **No secrets** should ever be set in the frontend.

| Variable | Type | Source | Description |
|----------|------|--------|-------------|
| `NEXT_PUBLIC_API_URL` | Non-secret | `wrangler.jsonc` → `vars` | Backend API base URL |
| `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | Public (browser-safe) | `wrangler.jsonc` → `vars` | Stripe publishable key |

To set secrets via Wrangler (if needed in future):
```bash
npx wrangler secret put <NAME>
```

---

## Backend Deployment (Cloud Run)

The backend is a FastAPI application packaged as a Docker container and deployed to Google Cloud Run.

### Configuration
- `Dockerfile` — Multi-stage container build
- `cloudbuild.yaml` — Cloud Build pipeline (build → push → deploy)
- `deploy/cloudrun-env.yaml` — Production non-secret environment variables

### Deploy

```bash
# Build and push via Cloud Build
gcloud builds submit --project=fielded-online \
  --tag us-central1-docker.pkg.dev/fielded-online/fielded/fielded-api:latest .

# Deploy to Cloud Run
gcloud run deploy fielded-api \
  --project=fielded-online \
  --image us-central1-docker.pkg.dev/fielded-online/fielded/fielded-api:latest \
  --region us-central1 \
  --port 8000 \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 3 \
  --allow-unauthenticated \
  --env-vars-file deploy/cloudrun-env.yaml \
  --set-secrets APP_SECRET_KEY=APP_SECRET_KEY:latest,JWT_SECRET_KEY=JWT_SECRET_KEY:latest,...
```

### Secrets (GCP Secret Manager)

Production secrets are stored in GCP Secret Manager and attached at runtime via `--set-secrets` in `cloudbuild.yaml`.

**Core secrets**:
| Secret | Description |
|--------|-------------|
| `APP_SECRET_KEY` | Application secret (random, ≥32 chars) |
| `JWT_SECRET_KEY` | JWT signing key (random, ≥32 chars) |
| `DATABASE_URL` | Neon PostgreSQL connection string |

**AI secrets**:
| Secret | Description |
|--------|-------------|
| `BRAIN_AI_API_KEY` | Groq API key for Business Brain |
| `DISCOVERY_AI_API_KEY` | Groq API key for Discovery |
| `CALL_AGENT_AI_API_KEY` | Groq API key for Call Agent |

**Payment secrets**:
| Secret | Description |
|--------|-------------|
| `PAYMENT_API_KEY` | Stripe secret key |
| `PAYMENT_WEBHOOK_SECRET` | Stripe webhook signing secret |

**Communication secrets**:
| Secret | Description |
|--------|-------------|
| `EMAIL_API_KEY` | Resend API key |
| `RESEND_WEBHOOK_SECRET` | Resend webhook signing secret |
| `VONAGE_API_KEY` | Vonage API key |
| `VONAGE_API_SECRET` | Vonage API secret |
| `VONAGE_APPLICATION_PRIVATE_KEY` | Vonage Application RSA private key (PEM) |
| `VONAGE_WEBHOOK_SECRET` | Vonage webhook signing secret |

**Calendar secrets**:
| Secret | Description |
|--------|-------------|
| `GOOGLE_OAUTH_CLIENT_SECRET` | Google OAuth client secret |
| `GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY` | Fernet key for OAuth token encryption |

### CORS

Backend CORS origins are configured via `BACKEND_CORS_ORIGINS` in `deploy/cloudrun-env.yaml`:

```
https://fielded.online,https://www.fielded.online,http://localhost:3000
```

---

## Configuration

All configuration via environment variables. Pydantic Settings validates at startup.

### Provider Selection

| Variable | Options | Default |
|----------|---------|---------|
| `AI_PROVIDER` | `groq`, `openai`, `mock` | `mock` |
| `PAYMENT_PROVIDER` | `stripe`, `mock` | `mock` |
| `EMAIL_PROVIDER` | `resend`, `mock` | `mock` |
| `SMS_PROVIDER` | `vonage`, `twilio`, `mock` | `mock` |
| `VOICE_PROVIDER` | `vonage`, `twilio`, `mock` | `mock` |
| `WHATSAPP_PROVIDER` | `vonage_whatsapp`, `mock` | `mock` |
| `CALENDAR_PROVIDER` | `google`, `mock` | `mock` |

### Production Validation

- `APP_SECRET_KEY` cannot be default value in production
- `JWT_SECRET_KEY` cannot be default value in production

See [PRODUCTION-CONFIGURATION.md](fielded/PRODUCTION-CONFIGURATION.md) for the complete configuration reference.

---

## Portability

The architecture supports deployment to any platform:
- Frontend: Any Cloudflare Workers-compatible host (or Vercel, Netlify)
- Backend: Any Docker-compatible host (Cloud Run, ECS/Fargate, Fly.io, etc.)
- Database: Any PostgreSQL 16 provider (Neon, Supabase, RDS, etc.)
