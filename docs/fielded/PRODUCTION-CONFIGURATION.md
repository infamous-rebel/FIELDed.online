# FIELDed — Production Configuration Guide

**Purpose**: Document exactly which configuration is required before each integration becomes operational.  
**Last Updated**: 2026-09-26

---

## Overview

FIELDed uses environment variables exclusively for configuration. No credentials are hardcoded. Secrets are managed through GCP Secret Manager (backend) and Wrangler Secrets (frontend).

### Where Configuration Lives

| Location | Purpose | Secret? |
|----------|---------|---------|
| `.env.example` | Template for all variables (committed, placeholder values) | No |
| `backend/app/config.py` | Pydantic Settings validation (committed) | No |
| `deploy/cloudrun-env.yaml` | Production non-secret runtime config | No |
| `cloudbuild.yaml` → `--set-secrets` | GCP Secret Manager references | References only |
| `frontend/wrangler.jsonc` → `vars` | Frontend non-secret vars | No |
| GCP Secret Manager | Production secret storage | Yes |
| GitHub Actions Secrets | CI/CD secrets | Yes |

---

## Production Readiness Checklist

### 1. Core Platform (REQUIRED)

These must be configured before FIELDed can operate at all.

| Variable | Where to Set | How to Generate | Notes |
|----------|-------------|-----------------|-------|
| `APP_SECRET_KEY` | GCP Secret Manager | `openssl rand -hex 32` | Random ≥32 chars |
| `JWT_SECRET_KEY` | GCP Secret Manager | `openssl rand -hex 32` | Random ≥32 chars |
| `DATABASE_URL` | GCP Secret Manager | Neon dashboard → Connection string | `postgresql+asyncpg://...` |
| `APP_ENV` | `cloudrun-env.yaml` | — | Set to `production` |
| `APP_DEBUG` | `cloudrun-env.yaml` | — | Set to `false` |
| `BACKEND_CORS_ORIGINS` | `cloudrun-env.yaml` | — | `https://fielded.online,https://www.fielded.online` |
| `PUBLIC_BASE_URL` | `cloudrun-env.yaml` | — | `https://fielded-api-meftvuaodq-uc.a.run.app` |

### 2. AI Provider — Groq (REQUIRED for Brain, Discovery, Call Agent)

