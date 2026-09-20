# Phase 14B.1 — Voice / Call Agent Domain & Database Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Production-grade voice domain + persistence foundation (calls, participants, attempts, sessions, escalations, Call Agent config, campaign foundation) integrating with Phase 14A communication infrastructure.

**Architecture:** New `app/domain/voice/` package following existing repository/service/state-machine conventions. VoiceCall hangs off the existing `Communication` entity (nullable FK). Deterministic call lifecycle enforced via `CALL_TRANSITIONS` map in `app/domain/common/enums.py`; every transition emits a `CommunicationAuditEvent`. Database-enforced idempotency via partial unique index. No provider calls, no API endpoints, no conversational agent in this block.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async, Alembic, PostgreSQL 16, pytest + pytest-asyncio.

---

## Verified conventions (from codebase inspection)

- Models inherit `BaseModel` (`app/domain/common/base_model.py`): UUID pk, `created_at`, `updated_at`, `deleted_at` (soft delete).
- Status/enum columns are `String(50)` holding Python `StrEnum` **UPPERCASE** values (14A style, e.g. `CommunicationStatus.PENDING = "PENDING"`).
- State machines: `TRANSITIONS: dict[Status, set[Status]]` maps in `app/domain/common/enums.py`; services raise `StateTransitionError` from `app.exceptions`.
- Repositories: class takes `AsyncSession`, `flush()` never `commit()`, filter `deleted_at.is_(None)`, tenant-scope by `business_id` (children scope via parent join).
- Migrations: handwritten, `revision = "0NN_<name>"`, `down_revision` = previous; indexes `ix_<table>_<col>`; partial unique indexes with `postgresql_where`.
- Tests: real PostgreSQL `postgresql+asyncpg://fielded:fielded@localhost:5432/fielded_test`; `db_session` fixture; schema checks via `information_schema`; factories in `tests/factories.py`.
- Provider boundary (unchanged): `app/adapters/voice/base.py` `VoiceProvider` / `VoiceCallRequest` / `VoiceCallResult`.
- Audit model (reused, no new audit table): `CommunicationAuditEvent` + `AuditRepository` (`app/domain/communication/`). Call provenance stored in its `metadata` JSONB + `communication_id` link.
- 14A responsibility boundary: operational config in dedicated tables; governed rules stay in `BrainVersion.communication_config` (already exists — no change).

## File map

| Action | File | Responsibility |
|---|---|---|
| Modify | `backend/app/domain/common/enums.py` | Voice enums + transition maps + `CALL_*` audit event types |
| Create | `backend/app/domain/voice/__init__.py` | Package marker (empty, matches `communication/`) |
| Create | `backend/app/domain/voice/models.py` | VoiceCall, VoiceCallParticipant, VoiceCallAttempt, VoiceCallSession, VoiceCallEscalation, CallAgentConfiguration, CommunicationCampaign, CampaignRecipient |
| Create | `backend/app/domain/voice/repository.py` | Repos for all voice entities + campaigns (+ recipient) |
| Create | `backend/app/domain/voice/service.py` | `VoiceCallLifecycleService` (call/session/escalation lifecycle, audit) + purpose/type consistency + fail-closed config gating |
| Create | `backend/app/domain/voice/campaign_service.py` | `CampaignService` (create + validated campaign/recipient status transitions; no execution) |
| Create | `backend/alembic/versions/011_phase14b_voice_call_agent.py` | Migration 011 (full upgrade/downgrade) |
| Modify | `backend/tests/conftest.py` | Import voice models so `Base.metadata.create_all` covers them |
| Create | `backend/tests/integration/test_phase14b_voice_foundation.py` | Targeted 14B.1 tests |

No changes to: 14A models/repositories/policy/orchestration, adapters, `BrainVersion.communication_config`, API layer.

---

## Task 1: Enums (`app/domain/common/enums.py`)

Append after the 14A section:

