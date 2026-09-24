# FIELDed — External Integrations

**Status**: Current State Baseline  
**Last Updated**: 2026-09-24

---

## Integration Inventory

| Provider | Purpose | Adapter | Credentials Configured? | Real E2E Verified? | Current State |
|----------|---------|---------|------------------------|-------------------|---------------|
| Groq | AI/LLM services | `GroqProvider` | Yes (env vars) | No | C. PARTIAL |
| OpenAI | AI/LLM services | `OpenAIProvider` | Yes (env vars) | No | C. PARTIAL |
| Stripe | Payment processing | `StripePaymentProvider` | Yes (env vars) | No | C. PARTIAL |
| Resend | Email delivery | `ResendEmailProvider` | Yes (env vars) | No | C. PARTIAL |
| Twilio | SMS delivery | `TwilioSmsProvider` | Yes (env vars) | No | C. PARTIAL |
| Twilio | Voice calls | `TwilioVoiceProvider` | Yes (env vars) | No | C. PARTIAL |
| WhatsApp | WhatsApp messaging | `StubWhatsAppProvider` | N/A | N/A | E. STUB |
| Push | Push notifications | `StubPushProvider` | N/A | N/A | E. STUB |

---

## AI Providers

### Groq

**Purpose**: AI/LLM services for discovery, brain conversations, call agent

**Adapter**: `app/adapters/ai/groq.py`

**Credentials**:
- `AI_API_KEY` or `GROQ_API_KEY`: Groq API key
- `AI_BASE_URL` or `GROQ_BASE_URL`: Groq API base URL (optional)
- `AI_MODEL` or `GROQ_MODEL`: Model name (default: `llama-3.3-70b-versatile`)

**Workload-Specific Keys**:
- `DISCOVERY_AI_API_KEY`: Discovery workload
- `BRAIN_AI_API_KEY`: Brain workload
- `CALL_AGENT_AI_API_KEY`: Call Agent workload

**Status**: Adapter implemented, not fully tested E2E with real Groq credentials

**Documentation**: See [AI-ARCHITECTURE.md](AI-ARCHITECTURE.md)

### OpenAI

**Purpose**: AI/LLM services (alternative to Groq)

**Adapter**: `app/adapters/ai/openai_provider.py`

**Credentials**:
- `AI_API_KEY` or `OPENAI_API_KEY`: OpenAI API key
- `AI_BASE_URL`: OpenAI API base URL (optional)
- `AI_MODEL`: Model name (default: `gpt-4o-mini`)

**Status**: Adapter implemented, not fully tested E2E with real OpenAI credentials

---

## Payment Providers

### Stripe

**Purpose**: Payment processing

**Adapter**: `app/adapters/payment/stripe_provider.py`

**Credentials**:
- `PAYMENT_API_KEY` or `STRIPE_API_KEY`: Stripe API key
- `PAYMENT_WEBHOOK_SECRET` or `STRIPE_WEBHOOK_SECRET`: Stripe webhook secret

**Features**:
- Payment creation
- Payment confirmation
- Refund processing
- Webhook handling

**Status**: Adapter implemented, not fully tested E2E with real Stripe credentials

**Webhooks**:
- `payment_intent.succeeded`
- `payment_intent.payment_failed`
- `charge.refunded`

---

## Communication Providers

### Resend (Email)

**Purpose**: Email delivery

**Adapter**: `app/adapters/email/resend.py`

**Credentials**:
- `EMAIL_API_KEY` or `RESEND_API_KEY`: Resend API key
- `EMAIL_FROM`: From email address (default: `noreply@fielded.local`)

**Features**:
- Transactional email
- Template-based email
- Delivery tracking

**Status**: Adapter implemented, not fully tested E2E with real Resend credentials

### Twilio (SMS)

**Purpose**: SMS delivery

**Adapter**: `app/adapters/sms/twilio.py`

