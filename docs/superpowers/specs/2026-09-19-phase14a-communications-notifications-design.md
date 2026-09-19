# Phase 14A — Core Communications, Notifications & Provider Adapters

## Status: Approved

## Overview

Phase 14A establishes the complete production communication infrastructure for FIELDed. It is the first sub-phase of Phase 14 (14A → 14B → 14C) and provides the foundational backend that 14B (Voice/Call Agent, Campaigns) and 14C (Frontend UI) depend on.

**Phase boundary:**
- **14A**: Core communications + notifications + DB event outbox + real Email/SMS/Voice provider infrastructure + communication policy/consent infrastructure
- **14B**: Voice/Call Agent + transactional/marketing calling + campaigns + human escalation + voice webhooks
- **14C**: Business/Customer communication UI + Call Agent UI + campaign UI + communication history + complete operational integration

## Architectural Decisions

### 1. Communication Configuration: Hybrid Storage

**Decision**: Use a hybrid architecture splitting operational state and governed policy.

**Dedicated operational tables** (frequently changing):
- `business_communication_channels` — channel enablement, provider references
- `business_communication_purposes` — purpose enablement, permitted channels
- `customer_communication_preferences` — consent, opt-in/out, suppression, DNC

**BrainVersion.communication_config JSONB** (governed policy):
- Frequency rules (max attempts, daily/weekly limits, retry intervals)
- Timing rules (communication hours, timezone, quiet periods, deferral)
- Escalation rules (conditions, max unsuccessful attempts, approval requirements)
- Agent behaviour (instructions, scripts, tone, information boundaries)
- Governed channel/purpose rules (restrictions, service-specific rules, conditions)

**Responsibility boundary**:
| Requirement | Storage |
|---|---|
| Email enabled | Dedicated table |
| Customer opted out | Dedicated table |
| Provider reference | Dedicated table |
| Max calls/day | BrainVersion |
| Calling hours | BrainVersion |
| Retry policy | BrainVersion |
| Escalation conditions | BrainVersion |
| Agent instructions | BrainVersion |

**Policy evaluation combines both sources** — a communication is permitted only when all operational AND governed requirements are satisfied.

### 2. Orchestration: DB Event Outbox

**Decision**: Use a PostgreSQL `outbox_events` table with a background worker. No Redis, Kafka, or external messaging infrastructure.

**Flow**:
```
Domain Transaction (PostgreSQL)
    ├── Domain change (e.g. booking → CONFIRMED)
    └── INSERT outbox_events (BOOKING_CONFIRMED)
    → COMMIT atomically

Background Outbox Worker
    → Notification/Communication Orchestrator
    → Communication Policy
    → Consent / Suppression / Frequency / Timing
    → Business Brain
    → Provider Adapter
    → Email / SMS / WhatsApp / Push / In-App
```

**Worker architecture**: Hybrid — core worker is a plain `async def process_outbox_events(session)` function. Phase 14A runs it as a FastAPI in-process background task. A standalone CLI entry point (`python -m app.workers.outbox`) invokes the same function for future independent deployment.

**Concurrency safety**:
1. Claim transaction: `SELECT ... FOR UPDATE SKIP LOCKED` → UPDATE to PROCESSING → COMMIT
2. Process event (external provider calls) — no locks held
3. Status transaction: UPDATE to PROCESSED / RETRYABLE / FAILED → COMMIT

**Lease/recovery**: PROCESSING events include `processing_started_at`. Events stuck past a configurable lease expiry can be reclaimed by another worker.

**Outbox lifecycle**:
```
PENDING → PROCESSING → PROCESSED
                     → RETRYABLE → PROCESSING (retry)
                                 → FAILED (max attempts)
```

### 3. Provider Adapters

**Decision**: Implement all 5 adapter interfaces. Real integrations for Email (Resend) and SMS (Twilio). Real provider boundary for Voice (Twilio Voice, no Call Agent). Stubs for WhatsApp and Push.

**Directory structure**:
```
backend/app/adapters/
├── email/
│   ├── base.py          # EmailProvider ABC (extended)
│   └── resend.py        # ResendEmailProvider
├── sms/
│   ├── base.py          # SmsProvider ABC (extended)
│   └── twilio.py        # TwilioSmsProvider
├── whatsapp/
│   ├── base.py          # WhatsAppProvider ABC
│   └── stub.py          # StubWhatsAppProvider
├── push/
│   ├── base.py          # PushProvider ABC
│   └── stub.py          # StubPushProvider
├── voice/
│   ├── base.py          # VoiceProvider ABC
│   └── twilio.py        # TwilioVoiceProvider (boundary, no agent)
```