```python
class CallType(StrEnum):
    TRANSACTIONAL = "TRANSACTIONAL"
    MARKETING = "MARKETING"

class CallPurpose(StrEnum):
    # Transactional purposes
    SERVICE_CONFIRMATION = "SERVICE_CONFIRMATION"
    BOOKING_CONFIRMATION = "BOOKING_CONFIRMATION"
    BOOKING_REMINDER = "BOOKING_REMINDER"
    QUOTE_FOLLOW_UP = "QUOTE_FOLLOW_UP"
    RESCHEDULE = "RESCHEDULE"
    CANCELLATION = "CANCELLATION"
    INVOICE_REMINDER = "INVOICE_REMINDER"
    PAYMENT_REMINDER = "PAYMENT_REMINDER"
    SERVICE_COMPLETION_FOLLOW_UP = "SERVICE_COMPLETION_FOLLOW_UP"
    INFORMATION_COLLECTION = "INFORMATION_COLLECTION"
    MISSED_CALL_FOLLOW_UP = "MISSED_CALL_FOLLOW_UP"
    HUMAN_ESCALATION = "HUMAN_ESCALATION"
    # Marketing purposes
    SERVICE_PROMOTION = "SERVICE_PROMOTION"
    EXISTING_CUSTOMER_CAMPAIGN = "EXISTING_CUSTOMER_CAMPAIGN"
    LEAD_FOLLOW_UP = "LEAD_FOLLOW_UP"
    REACTIVATION = "REACTIVATION"
    RENEWAL_REMINDER = "RENEWAL_REMINDER"
    MARKETING_CAMPAIGN = "MARKETING_CAMPAIGN"

CALL_PURPOSE_TYPE: dict[CallPurpose, CallType] = { ... all 12 transactional → TRANSACTIONAL, all 6 marketing → MARKETING }

class CallStatus(StrEnum):
    REQUESTED, AUTHORIZED, QUEUED, INITIATING, RINGING, CONNECTED, IN_PROGRESS, COMPLETED,
    FAILED, NO_ANSWER, BUSY, DECLINED, CANCELLED, EXPIRED, ESCALATED

CALL_TRANSITIONS: dict[CallStatus, set[CallStatus]] = {
    REQUESTED:   {AUTHORIZED, CANCELLED, FAILED, EXPIRED},
    AUTHORIZED:  {QUEUED, CANCELLED, FAILED, EXPIRED},
    QUEUED:      {INITIATING, CANCELLED, FAILED, EXPIRED},
    INITIATING:  {RINGING, CANCELLED, FAILED, EXPIRED},
    RINGING:     {CONNECTED, NO_ANSWER, BUSY, DECLINED, FAILED, CANCELLED, EXPIRED},
    CONNECTED:   {IN_PROGRESS, COMPLETED, FAILED, ESCALATED},
    IN_PROGRESS: {COMPLETED, FAILED, ESCALATED},
    # Terminal
    COMPLETED/FAILED/NO_ANSWER/BUSY/DECLINED/CANCELLED/EXPIRED/ESCALATED: set(),
}

class CallParticipantType(StrEnum): CUSTOMER, BUSINESS_MEMBER, AGENT, HUMAN_AGENT, EXTERNAL

class CallAttemptStatus(StrEnum): REQUESTED, RINGING, CONNECTED, COMPLETED, FAILED, NO_ANSWER, BUSY, DECLINED, CANCELLED

class CallSessionStatus(StrEnum): ACTIVE, COMPLETED, FAILED, ESCALATED
CALL_SESSION_TRANSITIONS = { ACTIVE: {COMPLETED, FAILED, ESCALATED}, COMPLETED/FAILED/ESCALATED: set() }

class EscalationStatus(StrEnum): NONE, REQUESTED, ASSIGNED, ACCEPTED, RESOLVED, CANCELLED
ESCALATION_TRANSITIONS = { NONE: {REQUESTED}, REQUESTED: {ASSIGNED, CANCELLED}, ASSIGNED: {ACCEPTED, CANCELLED},
    ACCEPTED: {RESOLVED}, RESOLVED: set(), CANCELLED: set() }

class CampaignStatus(StrEnum): DRAFT, SCHEDULED, ACTIVE, PAUSED, COMPLETED, CANCELLED
CAMPAIGN_TRANSITIONS = { DRAFT: {SCHEDULED, ACTIVE, CANCELLED}, SCHEDULED: {ACTIVE, CANCELLED},
    ACTIVE: {PAUSED, COMPLETED, CANCELLED}, PAUSED: {ACTIVE, CANCELLED}, COMPLETED: set(), CANCELLED: set() }

class CampaignRecipientStatus(StrEnum): PENDING, ELIGIBLE, CONTACTED, COMPLETED, SKIPPED, SUPPRESSED, FAILED
CAMPAIGN_RECIPIENT_TRANSITIONS = { PENDING: {ELIGIBLE, SKIPPED, SUPPRESSED, FAILED},
    ELIGIBLE: {CONTACTED, SKIPPED, SUPPRESSED, FAILED}, CONTACTED: {COMPLETED, FAILED},
    COMPLETED/SKIPPED/SUPPRESSED/FAILED: set() }
```

