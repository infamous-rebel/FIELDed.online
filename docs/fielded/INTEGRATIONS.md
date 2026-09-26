# FIELDed — External Integrations

**Status**: Production Configuration Baseline  
**Last Updated**: 2026-09-26

---

## Integration Inventory

| Provider | Purpose | Adapter | Status | Webhook Support |
|----------|---------|---------|--------|-----------------|
| Groq | AI/LLM services | `GroqProvider` | Adapter implemented | N/A |
| OpenAI | AI/LLM services | `OpenAIProvider` | Adapter implemented | N/A |
| Stripe | Payment processing | `StripePaymentProvider` | Adapter implemented | Yes |
| Resend | Email delivery | `ResendEmailProvider` | Adapter implemented | Yes |
| Vonage | SMS delivery | `VonageSmsProvider` | Adapter implemented | Yes |
| Vonage | WhatsApp messaging | `VonageWhatsappProvider` | Adapter implemented | Yes |
| Vonage | Voice calls | `VonageVoiceProvider` | Adapter implemented | Yes |
| Google | Calendar sync | `GoogleCalendarProvider` | Adapter implemented | N/A |
| Twilio | SMS delivery (legacy) | `TwilioSmsProvider` | Adapter implemented | Yes |
| Twilio | Voice calls (legacy) | `TwilioVoiceProvider` | Adapter implemented | Yes |

---

## Production Topology

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

FIELDed is the system of record. Stripe, Google Calendar, Resend, and Vonage are external adapters — none of them override FIELDed's authoritative booking/payment state.

---

## AI Providers

### Groq

**Purpose**: AI/LLM services for discovery, brain conversations, call agent

**Adapter**: `app/adapters/ai/groq.py`

| Variable | Required | Secret | Description |
|----------|----------|--------|-------------|
| `AI_PROVIDER` | Yes | No | Set to `groq` |
| `AI_API_KEY` | Yes | Yes | Groq API key |
| `AI_BASE_URL` | No | No | Override API base URL |
| `AI_MODEL` | Yes | No | Model name (e.g. `openai/gpt-oss-120b`) |

**Workload-specific overrides** (optional — fall back to global `AI_*`):

| Variable | Workload |
|----------|----------|
| `DISCOVERY_AI_API_KEY` / `DISCOVERY_AI_BASE_URL` | Discovery |
| `BRAIN_AI_API_KEY` / `BRAIN_AI_BASE_URL` | Business Brain |
| `CALL_AGENT_AI_API_KEY` / `CALL_AGENT_AI_BASE_URL` | Call Agent |

