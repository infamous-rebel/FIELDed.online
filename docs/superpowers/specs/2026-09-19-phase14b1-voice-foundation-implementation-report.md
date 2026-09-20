# Phase 14B.1 — Voice / Call Agent Domain & Database Foundation — Implementation Report

Date: 2026-09-19
Plan: `docs/superpowers/plans/2026-09-19-phase14b1-voice-call-agent-foundation.md`

## 14B.1 STATUS

**COMPLETE.** Domain models, repositories, deterministic lifecycle service, campaign
foundation, migration 011, targeted tests (56/56), migration verification against real
PostgreSQL (upgrade → downgrade → re-upgrade), and one full backend regression run
(657 passed) are all done. Nothing from the excluded scope (conversational AI, campaign
execution, webhooks, API endpoints, UI) was implemented.

## Database

Migration `011_phase14b_voice_call_agent` (down_revision
`010_phase14a_communications_notifications`) creates 8 tables:

- `voice_calls` — business-owned call aggregate. Nullable FK anchors to
  `users`, `enquiries`, `quotes`, `bookings`, `service_executions`, `invoices`,
  `brain_versions`, `communications`; `business_id` FK CASCADE (tenant anchor).
  Per-stage timestamps (`requested_at` … `completed_at`/`failed_at`),
  `failure_code`/`failure_reason`. Database-enforced idempotency via partial unique
  index `uq_voice_calls_business_idempotency (business_id, idempotency_key)
  WHERE deleted_at IS NULL`.
- `voice_call_participants` — participant records per call (user / customer /
  business member / external phone), join/left timestamps.
- `voice_call_attempts` — per-dial attempts; unique
  `uq_voice_call_attempts_call_attempt (call_id, attempt_number)`;
  `retryable`, `provider_payload_reference` (reference only — no payload storage).
- `voice_call_sessions` — agent sessions; `session_status`, `started_at`/`ended_at`,
  `agent_session_reference`, `language`; `transcript_reference` /
  `recording_reference` stored as string references only;
  `human_escalation_requested` / `human_escalation_at`.
- `voice_call_escalations` — human escalation lifecycle
  (NONE → REQUESTED → ASSIGNED → ACCEPTED → RESOLVED, CANCELLED);
  `assigned_member_id` FK `business_members` SET NULL, `resolution_notes`.
- `call_agent_configurations` — one per business (partial unique
  `uq_call_agent_configurations_business WHERE deleted_at IS NULL`);
  fail-closed booleans (`enabled`, `transactional_calling_enabled`,
  `marketing_calling_enabled` all default False); `max_attempts` (3),
  `retry_interval_seconds` (300); JSONB `allowed_calling_hours`,
  `quiet_periods`, `customer_frequency_limits`; `human_escalation_enabled`
  (True); `recording_enabled`/`transcription_enabled` (False).
- `communication_campaigns` — campaign foundation; channel, purpose, status
  (DRAFT default), `start_at`/`end_at`, `brain_version_id` FK, `created_by` FK.
- `campaign_recipients` — per-customer campaign state machine rows
  (`status` PENDING default, `attempt_count`, `last_attempt_at`, `completed_at`).

## Domain

- `app/domain/common/enums.py` (modified): `CallType`, `CallPurpose` (12 transactional
  + 6 marketing), authoritative `CALL_PURPOSE_TYPE` mapping, `CallStatus` +
  `CALL_TRANSITIONS`, `CallParticipantType`, `CallAttemptStatus`, `CallSessionStatus`
  + `CALL_SESSION_TRANSITIONS`, `EscalationStatus` + `ESCALATION_TRANSITIONS`,
  `CampaignStatus` + `CAMPAIGN_TRANSITIONS`, `CampaignRecipientStatus` +
  `CAMPAIGN_RECIPIENT_TRANSITIONS`, and 20 `CALL_*` `AuditEventType` entries.
- `app/domain/voice/models.py` (489 lines): the 8 models above; String(50) status
  columns storing StrEnum values (14A convention); no ORM relationships to
  enquiry/quote/booking/execution/invoice (14A `Communication` precedent) — anchors
  are FKs only.
- `app/domain/voice/repository.py` (448 lines): 8 repositories. Primary tables
  tenant-scoped by `business_id`; child tables (participants, attempts, sessions,
  escalations, campaign recipients) tenant-scoped via join to their parent. All
  queries filter `deleted_at IS NULL`; repositories `flush()`, never commit.
- `app/domain/voice/service.py` (789 lines): `VoiceCallLifecycleService` —
  deterministic lifecycle + escalation orchestration. No provider calls, no AI, no
  authorization decisions.