Extend `AuditEventType` with: `CALL_REQUESTED, CALL_AUTHORIZED, CALL_QUEUED, CALL_INITIATED, CALL_RINGING, CALL_CONNECTED, CALL_SESSION_STARTED, CALL_IN_PROGRESS, CALL_COMPLETED, CALL_FAILED, CALL_NO_ANSWER, CALL_BUSY, CALL_DECLINED, CALL_CANCELLED, CALL_EXPIRED, CALL_ESCALATED, CALL_ESCALATION_ASSIGNED, CALL_ESCALATION_ACCEPTED, CALL_ESCALATION_RESOLVED, CALL_ESCALATION_CANCELLED`.

## Task 2: Models (`app/domain/voice/models.py`)

- **VoiceCall** `voice_calls`: business_id FK businesses CASCADE; customer_id FK users SET NULL; enquiry_id FK enquiries SET NULL; quote_id FK quotes SET NULL; booking_id FK bookings SET NULL; service_execution_id FK service_executions SET NULL; invoice_id FK invoices SET NULL; communication_id FK communications SET NULL; brain_version_id FK brain_versions SET NULL; call_type String(50); purpose String(50); status String(50) default REQUESTED; to_number String(50); from_number String(50) null; provider String(100); provider_reference String(500) null; idempotency_key String(500); requested_at (tz, default now); authorized_at/queued_at/initiated_at/connected_at/completed_at/failed_at nullable tz; failure_code String(100) null; failure_reason Text null. Indexes: business_id, customer_id, status, call_type, purpose, communication_id. Partial unique: `uq_voice_calls_business_idempotency (business_id, idempotency_key) WHERE deleted_at IS NULL`. Relationships: business, customer, brain_version, communication, participants/attempts/sessions/escalations (cascade all, delete-orphan).
- **VoiceCallParticipant** `voice_call_participants`: call_id FK voice_calls CASCADE; participant_type String(50); user_id FK users SET NULL; customer_id FK users SET NULL; business_member_id FK business_members SET NULL; phone_number String(50); display_name String(255) null; role String(100) null; joined_at/left_at nullable tz. Indexes: call_id, user_id.
- **VoiceCallAttempt** `voice_call_attempts` (append-oriented): call_id FK voice_calls CASCADE; attempt_number Integer; provider String(100); provider_reference String(500) null; status String(50) default REQUESTED; requested_at tz; started_at/connected_at/completed_at nullable; failure_code String(100) null; failure_reason Text null; retryable Boolean default false; provider_payload_reference String(500) null. Index: call_id. Unique: `uq_voice_call_attempts_call_attempt (call_id, attempt_number)`.
- **VoiceCallSession** `voice_call_sessions`: call_id FK voice_calls CASCADE; session_status String(50) default ACTIVE; started_at tz; ended_at null; agent_session_reference String(500) null; language String(50) null; transcript_reference String(500) null; recording_reference String(500) null; human_escalation_requested Boolean default false; human_escalation_at null. Index: call_id. (No large payloads — references only.)
- **VoiceCallEscalation** `voice_call_escalations`: call_id FK voice_calls CASCADE; escalation_status String(50) default REQUESTED; escalation_reason Text; requested_at tz; assigned_member_id FK business_members SET NULL; accepted_at/resolved_at null; resolution_notes Text null. Indexes: call_id, escalation_status.
- **CallAgentConfiguration** `call_agent_configurations`: business_id FK businesses CASCADE (partial unique per business WHERE deleted_at IS NULL); enabled Boolean default false; transactional_calling_enabled Boolean default false; marketing_calling_enabled Boolean default false; default_from_number String(50) null; provider_reference String(500) null; timezone String(100) null; max_attempts Integer default 3; retry_interval_seconds Integer default 300; allowed_calling_hours JSONB null; quiet_periods JSONB null; max_daily_attempts Integer null; max_weekly_attempts Integer null; customer_frequency_limits JSONB null; human_escalation_enabled Boolean default true; recording_enabled Boolean default false; transcription_enabled Boolean default false. Index: business_id.
- **CommunicationCampaign** `communication_campaigns`: business_id FK businesses CASCADE; name String(255); description Text null; channel String(50) (CommunicationChannel values); purpose String(50) (CallPurpose values); status String(50) default DRAFT; start_at/end_at nullable tz; brain_version_id FK brain_versions SET NULL; created_by FK users SET NULL. Indexes: business_id, status, channel, purpose.
- **CampaignRecipient** `campaign_recipients`: campaign_id FK communication_campaigns CASCADE; customer_id FK users SET NULL; phone_number String(50); status String(50) default PENDING; attempt_count Integer default 0; last_attempt_at/completed_at null. Indexes: campaign_id, customer_id, status.