**Setup**: Create account at [console.groq.com](https://console.groq.com), generate API key.

---

## Payment Providers

### Stripe

**Purpose**: Payment processing, Connect for business onboarding

**Adapter**: `app/adapters/payment/stripe_provider.py`

| Variable | Required | Secret | Description |
|----------|----------|--------|-------------|
| `PAYMENT_PROVIDER` | Yes | No | Set to `stripe` |
| `PAYMENT_API_KEY` | Yes | Yes | Stripe secret key (`sk_test_...` or `sk_live_...`) |
| `PAYMENT_WEBHOOK_SECRET` | Yes | Yes | Webhook signing secret (`whsec_...`) |
| `STRIPE_CONNECT_CLIENT_ID` | If using Connect | No | OAuth client ID for Connect onboarding |
| `STRIPE_CONNECT_WEBHOOK_SECRET` | If using Connect | Yes | Connect event webhook secret |
| `PLATFORM_FEE_PERCENT` | No | No | Platform fee percentage (default: `5.00`) |

**Frontend (public, browser-safe)**:

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | Yes | Stripe publishable key (`pk_test_...` or `pk_live_...`) |

**Webhook endpoints** (configure in Stripe Dashboard → Webhooks):
- URL: `{PUBLIC_BASE_URL}/api/v1/webhooks/payments/stripe`
- Events: `payment_intent.succeeded`, `payment_intent.payment_failed`, `charge.refunded`

**Setup**:
1. Create Stripe account at [stripe.com](https://stripe.com)
2. Generate API keys in Dashboard → Developers → API keys
3. Add webhook endpoint pointing to your `PUBLIC_BASE_URL`
4. Copy webhook signing secret

---

## Communication Providers

### Resend (Email)

**Purpose**: Transactional email delivery with delivery tracking

**Adapter**: `app/adapters/email/resend.py`

| Variable | Required | Secret | Description |
|----------|----------|--------|-------------|
| `EMAIL_PROVIDER` | Yes | No | Set to `resend` |
| `EMAIL_API_KEY` | Yes | Yes | Resend API key (`re_...`) |
| `EMAIL_FROM` | Yes | No | Verified sending domain address (e.g. `noreply@fielded.online`) |
| `EMAIL_REPLY_TO` | No | No | Reply-to address |
| `RESEND_WEBHOOK_SECRET` | Recommended | Yes | Webhook signing secret for delivery verification |

**Webhook endpoints** (configure in Resend Dashboard → Webhooks):
- URL: `{PUBLIC_BASE_URL}/api/v1/webhooks/communications/resend`
- Events: `email.sent`, `email.delivered`, `email.bounced`, `email.failed`
- Signing secret: Set `RESEND_WEBHOOK_SECRET` to verify webhook authenticity

**Setup**:
1. Create account at [resend.com](https://resend.com)
2. Add and verify your sending domain (DNS records required)
3. Generate API key in Dashboard → API Keys
4. Add webhook endpoint for delivery tracking
5. Copy webhook signing secret

**Verified domain required**: Before Resend can send email, you must add a verified sending domain and configure DNS (SPF, DKIM, DMARC records).

---

### Vonage (SMS)

**Purpose**: SMS delivery via Messages API

**Adapter**: `app/adapters/sms/vonage.py`

| Variable | Required | Secret | Description |
|----------|----------|--------|-------------|
| `SMS_PROVIDER` | Yes | No | Set to `vonage` |
| `VONAGE_APPLICATION_ID` | Yes | No | Vonage Application UUID (Dashboard → Applications) |
| `VONAGE_APPLICATION_PRIVATE_KEY` | Yes | Yes | PEM-encoded RSA private key |
| `VONAGE_NUMBER` | Yes | No | Sender phone number (E.164 format) |
| `VONAGE_WEBHOOK_SECRET` | Recommended | Yes | Inbound webhook signing secret |

**Authentication**: Vonage Messages API uses JWT authentication (Application-based). The private key signs a JWT that authorizes each API call.

**Webhook endpoints** (configure in Vonage Dashboard → Applications → Settings):
- URL: `{PUBLIC_BASE_URL}/api/v1/webhooks/communications/vonage_sms`
- Events: `delivered`, `failed`, `read`, `rejected`

---

### Vonage (WhatsApp)

**Purpose**: WhatsApp messaging via Messages API

**Adapter**: `app/adapters/whatsapp/vonage.py`

| Variable | Required | Secret | Description |
|----------|----------|--------|-------------|
| `WHATSAPP_PROVIDER` | Yes | No | Set to `vonage_whatsapp` |
| `VONAGE_APPLICATION_ID` | Yes | No | Same Vonage Application (shared with SMS) |
| `VONAGE_APPLICATION_PRIVATE_KEY` | Yes | Yes | Same private key (shared with SMS) |
| `VONAGE_WHATSAPP_NUMBER` | Yes | No | WhatsApp-enabled number (E.164 format) |

**Webhook endpoints**:
- URL: `{PUBLIC_BASE_URL}/api/v1/webhooks/communications/vonage_whatsapp`

---

### Vonage (Voice)

**Purpose**: Outbound voice calls via Voice API

**Adapter**: `app/adapters/voice/vonage.py`

| Variable | Required | Secret | Description |
|----------|----------|--------|-------------|
| `VOICE_PROVIDER` | Yes | No | Set to `vonage` |
| `VONAGE_APPLICATION_ID` | Yes | No | Same Vonage Application |
| `VONAGE_APPLICATION_PRIVATE_KEY` | Yes | Yes | Same private key |
| `VONAGE_NUMBER` | Yes | No | Caller ID number |

**Webhook endpoints** (configure in Vonage Application → Capabilities → Voice):
- Event URL: `{PUBLIC_BASE_URL}/api/v1/webhooks/voice/vonage`
- Call events: `ringing`, `answered`, `completed`, `busy`, `failed`

**NCCO**: Call behavior is controlled by an NCCO served at the callback URL.

---

### Vonage — Shared Configuration

All Vonage channels share the same Application and credentials:

| Variable | Channels | Description |
|----------|----------|-------------|
| `VONAGE_APPLICATION_ID` | SMS, WhatsApp, Voice | Application UUID |
| `VONAGE_APPLICATION_PRIVATE_KEY` | SMS, WhatsApp, Voice | RSA private key (PEM) |
| `VONAGE_API_KEY` | Account-level | API key (for legacy REST APIs) |
| `VONAGE_API_SECRET` | Account-level | API secret (for legacy REST APIs) |
| `VONAGE_NUMBER` | SMS, Voice | Default phone number |
| `VONAGE_WHATSAPP_NUMBER` | WhatsApp | WhatsApp-specific number |
| `VONAGE_WEBHOOK_SECRET` | All | Inbound webhook signing secret |

**Setup**:
1. Create account at [vonage.com](https://vonage.com)
2. Create an Application in Dashboard → Applications
3. Enable capabilities: Messages (SMS, WhatsApp), Voice
4. Download the private key
5. Configure webhook URLs for each capability
6. Purchase phone numbers for SMS/Voice/WhatsApp

---

## Calendar Providers

### Google Calendar

**Purpose**: Booking synchronization — syncs FIELDed bookings to business Google Calendars

**Adapter**: `app/adapters/calendar/google_calendar.py`

**Platform-level OAuth credentials** (for the "Connect Google Calendar" flow):

| Variable | Required | Secret | Description |
|----------|----------|--------|-------------|
| `CALENDAR_PROVIDER` | Yes | No | Set to `google` |
| `GOOGLE_OAUTH_CLIENT_ID` | Yes | No | OAuth 2.0 Client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Yes | Yes | OAuth 2.0 Client Secret |
| `GOOGLE_OAUTH_REDIRECT_URI` | Yes | No | Must match exactly: `{PUBLIC_BASE_URL}/api/v1/calendar/oauth/callback` |
| `GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY` | Recommended | Yes | Fernet key for OAuth token encryption at rest |

**Token encryption**: Per-business OAuth tokens are encrypted at rest using Fernet symmetric encryption. The encryption key is derived from `APP_SECRET_KEY` by default. For production, set `GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY` to a dedicated Fernet key.

Generate a Fernet key:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**OAuth scope**: `https://www.googleapis.com/auth/calendar.events` (minimum required — read/write events only, NOT calendar management)

**OAuth callback endpoint**:
- URL: `{PUBLIC_BASE_URL}/api/v1/calendar/oauth/callback`
- This must be registered in Google Cloud Console → OAuth 2.0 Client → Authorized redirect URIs

**Setup**:
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project (or use existing)
3. Enable Google Calendar API
4. Configure OAuth consent screen
5. Create OAuth 2.0 Client ID (Web application type)
6. Add authorized redirect URI: `{PUBLIC_BASE_URL}/api/v1/calendar/oauth/callback`
7. Download client credentials
8. Set `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI`

**Per-business flow**: Each business connects their own Google Calendar through the "Connect Google Calendar" UI. FIELDed stores the encrypted OAuth token and syncs bookings to their calendar.

---

## Provider Factory

Providers are resolved through `ProviderFactory`:

```python
factory = ProviderFactory.from_settings(settings)
email_provider = factory.email_provider
sms_provider = factory.sms_provider
voice_provider = factory.voice_provider
whatsapp_provider = factory.whatsapp_provider
payment_provider = factory.payment_provider
calendar_provider = factory.calendar_provider
```

---

## Integration Testing

### Mock Providers

For local development and testing, use mock/stub providers:

```bash
AI_PROVIDER=mock
PAYMENT_PROVIDER=mock
EMAIL_PROVIDER=mock
SMS_PROVIDER=mock
VOICE_PROVIDER=mock
WHATSAPP_PROVIDER=mock
CALENDAR_PROVIDER=mock
```

### Real Provider Testing

To test with real providers:

1. Set up provider accounts (see per-provider setup above)
2. Configure environment variables with real credentials
3. Set `PUBLIC_BASE_URL` to your ngrok/tunnel URL (development) or production domain
4. Register webhook URLs with each provider
5. Run integration tests
6. Verify E2E behavior

**Warning**: Real provider testing may incur costs.

---

## Security Considerations

### Credential Storage

- **Never** commit credentials to code
- Use environment variables exclusively
- Production: GCP Secret Manager (Cloud Run) or Wrangler Secrets (Cloudflare)
- Rotate credentials regularly
- OAuth tokens are encrypted at rest (Fernet)

### Webhook Security

- All webhook endpoints verify provider signatures
- Resend: `RESEND_WEBHOOK_SECRET` for HMAC verification
- Vonage: `VONAGE_WEBHOOK_SECRET` for message status verification
- Stripe: `PAYMENT_WEBHOOK_SECRET` for event verification
- Voice: `webhook_signature_secret` per voice campaign configuration

### Secret Boundary

| Location | Secrets Allowed | Examples |
|----------|----------------|---------|
| Backend (Cloud Run) | Yes | All API keys, webhook secrets, DB credentials |
| Frontend (Cloudflare) | **No** (except `NEXT_PUBLIC_*`) | Only `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` |
| wrangler.jsonc | **No** | Only non-secret `NEXT_PUBLIC_*` vars |
| .env.example | Placeholder only | Documented but empty |

---

## Summary

FIELDed has adapter implementations for all major external providers. Each integration requires specific credentials and configuration before it becomes operational. See [PRODUCTION-CONFIGURATION.md](PRODUCTION-CONFIGURATION.md) for the complete production readiness checklist.