**Interface pattern** (consistent with existing):
- ABC with `@abstractmethod async def send(...)`
- Dataclass for request and result
- `provider_name` property
- Result includes `success: bool`, `error: str | None`, `retryable: bool`, `provider_message_id: str`
- Provider SDK exceptions are caught and translated to the common result contract

**ProviderFactory** in `app/adapters/__init__.py` creates configured providers from settings. Domain services receive providers through dependency injection — never importing provider SDKs directly.

### 4. Communication Policy Engine

**Decision**: Deterministic policy evaluation combining operational config + governed policy + consent state.

**Location**: `backend/app/domain/communication/policy.py`

**Evaluation pipeline** (ordered):
1. Channel enabled? → `business_communication_channels`
2. Purpose enabled? → `business_communication_purposes`
3. Customer consent? → `customer_communication_preferences`
4. Suppression / DNC? → `customer_communication_preferences`
5. Timing / calling hours? → `BrainVersion.communication_config`
6. Frequency limits? → `BrainVersion.communication_config` + recent communications count
7. Business Brain policy rules? → `communication_config` governed rules
8. Approval required? → `BrainVersion.communication_config`
9. → ALLOW / DENY / REQUIRE_APPROVAL / DEFER / ESCALATE

**PolicyDecision** (dataclass):
- `decision: str` — ALLOW | DENY | REQUIRE_APPROVAL | DEFER | ESCALATE
- `reason: str`
- `brain_version_id: UUID | None`
- `matched_rules: list[dict]`
- `consent_state: dict | None`
- `suppression_state: dict | None`
- `frequency_state: dict | None`
- `timing_state: dict | None`

**Properties**: `evaluate()` reads PostgreSQL state but the decision logic is deterministic and side-effect-free. No LLM involvement. Every decision is traceable and auditable.

### 5. Notification & Orchestration

**Decision**: Separate NotificationService (persisted notification state) from OrchestrationService (translates outbox events into governed communications).

**OrchestrationService flow**:
```
Outbox Event
    ↓
1. Create Notification(s) based on event_type
    ↓
2. For each eligible notification:
   a. Determine target channel(s) from business config
   b. Resolve template (channel + purpose + business)
   c. Render template with event variables
   d. Evaluate CommunicationPolicyService.evaluate(...)
   e. If ALLOW → create Communication + CommunicationRecipient
   f. Create CommunicationAttempt, call provider adapter
   g. Persist attempt result, update communication status
   h. Record audit event
    ↓
3. If DENY/DEFER/REQUIRE_APPROVAL/ESCALATE → record decision in audit
```

**Idempotency**:
- Outbox `idempotency_key` prevents duplicate event processing
- Communication `idempotency_key` = `f"{event_type}:{aggregate_type}:{aggregate_id}:{channel}:{purpose}"`
- Provider message IDs alone cannot prevent duplicate sends (they exist only after success) — use persisted communication/attempt state + provider-supported idempotency for retries

**Template rendering**: Simple variable substitution (`{{ customer_name }}`, `{{ booking_reference }}`). Variables extracted from outbox payload + entity lookups. No AI involvement.

## Domain Models & Database Schema

### Migration: `010_phase14a_communications_notifications`

### Communication Core

**`communications`** — Core communication record:
- `id` (UUID PK), `business_id` (FK), `customer_id` (FK, nullable — some comms target staff), `channel`, `purpose`, `status`
- `idempotency_key` (unique constraint)
- `brain_version_id` (FK, nullable)
- `decision_evidence` (JSONB)
- Related entity refs: `enquiry_id`, `quote_id`, `booking_id`, `service_execution_id`, `invoice_id` (all nullable FKs)
- `provider_reference` (nullable)
- `metadata` (JSONB, nullable)
- Timestamps: `created_at`, `updated_at`
- Soft-delete: yes

**`communication_recipients`** — Per-communication recipients:
- `id` (UUID PK), `communication_id` (FK), `user_id` (FK, nullable — external recipients supported)
- `channel`, `address` (email/phone/device token), `status`
- Timestamps, soft-delete: yes

**`communication_attempts`** — Provider delivery attempts:
- `id` (UUID PK), `communication_id` (FK), `provider_name`, `provider_reference`
- `status`, `error`, `retry_count`, `provider_response` (JSONB)
- Timestamps, soft-delete: **no** (append-oriented, immutable)

### Templates

**`communication_templates`** — Stable template identity:
- `id` (UUID PK), `business_id` (FK), `channel`, `purpose`, `name`
- `active_version_id` (FK to communication_template_versions)
- `status`, `approval_state`
- Timestamps, soft-delete: yes

