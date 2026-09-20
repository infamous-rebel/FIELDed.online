# Phase 14B.2 — Voice Runtime (Provider, Webhooks, Call Agent, Campaigns, API, Outbox) — Implementation Report

Date: 2026-09-19
Plan: `docs/superpowers/plans/2026-09-19-phase14b2-voice-runtime.md`

## 14B.2 STATUS

**COMPLETE.** All seven remaining 14B scopes are implemented: real voice-provider
runtime, voice webhooks, Call Agent runtime + conversation capabilities, campaign
execution, API layer, and 14A/outbox integration. 124 new targeted tests (180 total
for 14B including 14B.1's 56) pass against real PostgreSQL. Migration 012 verified on
a fresh database. One complete backend regression run: 781 passed, 0 failures. 14A
behavior confirmed unregressed. Architecture synchronization check below.

## Block A — Real voice-provider runtime

`app/domain/voice/provider_service.py` (433 lines) — `VoiceProviderOrchestrationService`
wraps the existing provider-agnostic `VoiceProvider` adapter contract
(`app/adapters/voice/base.py`; Twilio implementation `twilio.py` used as-is).

- **Idempotent initiation**: a call already carrying a `provider_reference` is never
  re-dialed; re-invoking `initiate_call` is a no-op (verified: the provider receives
  exactly one request).
- **Real dial path**: request → authorize → `provider.initiate_call(VoiceCallRequest)`;
  per-dial `VoiceCallAttempt` created via `record_attempt` (unique
  `(call_id, attempt_number)`), `retryable` flag + `provider_payload_reference`
  (reference only — no payload storage).
- **Success**: provider reference persisted on the call, initiation outcome audited,
  and `voice.call_initiated` emitted to the outbox (slot = attempt id).
- **Retryable failure**: attempt recorded as retryable, call stays INITIATING, no
  outbox event (a later retry re-dials); **terminal failure**: `fail_call` → FAILED +
  `voice.call_failed` with `failure_code` PROVIDER_ERROR.
- **Provider state synchronization**: `sync_provider_status(call, provider_status)`
  deterministically maps provider statuses ("ringing" → RINGING, "in-progress" →
  CONNECTED, "completed" → COMPLETED with the connect pre-step when needed,
  "busy"/"no-answer"/"declined"/"failed" → terminal `fail_call`). Illegal skips
  (e.g. INITIATING→CONNECTED) are refused by the state machine.

## Block B — Voice webhooks

`app/domain/voice/webhook_service.py` (322 lines) + public endpoint
`POST /api/v1/webhooks/voice/{provider}` (mirrors the 14A communications webhook).

- **Authentication**: HMAC-SHA256 hex digest over the raw request body in
  `X-Voice-Signature`, secret from `CallAgentConfiguration.webhook_signature_secret`;
  fail-closed (missing/invalid → 401) except the mock provider used by tests/dev.
- **Idempotent persistence**: event id `"{CallSid}:{status}"` stored in
  `communication_webhooks` (unique provider + external_event_id) and linked to the
  call via the new `voice_call_id` column; same-status replay is a duplicate no-op;
  a distinct status is a distinct event.
- **Synchronization**: resolves the call by provider reference, drives `VoiceCall`
  through `sync_provider_status`, updates the active attempt/session, and handles
  terminal/provider failure states.
- **Audit**: significant provider events recorded as `CommunicationAuditEvent`.
  Malformed JSON → 400.

## Block C — Call Agent runtime and conversation capabilities

`app/domain/voice/agent.py` (647 lines) — `VoiceCallAgent(session, ai_provider)` with
constructor-injected `AIProvider` (never a direct provider dependency).

- **Context loading**: customer / business / enquiry / booking anchors plus the
  applicable ACTIVE `BrainVersion`.
- **Brain governance**: agent behavior is governed through Brain policy
  (`BrainVersion.communication_config` voice-agent section); `agent_instructions`
  carries operational style only — deterministic rules stay authoritative.
- **Conversation loop**: `begin(call)` (CONNECTED-only; creates the single ACTIVE
  session via `start_session`, moving the call to IN_PROGRESS) and `handle_turn`
  (requires an active session; violation → `StateTransitionError` → 422). Every turn
  follows AI proposal → structured schema → validation → deterministic execution.
- **Tools/actions**: allowed FIELDed tools execute through deterministic services
  only; structured information collection persisted per session
  (`collected_information`, `conversation_log`, `turn_count`).
- **Escalation/handoff**: escalation triggers → `escalate_call` (REQUESTED
  escalation, session flagged, call ESCALATED, `voice.escalation_requested` emitted);
  human transfer proceeds through the escalation state machine
  (assign/accept/resolve/cancel).
- **Outcome recording**: `record_outcome` validates against `CallOutcome` (unknown →
  422); transactional-vs-marketing separation enforced via
  `TRANSACTIONAL_ONLY_OUTCOMES`; outcome + summary persisted on the session; the call
  completes deterministically → `voice.call_completed`.
- **Recording/transcription boundaries** honored from configuration; stored as string
  references only.

## Block D — Campaign execution

`app/domain/voice/campaign_execution.py` (614 lines) —
`CampaignExecutionService(session, provider)`.

- **Scheduling semantics**: invocation-driven (`process_campaign(campaign, now=...)`);
  activation gates on `start_at`; governed activation (marketing campaigns require
  `brain_version_id` → 422 otherwise).
- **Recipient processing**: per-recipient eligibility — VOICE channel + purpose
  consent (OPTED_IN), DNC (`do_not_contact`), suppression; frequency limits
  (`max_attempts`, `customer_frequency_limits`); calling-window enforcement
  (`allowed_calling_hours`, `quiet_periods`) — enforcing the JSONB limits persisted
  since 14B.1.
- **Marketing-vs-transactional separation**: `transactional_calling_enabled` /
  `marketing_calling_enabled` config gates plus the authoritative
  `CALL_PURPOSE_TYPE` mapping.
- **Execution**: per-recipient calls flow through the full deterministic lifecycle;
  attempts bump recipient `attempt_count`/`last_attempt_at` (CONTACTED);
  `complete_campaign_recipient` settles a recipient COMPLETED from a completed call.
- **Outcome/history**: when every recipient is settled the campaign auto-transitions
  ACTIVE → COMPLETED and emits `voice.campaign_completed`.

## Block E — API layer

`app/api/v1/voice.py` (682 lines) + `app/domain/voice/schemas.py` (237 lines).
The router is mounted with `prefix=""` following the 14A convention, so real URLs are
`/api/v1/{business_id}/voice/...` (same shape as `/api/v1/{business_id}/communications/...`);
the provider webhook is public at `/api/v1/webhooks/voice/{provider}`.

- **Endpoints**: call request / initiate / list / get / cancel; agent-configuration
  upsert (`webhook_signature_secret` is write-only, never returned); agent turns and
  outcome recording; escalation lifecycle (assign / accept / resolve / cancel —
  assigning a cross-business member → 404); campaigns create / transition / process
  and recipient add.
- **Authorization**: full matrix asserted — 401 unauthenticated, 403 non-member,
  server-side role gates (staff → 403 on campaign create, admin → 201), ownership and
  tenant scoping on every lookup (cross-business ids → 404).
- **Serialization**: `db.refresh()` before `model_validate` in mutation endpoints
  (server-generated columns are not loaded after flush; avoids lazy-load outside
  greenlet) — 14A convention.

## Block F — 14A/outbox integration

`app/domain/voice/outbox_integration.py` (159 lines).

- **Emission**: `emit_voice_event(...)` inserts an `OutboxEvent` in the caller's
  transaction (`OutboxRepository`, flush — never commit), idempotency key
  `voice:{event_type}:{aggregate_id}:{slot}`; duplicate emission is a no-op; unknown
  event types are rejected against the `VOICE_EVENT_TYPES` whitelist. Five event
  types: `voice.call_initiated`, `voice.call_completed`, `voice.call_failed`,
  `voice.escalation_requested`, `voice.campaign_completed`.
- **Wiring**: emissions live inside the deterministic services (provider
  orchestration, lifecycle complete/fail/escalate, campaign auto-completion) — the
  transactional boundary is preserved; the worker delivers later.
- **Processing**: `VoiceEventOrchestrator.process_event` turns `voice.*` events into
  idempotent in-app Notifications (key `notification:{outbox_event_id}`, mirroring 14A
  `_create_notification`) and makes **no provider calls**. `app/workers/__init__.py`
  routes `event_type.startswith("voice.")` → voice orchestrator, everything else → the
  unchanged 14A `OrchestrationService`; a voice event without a configured voice
  orchestrator raises (→ retryable/failed — never silently dropped).
  `workers/outbox.py` CLI constructs both orchestrators.

## Database (migration 012)

`012_phase14b_voice_runtime` (down_revision `011_phase14b_voice_call_agent`), additive:

- `voice_calls.campaign_id` (+ FK `communication_campaigns` SET NULL, + index)
- `voice_call_sessions`: `collected_information` (JSONB), `conversation_log` (JSONB),
  `turn_count` (int, default 0), `outcome`, `outcome_summary`
- `call_agent_configurations`: `agent_instructions`, `webhook_signature_secret`
- `communication_webhooks.voice_call_id` (+ FK `voice_calls` SET NULL, + index) —
  the single provider-event store now spans channels

## Integration with 14A

- Only 14A change is additive: `CommunicationWebhook.voice_call_id` + index
  (`app/domain/communication/models.py`). No 14A service, repository, or adapter was
  modified.
- Audit reuses `CommunicationAuditEvent` (no parallel audit table); consent reuses
  14A `ConsentRepository` / `CustomerCommunicationPreference`; notifications reuse the
  14A `Notification` model; webhooks reuse `communication_webhooks`.
- Outbox coexistence proven: a 14A event in the same worker batch is still processed
  by `OrchestrationService` exactly as before.

## Tests

All against real PostgreSQL 16 (per-test schema recreate + rollback, conftest pattern).
Per-file counts (pytest `--collect-only`):

| File | Tests |
|---|---|
| `tests/integration/test_phase14b_voice_foundation.py` (14B.1) | 56 |
| `tests/integration/test_phase14b2_provider_runtime.py` | 24 |
| `tests/integration/test_phase14b3_webhooks.py` | 23 |
| `tests/integration/test_phase14b4_agent.py` | 25 |
| `tests/integration/test_phase14b5_campaigns.py` | 23 |
| `tests/integration/test_phase14b6_api.py` | 19 |
| `tests/integration/test_phase14b7_outbox.py` | 10 |
| **14B total** | **180** |

Required-coverage mapping:

- Lifecycle/state-machine transitions + invalid transitions — foundation suite,
  provider/webhook/agent suites (`CALL_TRANSITIONS`, session, escalation, campaign
  maps; illegal skips and inactive-session turns → 422)
- Tenant isolation — every suite (cross-business ids → 404/403; repositories
  tenant-scoped)
- RBAC/authorization — API suite auth matrix (401/403/role gates/ownership)
- Call idempotency — provider suite re-initiation no-op + DB partial unique index
- Provider success/failure/retry — provider suite (retryable keeps INITIATING with no
  event; terminal fails with PROVIDER_ERROR)
- Webhook authentication + idempotency — webhook suite + API webhook tests (invalid
  signature 401, same-status replay duplicate, mock exemption, invalid JSON 400)
- Session lifecycle — agent suite (begin/turn/turn_count/active-session uniqueness)
- Escalation/handoff — agent + API suites (REQUESTED → ASSIGNED → ACCEPTED →
  RESOLVED; cross-business assignee 404)
- Brain/policy enforcement — agent suite (policy-governed turns via
  `BrainVersion.communication_config`) + governed campaign activation
- Transactional vs marketing separation — agent outcomes (`TRANSACTIONAL_ONLY_OUTCOMES`)
  + config class gates + `CALL_PURPOSE_TYPE`
- Consent/DNC/suppression + calling windows/frequency limits — campaign suite
- Campaign execution — campaign suite (activation, processing, recipient settling,
  auto-completion)
- Outbox integration — outbox suite (emission idempotency, worker routing, 14A
  coexistence, missing-orchestrator loudness, zero provider calls)
- Concurrency — enforced by PostgreSQL constraints rather than application locks:
  partial unique idempotency index on `voice_calls`, unique `(call_id, attempt_number)`,
  unique provider+external_event_id on webhooks; concurrent duplicates raise
  `IntegrityError` instead of duplicating (see Limitations)
- PostgreSQL persistence/integrity — all suites + fresh-DB migration verification

## End-of-phase verification (all five steps, in order)

1. **Fresh migration verification — PASS.** Scratch database `fielded_migration_test`
   (PostgreSQL 16.15, dropped afterwards): `alembic upgrade head` → stamp 012, all 012
   columns verified via `information_schema`; `downgrade -1` → columns gone, stamp
   011; `upgrade head` again → columns restored. Verification script deleted after use.
2. **Full 14B targeted suite — PASS.** `pytest tests/integration/test_phase14b*.py -q`:
   **180 passed** (1212.47s).
3. **One complete backend regression — PASS.** `pytest tests/ -q`:
   **781 passed, 0 failures, 18 warnings** (2645.38s ≈ 44m). All warnings pre-existing
   (legacy JWT unit-test key-length warning); none originate from 14B.
4. **14A regression — CONFIRMED.** The 14A communications suite and the security
   suites are green within the same run; the only 14A file touched is the additive
   `CommunicationWebhook.voice_call_id` column.
5. **Architecture synchronization check — below.**

## Architecture synchronization check (FIELDed core)

- **AI proposal → structured schema → validation → deterministic rules →
  authorization → execution → audit**: every agent turn produces a structured
  proposal that is validated before any effect; tools/actions execute through
  deterministic FIELDed services; every transition records actor, timestamps,
  previous/new state, reason and audit event (`CommunicationAuditEvent`).
- **AI authority limitations upheld**: the agent cannot set prices, determine
  availability, override policy, grant permissions, mutate booking state, or decide
  review eligibility — Brain policy governs behavior, `agent_instructions` is
  operational style only, and outcomes are validated against deterministic enums.
- **Provider-agnostic adapters**: all provider access sits behind `VoiceProvider` /
  `AIProvider` interfaces; the webhook signature scheme is a generic per-business HMAC
  secret with provider-specific schemes available behind the same seam; no provider
  hardcoding in domain code.
- **Tenant isolation foundational**: repositories are business-scoped (child tables
  via parent joins), authorization is resolved server-side from identity, and
  cross-tenant probes are tested to fail closed (404/403).
- **Explicit state machines**: call, session, escalation, campaign, and
  campaign-recipient transitions all validated against explicit transition maps; the
  provider mapping refuses out-of-order jumps; no endpoint mutates state outside the
  validators.
- **Transactional outbox**: in-transaction emission with idempotency keys, idempotent
  worker processing, loud failure on missing orchestrator, and zero provider calls
  from event processing.
- **No duplicate domain concepts**: voice reuses 14A audit, consent, notification,
  and webhook infrastructure rather than introducing parallel tables; campaigns
  extend the 14B.1 foundation instead of a second campaign model.

## Files changed

Created (14B.2):

- `backend/app/domain/voice/provider_service.py` (433 lines)
- `backend/app/domain/voice/webhook_service.py` (322 lines)
- `backend/app/domain/voice/agent.py` (647 lines)
- `backend/app/domain/voice/campaign_execution.py` (614 lines)
- `backend/app/domain/voice/schemas.py` (237 lines)
- `backend/app/domain/voice/outbox_integration.py` (159 lines)
- `backend/app/api/v1/voice.py` (682 lines)
- `backend/alembic/versions/012_phase14b_voice_runtime.py` (124 lines)
- `backend/tests/integration/test_phase14b2_provider_runtime.py` (545 lines)
- `backend/tests/integration/test_phase14b3_webhooks.py` (457 lines)
- `backend/tests/integration/test_phase14b4_agent.py` (655 lines)
- `backend/tests/integration/test_phase14b5_campaigns.py` (766 lines)
- `backend/tests/integration/test_phase14b6_api.py` (844 lines)
- `backend/tests/integration/test_phase14b7_outbox.py` (542 lines)
- `docs/superpowers/plans/2026-09-19-phase14b2-voice-runtime.md`

Modified (14B.2, additive):

- `backend/app/domain/voice/models.py` (489 → 517: campaign_id, session runtime
  columns, agent-config columns)
- `backend/app/domain/voice/repository.py` (448 → 461: additive lookups for provider
  references / webhook resolution / campaign execution)
- `backend/app/domain/voice/service.py` (789 → 855: outbox emissions from
  complete/fail/escalate)
- `backend/app/domain/common/enums.py` (appended `CallOutcome`,
  `TRANSACTIONAL_ONLY_OUTCOMES`)
- `backend/app/domain/communication/models.py` (additive
  `CommunicationWebhook.voice_call_id` + index)
- `backend/app/api/router.py` (voice router registration, `prefix=""`)
- `backend/app/workers/__init__.py` (`voice.*` routing + optional
  `voice_orchestrator` param)
- `backend/app/workers/outbox.py` (CLI constructs `VoiceEventOrchestrator`)

Not modified: `app/adapters/voice/` (base contract + Twilio adapter used as-is),
historical migrations 001–011, 14A services/repositories, Phase 13 modules.

## Genuine limitations

1. **Concurrency is constraint-backed, not lock-backed**: idempotency and uniqueness
   rely on PostgreSQL constraints (partial unique idempotency index, unique attempt
   numbering, unique webhook event id); concurrent duplicate work raises
   `IntegrityError` rather than duplicating. No advisory locks were added.
2. **Campaign execution is invocation-driven** (endpoint / worker call), not a cron
   scheduler; `start_at` gates activation.
3. **Webhook signature is a generic HMAC header**; provider-specific schemes (e.g.
   Twilio's own) plug into the same verification seam but are not implemented.
4. **Recording/transcription are string references only** — no media ingestion or
   storage.
5. **Status columns remain String(50)** storing StrEnum values (14A convention), not
   PG native enums.
6. **Voice event processing creates in-app notifications only** — no external
   channel fan-out (by design: no provider calls from event processing).
7. **Server-driven turn loop** (POST turns); no streaming/websocket transport.
8. Repo-wide lint baseline (pre-existing errors in untouched files) is unchanged; all
   new/modified 14B files pass `ruff check` / `ruff format --check`.

## Remaining 14B work

None — every scope in the 14B.2 request is implemented and verified. Natural next
candidates for a later phase: operator escalation UI, streaming voice transport,
real provider credentials/e2e provider testing, and a scheduled campaign runner.