- `app/domain/voice/campaign_service.py` (162 lines): `CampaignService` — campaign
  and recipient state transitions only (no execution).
- `app/domain/voice/__init__.py`: package marker.

## Lifecycle

Full state machine: REQUESTED → AUTHORIZED → QUEUED → INITIATING → RINGING →
CONNECTED → (start_session) IN_PROGRESS → COMPLETED; terminal FAILED / NO_ANSWER /
BUSY / DECLINED / CANCELLED / EXPIRED / ESCALATED. Every transition validated against
`CALL_TRANSITIONS` (`StateTransitionError` on violation); per-stage timestamps set;
one `CommunicationAuditEvent` per transition (`channel="VOICE"`, provenance in
metadata: `call_id`, `call_type`, `purpose`, `previous_status`, `new_status`,
`reason`, `actor_id`). All 14 required methods implemented: `request_call`,
`authorize_call`, `queue_call`, `mark_initiating`, `mark_ringing`, `mark_connected`,
`start_session`, `complete_call`, `fail_call`, `mark_no_answer`, `mark_busy`,
`cancel_call`, `expire_call`, `escalate_call` (+ `record_attempt` and the four
escalation transition methods). `start_session` is CONNECTED-only, creates the single
ACTIVE session (second session → `ConflictError`), and moves the call to IN_PROGRESS.
`fail_call` / `escalate_call` end the active session via `CALL_SESSION_TRANSITIONS`.
No endpoint, no webhook, no provider behavior — deterministic domain logic only.

## Escalation

`escalate_call` (CONNECTED/IN_PROGRESS only) creates a `REQUESTED` escalation, marks
the active session `human_escalation_requested`, and terminates the AI-handled call
as ESCALATED. Escalation then proceeds independently: `assign_escalation`,
`accept_escalation`, `resolve_escalation`, `cancel_escalation`, each validated
against `ESCALATION_TRANSITIONS` with audit events.

## Configuration

`CallAgentConfiguration` is a dedicated operational config; governed policy remains
solely in `BrainVersion.communication_config` — no second policy system. `request_call`
is fail-closed: missing config → `DomainError`; `enabled=False` → `DomainError`;
class-level gate (`transactional_calling_enabled` / `marketing_calling_enabled`) →
`DomainError`. Repository upsert preserves attributes on update. The JSONB
limit fields are persisted but not yet enforced (belongs to placement/queueing
logic in later 14B phases).

## Campaign foundation

`CampaignService` supports `create_campaign` (DRAFT), validated `transition_campaign`
(SCHEDULED/ACTIVE/PAUSED/COMPLETED/CANCELLED per `CAMPAIGN_TRANSITIONS`),
`get_campaign`, `add_recipient` (PENDING), and `transition_recipient`
(`CONTACTED` bumps `attempt_count`/`last_attempt_at`; `COMPLETED` sets
`completed_at`). No execution, scheduler, audience selection, bulk calls, or
analytics — explicitly out of scope for 14B.1.

## Integration with 14A

- `VoiceCall.communication_id` FK → `communications` (nullable); preferred
  Communication → VoiceCall direction; no reverse ORM relationship.
- `VoiceCall.brain_version_id` FK → `brain_versions` for historical reconstruction.
- Audit reuses `CommunicationAuditEvent` (extended with 20 CALL_* event types) —
  no parallel audit table.
- `VoiceProvider` adapter contract (`app/adapters/voice/base.py`) untouched;
  lifecycle methods perform no provider calls.
- 14A architecture otherwise unmodified.

## Tests

`tests/integration/test_phase14b_voice_foundation.py` (1465 lines) — **56 tests,
56 passed** (251.92s, real PostgreSQL 16), 11 classes: state-machine invariants,
schema verification (information_schema/pg_indexes), every valid lifecycle path +
representative invalid ones, audit-evidence multisets per flow, purpose→type gating
including fail-closed config, DB-enforced idempotency, tenant isolation for all 7
entity kinds, relationship anchors (transaction-chain fixture enquiry → quote →
booking → execution → invoice + communication + brain version), attempts, escalation
transitions, campaign foundation, and configuration upsert/enablement. Test
assertions use event-type multisets because PostgreSQL `now()` is
transaction-stable. `tests/conftest.py` extended with the 8 voice model imports so
`create_all` registers them.

## PostgreSQL

Verified on a fresh scratch database (`fielded_migration_test`, PostgreSQL 16.15),
afterwards dropped:

- `alembic upgrade head` from empty → all 11 revisions applied, stamp
  `011_phase14b_voice_call_agent`; `alembic_version.version_num` = VARCHAR(128);
  8 voice tables, FKs to all 9 parent tables, partial unique indexes present
  (42 public tables total).
- `alembic downgrade -1` → stamp `010_phase14a_communications_notifications`,
  voice tables removed (42 → 34 tables).
- `alembic upgrade head` again → stamp 011, 8 voice tables restored.

Pre-existing defect discovered and fixed: Alembic creates `alembic_version` as
VARCHAR(32), but this repository's revision ids are up to 45 characters
(`009_phase13_service_execution_invoice_ledger`), so `upgrade head` never worked on
a real database (CI uses `create_all` and never runs Alembic; the dev DB `fielded`
was stuck at 006). Fixed in `alembic/env.py` with an `ensure_version_table` step
(CREATE TABLE IF NOT EXISTS … VARCHAR(128) + ALTER … TYPE VARCHAR(128)) run inside
Alembic's own `context.begin_transaction()` block. Placement is load-bearing: running
it before `begin_transaction()` auto-begins a transaction, makes Alembic's own
transaction a no-op, and the whole chain is rolled back when the connection closes
(this exact failure mode was reproduced and diagnosed during verification).
Historical migrations 001–010 were not modified. The dev database `fielded` was
intentionally left untouched (still at 006); it can now be migrated with
`alembic upgrade head`.

## Full regression

One run, as required: `pytest tests/` — **657 passed, 0 failures, 18 warnings**
(1657.13s ≈ 27m37s). All warnings are pre-existing (unregistered
`pytest.mark.integration` marks; an HMAC key-length warning inside a legacy JWT unit
test); none originate from 14B.1. Ruff: new/modified files pass `ruff check` and
`ruff format --check` cleanly (lint fixes applied and targeted suite re-verified
56/56 afterwards). Repo-wide lint baseline (523 pre-existing errors, 102
unformatted files) was already red before this phase and was deliberately not
touched.

## Files changed

Created:

- `backend/app/domain/voice/__init__.py`
- `backend/app/domain/voice/models.py` (489 lines)
- `backend/app/domain/voice/repository.py` (448 lines)
- `backend/app/domain/voice/service.py` (789 lines)
- `backend/app/domain/voice/campaign_service.py` (162 lines)
- `backend/alembic/versions/011_phase14b_voice_call_agent.py` (248 lines)
- `backend/tests/integration/test_phase14b_voice_foundation.py` (1465 lines)
- `docs/superpowers/plans/2026-09-19-phase14b1-voice-call-agent-foundation.md`

Modified:

- `backend/app/domain/common/enums.py` (appended voice enums, transition maps,
  20 CALL_* audit event types; existing content untouched)
- `backend/alembic/env.py` (`ensure_version_table`, transaction-placement fix)
- `backend/tests/conftest.py` (voice model imports for metadata registration)

Not modified: historical migrations 001–010, Phase 14A models/services/adapters,
`VoiceProvider` contract.

## Genuine limitations

1. `record_attempt` numbering is append-oriented (`max+1`); concurrent attempt
   creation could race in application code, but the DB unique constraint
   `(call_id, attempt_number)` makes duplicates impossible (a concurrent insert
   raises `IntegrityError`).
2. Idempotent `request_call` is select-then-insert; concurrent duplicate requests
   rely on the partial unique index (IntegrityError, not silent duplication) rather
   than an application-level lock.
3. `allowed_calling_hours`, `quiet_periods`, `customer_frequency_limits`,
   `max_attempts`, and retry intervals are persisted but not yet enforced —
   enforcement belongs to call placement/queueing in a later phase.
4. Offline (`--sql`) Alembic mode does not run `ensure_version_table` (online-path
   only); offline SQL output would still emit a VARCHAR(32) version table on a
   brand-new target.
5. Status columns are String(50) storing enum values (14A convention), not PG
   native enums.
6. Campaign/recipient state transitions are foundation only — no side effects.

## Remaining 14B work

- 14B.2+ Call Agent runtime: conversational AI engine, real `VoiceProvider`
  adapter wiring, session orchestration, transcript/recording ingestion,
  provider webhook processing (no processing exists today — `webhook_received`
  and similar paths deliberately absent).
- Campaign execution: scheduler, audience selection, pacing, quiet-hours /
  allowed-hours / frequency-cap enforcement from the config JSONB, retry policy
  application.
- API endpoints for calls, configuration, and campaigns (none in 14B.1 by design).
- Outbox/worker integration for CALL_* side effects.
- Escalation routing/assignment UX flows on top of the escalation state machine.