**`communication_template_versions`** — Immutable historical content:
- `id` (UUID PK), `template_id` (FK), `version_number`
- `subject`, `body`, `variables` (JSONB)
- `approval_provenance` (JSONB)
- `created_at`, `created_by` (FK, nullable)
- Soft-delete: no (immutable)
- Unique: `(template_id, version_number)`

### Operational Config

**`business_communication_channels`**:
- `id` (UUID PK), `business_id` (FK), `channel` (String 50)
- `enabled` (bool), `provider_ref` (String, nullable), `settings` (JSONB, nullable)
- Timestamps, soft-delete: yes
- Unique: `(business_id, channel)`

**`business_communication_purposes`**:
- `id` (UUID PK), `business_id` (FK), `purpose` (String 50)
- `enabled` (bool), `permitted_channels` (JSONB, nullable)
- Timestamps, soft-delete: yes
- Unique: `(business_id, purpose)`

**`customer_communication_preferences`**:
- `id` (UUID PK), `customer_id` (FK), `business_id` (FK)
- `channel` (nullable = all channels), `purpose` (nullable = all purposes)
- `consent_state`, `opt_in` (bool), `suppression` (bool), `suppression_reason` (nullable)
- `do_not_contact` (bool), `source` (nullable), `consented_at` (nullable)
- Timestamps, soft-delete: yes
- Partial unique index: `UNIQUE INDEX (customer_id, business_id, COALESCE(channel, '__ALL__'), COALESCE(purpose, '__ALL__')) WHERE deleted_at IS NULL` — handles NULL wildcard semantics correctly

### Notifications

**`notifications`**:
- `id` (UUID PK), `business_id` (FK), `customer_id` (FK, nullable)
- `notification_type`, `title`, `body`, `priority`
- `related_entity_type`, `related_entity_id`
- `read_at` (nullable), `delivery_state` (nullable)
- Timestamps, soft-delete: yes

### Outbox

**`outbox_events`**:
- `id` (UUID PK), `business_id` (FK)
- `event_type`, `aggregate_type`, `aggregate_id`
- `payload` (JSONB), `idempotency_key` (unique)
- `status` (PENDING / PROCESSING / PROCESSED / RETRYABLE / FAILED)
- `attempt_count`, `available_at`, `processed_at`, `last_error`
- `processing_started_at` (for lease/recovery)
- `created_at`, `updated_at`
- Soft-delete: **no** (operational record)

### Webhooks

**`communication_webhooks`**:
- `id` (UUID PK), `provider`, `external_event_id`, `event_type`
- `communication_id` (FK, nullable), `raw_payload` (JSONB)
- `processing_status`, `error_metadata` (JSONB)
- `received_at`, `processed_at`
- Timestamps, soft-delete: **no** (immutable record)
- Unique: `(provider, external_event_id)` — webhook idempotency

### Audit

**`communication_audit_events`**:
- `id` (UUID PK), `event_type`, `actor_id` (FK, nullable)
- `business_id` (FK), `customer_id` (FK, nullable)
- `channel`, `purpose`, `communication_id` (FK, nullable)
- `brain_version_id` (FK, nullable), `decision_evidence` (JSONB)
- `provider_reference`, `metadata` (JSONB)
- `created_at`
- Soft-delete: **no** (append-only, immutable)
- Audit event types: `COMMUNICATION_REQUESTED`, `COMMUNICATION_ALLOWED`, `COMMUNICATION_DENIED`, `COMMUNICATION_DEFERRED`, `COMMUNICATION_SENT`, `COMMUNICATION_DELIVERED`, `COMMUNICATION_FAILED`, `NOTIFICATION_CREATED`, `NOTIFICATION_READ`, `CONSENT_GRANTED`, `CONSENT_REVOKED`, `SUPPRESSION_ADDED`, `SUPPRESSION_REMOVED`

### Indexes (all tables)
- `business_id` on all business-scoped tables
- `customer_id` on customer-scoped tables
- `status` on communications, outbox_events, notifications
- `channel`, `purpose` on communications, preferences
- `outbox_events`: composite `(status, available_at)` for efficient polling
- `communication_attempts`: `communication_id`
- `notifications`: `(customer_id, read_at)` for unread queries

### Channels
```
EMAIL, SMS, WHATSAPP, PUSH, IN_APP, VOICE
```

### Purposes
```
TRANSACTIONAL, SERVICE_NOTIFICATION, REMINDER, FOLLOW_UP,
AUTHENTICATION, PAYMENT, INVOICE, MARKETING, CAMPAIGN
```

## API Endpoints