| Variable | Where to Set | How to Obtain | Notes |
|----------|-------------|---------------|-------|
| `AI_PROVIDER` | `cloudrun-env.yaml` | — | Set to `groq` |
| `AI_MODEL` | `cloudrun-env.yaml` | — | e.g. `openai/gpt-oss-120b` |
| `BRAIN_AI_API_KEY` | GCP Secret Manager | [console.groq.com](https://console.groq.com) → API Keys | Business Brain workload |
| `DISCOVERY_AI_API_KEY` | GCP Secret Manager | Same Groq key (or separate) | Discovery workload |
| `CALL_AGENT_AI_API_KEY` | GCP Secret Manager | Same Groq key (or separate) | Call Agent workload |

**Before operational**: Create Groq account → Generate API key → Store in Secret Manager.

### 3. Payment Provider — Stripe (REQUIRED for bookings with payment)

| Variable | Where to Set | How to Obtain | Notes |
|----------|-------------|---------------|-------|
| `PAYMENT_PROVIDER` | `cloudrun-env.yaml` | — | Set to `stripe` |
| `PAYMENT_API_KEY` | GCP Secret Manager | Stripe Dashboard → Developers → API keys | `sk_test_...` or `sk_live_...` |
| `PAYMENT_WEBHOOK_SECRET` | GCP Secret Manager | Stripe Dashboard → Webhooks → Signing secret | `whsec_...` |
| `STRIPE_CONNECT_CLIENT_ID` | `cloudrun-env.yaml` | Stripe Dashboard → Connect settings | For business onboarding |
| `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | `wrangler.jsonc` → `vars` | Stripe Dashboard → API keys | `pk_test_...` or `pk_live_...` (public, browser-safe) |

**Webhook configuration** (Stripe Dashboard → Webhooks → Add endpoint):
- URL: `https://fielded-api-meftvuaodq-uc.a.run.app/api/v1/webhooks/payments/stripe`
- Events: `payment_intent.succeeded`, `payment_intent.payment_failed`, `charge.refunded`

**Before operational**: Create Stripe account → Generate API keys → Register webhook endpoint → Copy signing secret.

### 4. Email Provider — Resend (REQUIRED for customer/business notifications)

| Variable | Where to Set | How to Obtain | Notes |
|----------|-------------|---------------|-------|
| `EMAIL_PROVIDER` | `cloudrun-env.yaml` | — | Set to `resend` |
| `EMAIL_API_KEY` | GCP Secret Manager | [resend.com](https://resend.com) → API Keys | `re_...` |
| `EMAIL_FROM` | `cloudrun-env.yaml` | — | Must use verified domain (e.g. `noreply@fielded.online`) |
| `RESEND_WEBHOOK_SECRET` | GCP Secret Manager | Resend Dashboard → Webhooks → Signing secret | For delivery verification |

**Domain verification** (Resend Dashboard → Domains → Add domain):
- Add DNS records: SPF, DKIM, DMARC
- Wait for DNS propagation (up to 48 hours)

**Webhook configuration** (Resend Dashboard → Webhooks → Add webhook):
- URL: `https://fielded-api-meftvuaodq-uc.a.run.app/api/v1/webhooks/communications/resend`
- Events: `email.sent`, `email.delivered`, `email.bounced`, `email.failed`

**Before operational**: Create Resend account → Verify sending domain (DNS) → Generate API key → Register webhook → Copy signing secret.

### 5. Communication Provider — Vonage (REQUIRED for SMS, WhatsApp, Voice)

| Variable | Where to Set | How to Obtain | Notes |
|----------|-------------|---------------|-------|
| `SMS_PROVIDER` | `cloudrun-env.yaml` | — | Set to `vonage` |
| `VOICE_PROVIDER` | `cloudrun-env.yaml` | — | Set to `vonage` |
| `WHATSAPP_PROVIDER` | `cloudrun-env.yaml` | — | Set to `vonage_whatsapp` |
| `VONAGE_APPLICATION_ID` | `cloudrun-env.yaml` | [vonage.com](https://vonage.com) → Applications | Application UUID |
| `VONAGE_APPLICATION_PRIVATE_KEY` | GCP Secret Manager | Download when creating Application | PEM-encoded RSA key |
| `VONAGE_NUMBER` | `cloudrun-env.yaml` | Vonage Dashboard → Numbers | SMS/Voice number (E.164) |
| `VONAGE_WHATSAPP_NUMBER` | `cloudrun-env.yaml` | Vonage Dashboard → Numbers | WhatsApp number (E.164) |
| `VONAGE_API_KEY` | GCP Secret Manager | Vonage Dashboard → Settings | Account-level API key |
| `VONAGE_API_SECRET` | GCP Secret Manager | Vonage Dashboard → Settings | Account-level API secret |
| `VONAGE_WEBHOOK_SECRET` | GCP Secret Manager | Vonage Dashboard → Settings → Signing secret | Webhook verification |

**Application setup** (Vonage Dashboard → Applications → Create):
- Enable capabilities: Messages (SMS, WhatsApp), Voice
- Set webhook URLs:
  - SMS status: `https://fielded-api-meftvuaodq-uc.a.run.app/api/v1/webhooks/communications/vonage_sms`
  - WhatsApp status: `https://fielded-api-meftvuaodq-uc.a.run.app/api/v1/webhooks/communications/vonage_whatsapp`
  - Voice events: `https://fielded-api-meftvuaodq-uc.a.run.app/api/v1/webhooks/voice/vonage`
- Download private key

**Number setup**: Purchase numbers for SMS/Voice and WhatsApp. Link WhatsApp number to the Application.

**Before operational**: Create Vonage account → Create Application (enable all capabilities) → Download private key → Purchase numbers → Configure webhook URLs → Copy signing secret.

### 6. Calendar Provider — Google Calendar (REQUIRED for booking automation)

| Variable | Where to Set | How to Obtain | Notes |
|----------|-------------|---------------|-------|
| `CALENDAR_PROVIDER` | `cloudrun-env.yaml` | — | Set to `google` |
| `GOOGLE_OAUTH_CLIENT_ID` | `cloudrun-env.yaml` | [Google Cloud Console](https://console.cloud.google.com) → APIs & Services → Credentials | OAuth 2.0 Client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | GCP Secret Manager | Same location | OAuth 2.0 Client Secret |
| `GOOGLE_OAUTH_REDIRECT_URI` | `cloudrun-env.yaml` | — | Must match exactly: `https://fielded-api-meftvuaodq-uc.a.run.app/api/v1/calendar/oauth/callback` |
| `GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY` | GCP Secret Manager | Generate (see below) | Fernet key for token encryption |

**Google Cloud Console setup**:
1. Create project (or use existing)
2. Enable **Google Calendar API**
3. Configure OAuth consent screen (External or Internal)
4. Create OAuth 2.0 Client ID (type: Web application)
5. Add authorized redirect URI: `https://fielded-api-meftvuaodq-uc.a.run.app/api/v1/calendar/oauth/callback`
6. Download client credentials

**Generate encryption key**:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**OAuth scope**: `https://www.googleapis.com/auth/calendar.events` (minimum — read/write events only)

**Per-business flow**: Each business connects their Google Calendar through the FIELDed UI. FIELDed stores encrypted OAuth tokens and syncs bookings automatically.

**Before operational**: Create Google Cloud project → Enable Calendar API → Configure OAuth consent → Create OAuth credentials → Register redirect URI → Generate encryption key.

### 7. Frontend — Cloudflare Workers (REQUIRED for UI)

| Variable | Where to Set | How to Obtain | Notes |
|----------|-------------|---------------|-------|
| `NEXT_PUBLIC_API_URL` | `wrangler.jsonc` → `vars` | — | Backend API URL |
| `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | `wrangler.jsonc` → `vars` | Stripe Dashboard | Public key (browser-safe) |
| `CLOUDFLARE_API_TOKEN` | GitHub Actions Secrets | [Cloudflare Dashboard](https://dash.cloudflare.com) → My Profile → API Tokens | Workers edit permission |
| `CLOUDFLARE_ACCOUNT_ID` | GitHub Actions Secrets | Cloudflare Dashboard → Overview | Account identifier |

**Deploy**:
```bash
cd frontend
npm run deploy
```

**Custom domain** (after first deploy):
```bash
npx wrangler custom-domain add fielded.online fielded-frontend
npx wrangler custom-domain add www.fielded.online fielded-frontend
```

**Security rule**: Only `NEXT_PUBLIC_*` variables are exposed to the browser. No API keys or secrets.

**Before operational**: Create Cloudflare account → Generate API token → Set GitHub secrets → Deploy → Attach custom domain.

---

## GCP Secret Manager — Full Secret List

Create these secrets in GCP Secret Manager before deploying:

```bash
# Core
gcloud secrets create APP_SECRET_KEY --replication-policy=automatic
gcloud secrets create JWT_SECRET_KEY --replication-policy=automatic
gcloud secrets create DATABASE_URL --replication-policy=automatic

# AI
gcloud secrets create BRAIN_AI_API_KEY --replication-policy=automatic
gcloud secrets create DISCOVERY_AI_API_KEY --replication-policy=automatic
gcloud secrets create CALL_AGENT_AI_API_KEY --replication-policy=automatic

# Payments
gcloud secrets create PAYMENT_API_KEY --replication-policy=automatic
gcloud secrets create PAYMENT_WEBHOOK_SECRET --replication-policy=automatic

# Email (Resend)
gcloud secrets create EMAIL_API_KEY --replication-policy=automatic
gcloud secrets create RESEND_WEBHOOK_SECRET --replication-policy=automatic

# Vonage
gcloud secrets create VONAGE_API_KEY --replication-policy=automatic
gcloud secrets create VONAGE_API_SECRET --replication-policy=automatic
gcloud secrets create VONAGE_APPLICATION_PRIVATE_KEY --replication-policy=automatic
gcloud secrets create VONAGE_WEBHOOK_SECRET --replication-policy=automatic

# Calendar (Google)
gcloud secrets create GOOGLE_OAUTH_CLIENT_SECRET --replication-policy=automatic
gcloud secrets create GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY --replication-policy=automatic
```

Set secret values:
```bash
echo -n "your-secret-value" | gcloud secrets add-version SECRET_NAME --data-file=-
```

---

## Webhook URL Summary

All webhook endpoints use the `PUBLIC_BASE_URL` prefix:

| Provider | URL | Purpose |
|----------|-----|---------|
| Stripe | `{PUBLIC_BASE_URL}/api/v1/webhooks/payments/stripe` | Payment events |
| Resend | `{PUBLIC_BASE_URL}/api/v1/webhooks/communications/resend` | Email delivery |
| Vonage SMS | `{PUBLIC_BASE_URL}/api/v1/webhooks/communications/vonage_sms` | SMS status |
| Vonage WhatsApp | `{PUBLIC_BASE_URL}/api/v1/webhooks/communications/vonage_whatsapp` | WhatsApp status |
| Vonage Voice | `{PUBLIC_BASE_URL}/api/v1/webhooks/voice/vonage` | Call events |
| Google Calendar | `{PUBLIC_BASE_URL}/api/v1/calendar/oauth/callback` | OAuth callback |

---

## Configuration Order (First Deploy)

Execute in this order:

1. **Core platform**: `APP_SECRET_KEY`, `JWT_SECRET_KEY`, `DATABASE_URL`
2. **AI provider**: Groq API keys
3. **Payment provider**: Stripe keys + webhook
4. **Email provider**: Resend API key + domain verification + webhook
5. **Communication provider**: Vonage Application + numbers + webhooks
6. **Calendar provider**: Google OAuth credentials + redirect URI
7. **Frontend**: Cloudflare deployment + custom domain
8. **Backend**: Cloud Run deploy with all secrets

---

## Verification

After configuration, verify each integration:

```bash
# Health check
curl https://fielded-api-meftvuaodq-uc.a.run.app/api/v1/health

# Provider status (check logs for provider initialization)
# Each adapter logs a warning if selected but credentials are empty
```

Check backend logs for:
- `vonage.*provider.*credentials.*empty` — Vonage not configured
- `resend.*credentials.*empty` — Resend not configured
- `google.*calendar.*credentials.*empty` — Google Calendar not configured
- `stripe.*credentials.*empty` — Stripe not configured

---

## Related Documentation

- [INTEGRATIONS.md](INTEGRATIONS.md) — Adapter implementations and provider details
- [deployment.md](../deployment.md) — Deployment procedures
- [security.md](../security.md) — Security architecture
- [AI-ARCHITECTURE.md](AI-ARCHITECTURE.md) — AI provider configuration