## Task 3: Repositories (`app/domain/voice/repository.py`)

- `VoiceCallRepository`: `create`, `get_by_id(call_id, *, business_id)` (tenant-scoped, selectinload children), `get_by_idempotency_key(business_id, key)`, `list_for_business(business_id, *, call_type, purpose, status, limit, offset)`, `update`.
- `VoiceCallAttemptRepository`: `create`, `get_by_id(attempt_id, *, business_id)` (join voice_calls for tenant scope), `list_for_call(call_id)`, `next_attempt_number(call_id)`, `update`.
- `VoiceCallSessionRepository`: `create`, `get_by_id(session_id, *, business_id)` (join), `get_active_for_call(call_id)`, `update`.
- `VoiceCallEscalationRepository`: `create`, `get_by_id(esc_id, *, business_id)` (join), `get_for_call(call_id)`, `update`.
- `VoiceCallParticipantRepository`: `create`, `list_for_call(call_id)`, `get_by_id(participant_id, *, business_id)` (join).
- `CallAgentConfigRepository`: `get_for_business(business_id)`, `upsert(config)`.
- `CampaignRepository`: `create`, `get_by_id(campaign_id, *, business_id)`, `list_for_business`, `update`.
- `CampaignRecipientRepository`: `create`, `get_by_id(recipient_id, *, business_id)` (join campaigns), `list_for_campaign(campaign_id)`, `update`.

## Task 4: Lifecycle service (`app/domain/voice/service.py`)

`VoiceCallLifecycleService(session)` with repos + communication `AuditRepository` injected. Core pattern:

```python
async def _transition_call(self, call, target: CallStatus, *, event_type: AuditEventType,
                           actor_id=None, reason=None, brain_version_id=None) -> VoiceCall:
    current = CallStatus(call.status)
    allowed = CALL_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise StateTransitionError(f"Cannot transition call from '{current.value}' to '{target.value}'. Allowed: ...")
    previous = call.status
    call.status = target.value
    # set per-target timestamps: authorized_at / queued_at / initiated_at / connected_at / completed_at / failed_at
    await self.call_repo.update(call)
    await self._audit(call, event_type, previous_status=previous, new_status=target.value,
                      actor_id=actor_id, reason=reason, brain_version_id=brain_version_id)
    return call
```

Public methods (all deterministic, NO provider calls): `request_call(...)` — validates purpose↔type via `CALL_PURPOSE_TYPE` (mismatch → `DomainError`), fail-closed config gating (`DomainError` when config missing / disabled / class disabled), idempotent get-or-create on `(business_id, idempotency_key)`; `authorize_call`, `queue_call`, `mark_initiating`, `mark_ringing`, `mark_connected`, `start_session` (requires CONNECTED; creates ACTIVE session; call → IN_PROGRESS; ConflictError if active session exists), `complete_call` (ends active session COMPLETED), `fail_call(failure_code, failure_reason)` (ends active session FAILED), `mark_no_answer`, `mark_busy`, `cancel_call`, `expire_call`, `escalate_call` (CONNECTED/IN_PROGRESS → ESCALATED + VoiceCallEscalation REQUESTED + session ESCALATED), `add_participant`. Escalation transitions: `assign_escalation`, `accept_escalation`, `resolve_escalation`, `cancel_escalation` (validated via `ESCALATION_TRANSITIONS`). Audit: `CommunicationAuditEvent` per transition with `metadata_` = `{call_id, call_type, purpose, previous_status, new_status, reason, source}`.