### Communication (business-scoped)
```
GET    /businesses/{business_id}/communications
GET    /businesses/{business_id}/communications/{id}
GET    /businesses/{business_id}/communications/{id}/attempts
```

### Notifications
```
GET    /businesses/{business_id}/notifications
GET    /notifications/my-notifications
PATCH  /notifications/my-notifications/{id}/read
GET    /notifications/my-notifications/unread-count
```

### Templates (business-scoped)
```
POST   /businesses/{business_id}/communication-templates
GET    /businesses/{business_id}/communication-templates
GET    /businesses/{business_id}/communication-templates/{id}
PUT    /businesses/{business_id}/communication-templates/{id}
POST   /businesses/{business_id}/communication-templates/{id}/activate
POST   /businesses/{business_id}/communication-templates/{id}/deactivate
GET    /businesses/{business_id}/communication-templates/{id}/versions
```

### Communication Config (business-scoped)
```
GET    /businesses/{business_id}/communication-config/channels
PUT    /businesses/{business_id}/communication-config/channels/{channel}
GET    /businesses/{business_id}/communication-config/purposes
PUT    /businesses/{business_id}/communication-config/purposes/{purpose}
```

### Consent/Preferences (customer-facing)
```
GET    /customer/communication-preferences
PUT    /customer/communication-preferences
POST   /customer/communication-preferences/opt-in
POST   /customer/communication-preferences/opt-out
GET    /customer/communication-preferences/suppression-state
```

### Webhooks (provider-facing)
```
POST   /webhooks/communications/{provider}
```
Uses provider signature verification, not user auth token.

## Integration with Existing Domains

Phase 14A adds outbox event writes to existing domain services:
- `QuoteService` → `QUOTE_ISSUED`, `QUOTE_ACCEPTED`
- `BookingService` → `BOOKING_PROPOSED`, `BOOKING_CONFIRMED`, `BOOKING_CANCELLED`
- `ServiceExecutionService` → `SERVICE_STARTED`, `SERVICE_COMPLETED`
- `InvoiceService` → `INVOICE_ISSUED`

Each service receives an `OutboxRepository` injected and writes events in the same PostgreSQL transaction as the domain change.

## Historical Reproducibility

Every governed communication preserves:
- `brain_version_id` — the Brain version that governed the decision
- `decision_evidence` — full policy evaluation evidence (JSONB)
- `channel`, `purpose`
- `provider_reference`
- Consent/suppression state at time of decision
- Frequency/timing decision

Changing the active Brain does not rewrite historical communication decisions.

## Tenant Isolation

All business-scoped records enforce tenant isolation at the repository level. Business A cannot access Business B's communications, recipients, preferences, templates, notifications, outbox events, webhooks, or audit events.

## Testing Strategy

### Domain
- Communication lifecycle, notification lifecycle, template lifecycle
- Configuration, consent, suppression

### Policy
- Allowed/denied communication, marketing consent, transactional rules
- Frequency limits, calling hours, Business Brain decision integration

### Security
- Authentication, RBAC, tenant isolation
- Cross-business access prevention, customer access boundaries

### Idempotency
- Duplicate event, duplicate communication request, duplicate webhook

### Providers
- Adapter contract, provider reference, success/failure, delivery status
- Provider SDK exception translation, retryability classification

### Notifications
- Creation, unread/read, event association, routing

### Outbox
- Transactional atomicity (domain change + outbox event in same transaction)
- Retry, idempotency, concurrent processing, lease recovery

### PostgreSQL
- Integration tests against real PostgreSQL using existing test infrastructure

## Configuration Additions

```python
# config.py additions
whatsapp_provider: str = "mock"
whatsapp_api_key: str = ""
push_provider: str = "mock"
push_api_key: str = ""
voice_provider: str = "twilio"  # or "mock"
twilio_account_sid: str = ""
twilio_auth_token: str = ""
twilio_phone_number: str = ""
outbox_poll_interval_seconds: int = 5
outbox_batch_size: int = 10
outbox_max_attempts: int = 5
outbox_lease_seconds: int = 300
```

## Completion Criteria

At the end of 14A, FIELDed has a functioning communication foundation:
```
FIELDed Operational Event
    ↓
Notification / Communication Request
    ↓
Purpose
    ↓
Consent + Eligibility
    ↓
Communication Policy
    ↓
Business Brain
    ↓
Authorization
    ↓
Communication Service
    ↓
Provider Adapter
    ↓
Email / SMS / WhatsApp / Push / In-App
    ↓
Delivery Result
    ↓
Audit + History
```

Voice is represented as a first-class provider/channel boundary, ready for the 14B Call Agent implementation.