**Credentials**:
- `TWILIO_ACCOUNT_SID`: Twilio Account SID
- `TWILIO_AUTH_TOKEN`: Twilio Auth Token
- `TWILIO_PHONE_NUMBER`: Twilio phone number

**Features**:
- SMS sending
- Delivery tracking
- Webhook handling

**Status**: Adapter implemented, not fully tested E2E with real Twilio credentials

### Twilio (Voice)

**Purpose**: Voice calls

**Adapter**: `app/adapters/voice/twilio.py`

**Credentials**:
- `TWILIO_ACCOUNT_SID`: Twilio Account SID
- `TWILIO_AUTH_TOKEN`: Twilio Auth Token
- `TWILIO_PHONE_NUMBER`: Twilio phone number

**Features**:
- Voice call initiation
- Call session management
- TwiML integration
- Webhook handling

**Status**: Adapter implemented, not fully tested E2E with real Twilio credentials

### WhatsApp (Stub)

**Purpose**: WhatsApp messaging

**Adapter**: `app/adapters/whatsapp/stub.py`

**Credentials**: N/A (stub provider)

**Status**: Stub provider only, no real WhatsApp integration

### Push Notifications (Stub)

**Purpose**: Push notifications

**Adapter**: `app/adapters/push/stub.py`

**Credentials**: N/A (stub provider)

**Status**: Stub provider only, no real push notification integration

---

## Integration Configuration

### Provider Selection

Providers are selected via environment variables:

```bash
AI_PROVIDER=groq  # or openai, mock
PAYMENT_PROVIDER=stripe  # or mock
EMAIL_PROVIDER=resend  # or mock
SMS_PROVIDER=twilio  # or mock
VOICE_PROVIDER=twilio  # or mock
WHATSAPP_PROVIDER=mock  # stub only
PUSH_PROVIDER=mock  # stub only
```

### Provider Factory

Providers are resolved through `ProviderFactory`:

```python
factory = ProviderFactory.from_settings(settings)
email_provider = factory.email_provider
sms_provider = factory.sms_provider
voice_provider = factory.voice_provider
payment_provider = factory.payment_provider
```

---

## Integration Testing

### Mock Providers

For testing, use mock/stub providers:

```bash
AI_PROVIDER=mock
PAYMENT_PROVIDER=mock
EMAIL_PROVIDER=mock
SMS_PROVIDER=mock
VOICE_PROVIDER=mock
```

### Real Provider Testing

To test with real providers:

1. Set up provider accounts
2. Configure environment variables with real credentials
3. Run integration tests
4. Verify E2E behavior

**Warning**: Real provider testing may incur costs

---

## Integration Gaps

### Critical Gaps

1. **Stripe**: Not fully tested E2E with real credentials
2. **Resend**: Not fully tested E2E with real credentials
3. **Twilio SMS**: Not fully tested E2E with real credentials
4. **Twilio Voice**: Not fully tested E2E with real credentials

### Future Integrations

1. **WhatsApp Business API**: Real WhatsApp integration
2. **Push Notification Services**: Firebase Cloud Messaging, Apple Push Notification Service
3. **Calendar Integration**: Google Calendar, Outlook Calendar
4. **Accounting Integration**: QuickBooks, Xero
5. **CRM Integration**: Salesforce, HubSpot

---

## Security Considerations

### Credential Storage

- **Never** commit credentials to code
- Use environment variables
- Use secret management services (Vercel Secrets, GCP Secret Manager, etc.)
- Rotate credentials regularly

### Webhook Security

- Verify webhook signatures
- Use webhook secrets
- Validate webhook payloads
- Implement idempotency

### Rate Limiting

- Respect provider rate limits
- Implement retry logic
- Use exponential backoff

---

## Summary

FIELDed currently has **adapter implementations** for major external providers (Groq, OpenAI, Stripe, Resend, Twilio), but **real E2E verification** with actual credentials is still needed. The architecture supports easy switching between providers and workload-specific configuration.

WhatsApp and Push notification integrations are **stub-only** and require real implementations for production use.