## Task 5: Campaign service (`app/domain/voice/campaign_service.py`)

`CampaignService(session)`: `create_campaign(...)`, `transition_campaign(campaign, target)` validated via `CAMPAIGN_TRANSITIONS` (StateTransitionError), `add_recipient(...)`, `transition_recipient(recipient, target)` validated via `CAMPAIGN_RECIPIENT_TRANSITIONS` (bumps attempt_count/last_attempt_at on CONTACTED; completed_at on COMPLETED). No audience selection, no scheduler, no execution.

## Task 6: Migration `011_phase14b_voice_call_agent.py`

`revision = "011_phase14b_voice_call_agent"`, `down_revision = "010_phase14a_communications_notifications"`. Creates the 8 tables in dependency order (voice_calls → participants/attempts/sessions/escalations; communication_campaigns → campaign_recipients; call_agent_configurations independent) with all FKs, indexes, partial unique indexes from Task 2. `downgrade()` drops in reverse order.

## Task 7: conftest + tests

- `backend/tests/conftest.py`: add voice model imports (after 14A block).
- `backend/tests/integration/test_phase14b_voice_foundation.py` (mirrors 14A test conventions: `biz_a`/`biz_b` fixtures, information_schema checks):

| Test class | Covers |
|---|---|
| `TestSchemaVerification` | 8 tables exist with required columns; FKs (voice_calls → communications/enquiries/quotes/bookings/service_executions/invoices/brain_versions); unique index `(business_id, idempotency_key)`; unique `(call_id, attempt_number)` |
| `TestCallLifecycle` | Happy path REQUESTED→…→COMPLETED incl. session; fail/no_answer/busy/cancel/expire paths; representative invalid transitions raise `StateTransitionError`; every transition wrote audit events with prev/new status |
| `TestPurposeTypeGating` | Purpose/type mismatch → DomainError; marketing purpose rejected when `marketing_calling_enabled=False`; transactional rejected when disabled; disabled/missing config fail closed |
| `TestIdempotency` | Same (business, key) returns same call, no duplicate row; different key → new call |
| `TestTenantIsolation` | biz B cannot fetch biz A's call/attempt/session/escalation/config/campaign/campaign-recipient (repository returns None / raises) |
| `TestRelationships` | Optional FKs to enquiry, quote, booking, service_execution, invoice, communication all persist and load |
| `TestEscalation` | Full escalation lifecycle REQUESTED→ASSIGNED→ACCEPTED→RESOLVED; CANCELLED path; invalid transition raises |
| `TestCampaign` | Campaign lifecycle DRAFT→SCHEDULED→ACTIVE→PAUSED→ACTIVE→COMPLETED; invalid transition raises; recipient status transitions; NO execution |

## Task 8: Verification (exact commands)

```bash
# 0. PostgreSQL reachable
cd backend && .venv/bin/python -c "import asyncio, asyncpg; asyncio.run(asyncpg.connect('postgresql://fielded:fielded@localhost:5432/postgres'))"

# 1. Migration against real PostgreSQL (scratch DB), incl. downgrade
createdb fielded_migration_test  # or psql -c 'CREATE DATABASE ...'
DATABASE_URL=postgresql+asyncpg://fielded:fielded@localhost:5432/fielded_migration_test .venv/bin/python -m alembic upgrade head
DATABASE_URL=postgresql+asyncpg://fielded:fielded@localhost:5432/fielded_migration_test .venv/bin/python -m alembic downgrade -1
DATABASE_URL=postgresql+asyncpg://fielded:fielded@localhost:5432/fielded_migration_test .venv/bin/python -m alembic upgrade head

# 2. Targeted 14B.1 tests
.venv/bin/python -m pytest tests/integration/test_phase14b_voice_foundation.py -v

# 3. Full backend regression (once, at the end)
.venv/bin/python -m pytest
```

## Boundaries (do NOT implement in 14B.1)

Conversational LLM agent, STT/TTS, scripts/tools execution, campaign audience/scheduler/bulk calls/analytics, voice/customer/Call Agent UI, recording/transcription processing, webhook processing, API endpoints. Provider execution stays in the later orchestration block; `VoiceProvider` remains the untouched 14A abstraction.
