# Phase 14B.2 — Voice Runtime, Webhooks, Agent, Campaign Execution, API & Outbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the remaining Phase 14B scopes on top of 14B.1: real voice-provider orchestration, provider webhooks, the governed Call Agent runtime, campaign execution, the voice API layer, and outbox integration — with targeted tests per block and the mandated end-of-phase verification sequence.

**Architecture:** Everything mounts on the 14B.1 deterministic lifecycle (`VoiceCallLifecycleService`) and the unchanged 14A `VoiceProvider` / `AIProvider` adapter contracts. A new orchestration layer drives the lifecycle through the provider; webhooks synchronize provider state idempotently through the existing `communication_webhooks` store; the Call Agent uses AI only to propose actions that deterministic services validate and execute; campaign execution reuses the 14A closed-world policy engine for consent/DNC/frequency/timing/Brain gating. AI never mutates state directly; provider references never masquerade as authority.

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy 2.0 async + PostgreSQL 16 + Alembic; pytest + httpx; adapter ABCs from Phase 14A.

---

## Inspection summary (facts this plan relies on)

- `VoiceProvider.initiate_call(VoiceCallRequest{to, from_number, callback_url, metadata}) -> ProviderResult{success, provider_reference, error, retryable, raw_response}` — `app/adapters/voice/base.py` (UNCHANGED).
- `ProviderFactory.from_settings(settings).voice_provider` resolves Twilio/mock — `app/adapters/__init__.py`.
- Lifecycle transitions (14B.1, unchanged): REQUESTED→AUTHORIZED→QUEUED→INITIATING→{RINGING|CANCELLED|FAILED|EXPIRED}; RINGING→{CONNECTED|NO_ANSWER|BUSY|DECLINED|FAILED|CANCELLED|EXPIRED}; CONNECTED→{IN_PROGRESS|COMPLETED|FAILED|ESCALATED}; IN_PROGRESS→{COMPLETED|FAILED|ESCALATED}. Retries keep the call in INITIATING; each dial is an appended `VoiceCallAttempt` row.
- `CommunicationPolicyService.evaluate(business_id, RecipientContext) -> PolicyDecision` — closed-world chain: channel config → purpose config → consent/suppression/DNC → timing → frequency → Brain rules (REQUIRE_APPROVAL when governance data absent).
- Outbox: `OutboxEvent(business_id, event_type, aggregate_type, aggregate_id, payload, idempotency_key, status, attempt_count, available_at)`; `OutboxRepository.{create,get_by_idempotency_key,claim_pending_events,mark_processed,mark_retryable,mark_failed}`; `app/workers/__init__.py::process_outbox_events(session, orchestrator=..., ...)` commits claim before I/O.
- `communication_webhooks` table: `provider`, `external_event_id` (unique per provider), `event_type`, `communication_id`, `raw_payload`, `processing_status` (RECEIVED default), `error_metadata`, `received_at`, `processed_at` — reusable as the single provider-event store for voice.
- API deps: `get_current_user`, `require_business_member`, `require_business_role(min_role)` (owner>admin>staff, `business_id` path param), `tenant_scope`. conftest provides `client`, `auth_headers`, `second_auth_headers`.
- `BrainVersion.communication_config` JSONB — governed voice-agent policy section `voice_agent` lives here (never in operational config).
- `CallAgentConfiguration` operational fields: enabled flags, `default_from_number`, `timezone`, `max_attempts` (3), `retry_interval_seconds` (300), `allowed_calling_hours`/`quiet_periods`/`customer_frequency_limits` JSONB, `max_daily_attempts`, `max_weekly_attempts`, `human_escalation_enabled`, `recording_enabled`, `transcription_enabled`.
- `AIProvider.complete(prompt, system=...) -> AIResponse` and `structured_output(prompt, schema, system=...) -> dict` — `app/adapters/ai/base.py` (`stub.py` exists).
- Exceptions: `app.exceptions.{DomainError, ConflictError, StateTransitionError, NotFoundError, AuthenticationError, AuthorizationError, TenantIsolationError}`.
- Tests run against real PostgreSQL (`fielded_test`); conftest recreates the schema per test; voice models imported in conftest.

## Schema changes — migration `012_phase14b_voice_runtime`

File: `backend/alembic/versions/012_phase14b_voice_runtime.py` (revision `012_phase14b_voice_runtime`, down_revision `011_phase14b_voice_call_agent`).

| Table | Change |
|---|---|
| `voice_calls` | add `campaign_id UUID NULL FK→communication_campaigns (SET NULL)` + index `ix_voice_calls_campaign_id` |
| `voice_call_sessions` | add `outcome VARCHAR(50) NULL`, `outcome_summary TEXT NULL`, `collected_information JSONB NULL`, `conversation_log JSONB NULL`, `turn_count INTEGER NOT NULL SERVER_DEFAULT '0'` |
| `call_agent_configurations` | add `agent_instructions TEXT NULL`, `webhook_signature_secret VARCHAR(255) NULL` |
| `communication_webhooks` | add `voice_call_id UUID NULL FK→voice_calls (SET NULL)` + index `ix_comm_webhooks_voice_call_id` |

Downgrade drops columns/indexes in reverse. Model updates: `voice/models.py` (VoiceCall.campaign_id + relationship; VoiceCallSession 5 new columns; CallAgentConfiguration 2 new columns), `communication/models.py` (CommunicationWebhook.voice_call_id), `common/enums.py` (new `CallOutcome` StrEnum + `AgentAction` StrEnum + `CALL_AGENT_ACTIONS` map; new AuditEventType entries `CALL_PROVIDER_STATE_SYNC`, `CALL_AGENT_TURN`, `CALL_AGENT_ACTION_EXECUTED`, `CALL_AGENT_HANDOFF_REQUESTED`, `CAMPAIGN_PROCESSING_STARTED`, `CAMPAIGN_RECIPIENT_SUPPRESSED`, `CAMPAIGN_RECIPIENT_SKIPPED`).

---

### Block A — Provider orchestration runtime

**Files:** Create `app/domain/voice/provider_service.py`; modify `app/domain/voice/models.py` (campaign_id), `common/enums.py`, conftest (no new models → no conftest change needed for Block A alone).

- [ ] `VoiceProviderOrchestrationService(session, voice_provider: VoiceProvider, lifecycle: VoiceCallLifecycleService | None = None)` — builds its own lifecycle if not injected.
- [ ] `async initiate_call(call: VoiceCall, *, actor_id=None) -> VoiceCall`
  1. Guard: `CallStatus(call.status)` must be in `{AUTHORIZED, QUEUED, INITIATING}`; else `StateTransitionError`.
  2. Idempotency: if `call.provider_reference` is set and a non-failed attempt with that reference exists → return call unchanged (idempotent re-initiation, no double dial).
  3. Retry guard: count attempts for call; if `attempt_count >= config.max_attempts` → `fail_call(call, failure_code="MAX_ATTEMPTS_EXCEEDED")` and return; if the last attempt is retryable-failed and `now - last_attempt.requested_at < retry_interval_seconds` → `DomainError("retry interval not elapsed")`.
  4. If AUTHORIZED → `lifecycle.queue_call(call)`; then `lifecycle.mark_initiating(call)` (INITIATING is the retry-stable state).
  5. `attempt = lifecycle.record_attempt(call, provider=voice_provider.provider_name, status="REQUESTED")`.
  6. `result = await voice_provider.initiate_call(VoiceCallRequest(to=call.to_number, from_number=call.from_number, metadata={"call_id": str(call.id), "business_id": str(call.business_id), "purpose": call.purpose}))`.
  7. success: `attempt.provider_reference = result.provider_reference`, flush; `call.provider_reference = result.provider_reference`; `call_repo.update(call)`. Call stays INITIATING — provider state sync (webhooks) drives RINGING onward.
  8. retryable failure: `attempt.status="FAILED"`, `attempt.retryable=True`, `attempt.failure_code/reason`; audit `CALL_ATTEMPT_FAILED` via `AuditEventType` (reuse `CALL_FAILED`? No — attempt failure without call failure uses `CALL_PROVIDER_STATE_SYNC` evidence) — call remains INITIATING for retry.
  9. non-retryable failure: same attempt update + `lifecycle.fail_call(call, failure_code=..., failure_reason=...)`.
- [ ] `PROVIDER_STATUS_TRANSITIONS: dict[str, str]` mapping (module-level, deterministic): `{"ringing": "RINGING", "in-progress": "CONNECTED", "completed": "COMPLETED", "busy": "BUSY", "no-answer": "NO_ANSWER", "failed": "FAILED", "canceled": "CANCELLED", "declined": "DECLINED"}`.
- [ ] `async sync_provider_status(call, provider_status: str, *, payload: dict | None = None, actor_id=None) -> VoiceCall` — used by webhooks and tests: updates the latest attempt status; applies call transitions with a pre-step (`RINGING + COMPLETED` → `mark_connected` then `complete_call`; `INITIATING + {BUSY, NO_ANSWER, DECLINED}` → `fail_call`; terminal no-op on already-terminal calls → return unchanged).
- [ ] Emit outbox event `voice.call_initiated` on success and `voice.call_failed` on terminal failure (Block F helper `_emit_voice_event`).

**Tests** `tests/integration/test_phase14b2_provider_runtime.py`:
- success initiation persists provider_reference on call + attempt, call INITIATING, audit evidence present
- idempotent re-initiation returns same call, no second attempt
- retryable failure keeps call INITIATING, attempt FAILED retryable=True; retry after interval creates attempt #2
- retry before interval elapsed raises DomainError
- attempts exhausted triggers MAX_ATTEMPTS_EXCEEDED fail_call
- non-retryable failure fails the call
- initiate from REQUESTED / terminal state raises StateTransitionError
- tenant isolation: initiate a call owned by another business fails (repo get_by_id scoped)

### Block B — Voice webhooks

**Files:** Create `app/domain/voice/webhook_service.py`; modify `communication/models.py` (voice_call_id), `adapters/voice/twilio.py` (no change), API endpoint in Block E consumes service.

- [ ] `verify_webhook_signature(provider: str, payload_bytes: bytes, headers, secret: str | None) -> bool` — generic HMAC-SHA256 over raw body compared to `X-Voice-Signature` (hex); Twilio provider additionally accepts `X-Twilio-Signature` presence path in tests via injected secret. Missing secret configured → reject (fail-closed) unless provider == "mock".
- [ ] `VoiceWebhookService(session)`:
  - `async process_event(*, provider, external_event_id, event_type, payload, call: VoiceCall | None)`:
    1. Persist `CommunicationWebhook` idempotently (`WebhookRepository.get_by_provider_event` → duplicate returns existing row, no state change, `processing_status="DUPLICATE"` not written; returns `{"status": "duplicate"}`).
    2. Resolve call: explicit `call` arg or lookup by `VoiceCall.provider_reference == external CallSid` / attempt provider_reference (unscoped by business — provider callbacks are system-authority; business scope preserved on the row via `voice_call_id`).
    3. Map `event_type` via `PROVIDER_STATUS_TRANSITIONS`; `sync_provider_status(call, ...)`; link `webhook.voice_call_id = call.id`.
    4. Terminal/failure states end sessions (lifecycle handles), write `CALL_PROVIDER_STATE_SYNC` audit with `metadata={event_type, provider_event_id, call_id, mapped_status}`.
    5. `processing_status="PROCESSED"`, `processed_at=now()`; on exception → `processing_status="FAILED"` + `error_metadata`, re-raise.
- [ ] Audit significant provider events only (state-sync transitions already audit; raw no-op events like "queued"/"accepted" update the attempt only).

**Tests** `tests/integration/test_phase14b3_webhooks.py`:
- signature: valid HMAC accepted; tampered payload rejected; missing signature rejected; unsigned allowed only for mock provider
- idempotency: same external_event_id twice → second is duplicate, no second state transition, one audit
- state sync: queued→(no transition) / ringing→RINGING / in-progress→CONNECTED / completed from IN_PROGRESS→COMPLETED / completed from RINGING→CONNECTED→COMPLETED two-step
- terminal failures: no-answer→NO_ANSWER, busy→BUSY, failed→FAILED, canceled→CANCELLED from RINGING; busy from INITIATING→FAILED
- webhook row linked to voice_call_id, processing_status PROCESSED
- provider_reference lookup: call resolved by CallSid without explicit call arg
- audit evidence contains provider event id + mapped status

### Block C — Call Agent runtime & conversation capabilities

**Files:** Create `app/domain/voice/agent.py`; enum additions above.

- [ ] `AgentAction` StrEnum: `CONTINUE`, `COLLECT_INFORMATION`, `REQUEST_HUMAN`, `END_CALL`. `CALL_AGENT_ACTIONS: dict[AgentAction, set[AgentAction]]` (all may follow CONTINUE; REQUEST_HUMAN/END_CALL are terminal for the turn loop).
- [ ] `CallOutcome` StrEnum: `CONFIRMED`, `INFORMATION_COLLECTED`, `RESCHEDULE_REQUESTED`, `CANCELLATION_REQUESTED`, `PAYMENT_ARRANGED`, `COMPLAINT_LOGGED`, `NOT_INTERESTED`, `CALLBACK_REQUESTED`, `NO_CONTACT`, `OTHER`.
- [ ] `VoiceCallAgent(session, ai_provider: AIProvider)`:
  - `async begin(call, *, language=None, actor_id=None) -> VoiceCallSession` — requires CONNECTED; loads governed config (`_load_governance(call)`): active `BrainVersion` (business brain, status ACTIVE) → `communication_config.get("voice_agent", {})`; **closed-world**: no ACTIVE brain or no `voice_agent` section → `DomainError` (agent must not run ungoverned). Stores `brain_version_id` on call if not set. Starts session via lifecycle (`start_session`), seeds `conversation_log=[{"role":"system","content":instructions}]`.
  - `async build_context(call) -> dict` — deterministic loads: business (name), customer profile (name), enquiry/quote/booking/invoice summaries when anchor ids set (bounded field projection only — no authz bypass: caller must already hold the call).
  - `_build_instructions(call, brain_config, context) -> str` — deterministic template: purpose class behavior (transactional = task completion about a specific booking/quote; marketing = campaign script with explicit consent-safe framing), allowed actions from `brain_config["allowed_actions"]` (default all of CONTINUE/COLLECT_INFORMATION/REQUEST_HUMAN/END_CALL), `max_turns`, escalation triggers, `config.agent_instructions` appended as operational style only. Explicit rule text: never quote prices/availability/policies beyond provided context; never promise bookings/changes; request human for anything outside scope.
  - `async handle_turn(call, user_utterance: str, *, actor_id=None) -> dict`:
    1. session = active session (StateTransitionError if none); turn_count check against governed `max_turns` → exceeded: forced `REQUEST_HUMAN` path (AI not consulted).
    2. `proposal = await ai_provider.structured_output(prompt=utterance+context, schema=AGENT_DECISION_SCHEMA, system=instructions)` — schema: `{reply: string, action: enum, collected_information: object, outcome: enum|null, escalation_reason: string|null}`; malformed/unknown action/outcome → `DomainError("agent proposal rejected")` (fail-closed validation).
    3. Action execution through deterministic services only:
       - CONTINUE → append turn to conversation_log.
       - COLLECT_INFORMATION → validate keys ⊆ governed `collectible_fields` (default `["callback_number", "preferred_time", "notes"]`); merge into `session.collected_information`; append turn.
       - REQUEST_HUMAN → gate on `config.human_escalation_enabled` (disabled → DomainError); append turn; `lifecycle.escalate_call(call, escalation_reason=proposal.escalation_reason or "agent requested handoff")`.
       - END_CALL → validate outcome against purpose class (marketing may not report CONFIRMED/PAYMENT_ARRANGED — domain rule); `session.outcome/outcome_summary`; append turn; `lifecycle.complete_call(call, reason=outcome)`.
    4. `session.turn_count += 1`; audit `CALL_AGENT_TURN` per turn (metadata: action, turn_count) and `CALL_AGENT_ACTION_EXECUTED` for state-affecting actions; return `{reply, action, session, call}`.
  - `async record_outcome(call, outcome, summary=None, *, actor_id=None)` — deterministic outcome recording for human/agent-completed sessions (session ACTIVE required; sets outcome fields).
  - Marketing vs transactional: instructions differ; END_CALL outcome validation differs (above); escalation always available to both.

**Tests** `tests/integration/test_phase14b4_agent.py`:
- begin on CONNECTED call creates session, stores brain_version_id, seeds conversation_log
- begin without ACTIVE brain → DomainError; with brain lacking voice_agent section → DomainError (closed-world)
- CONTINUE turn appends log, turn_count increments, CALL_AGENT_TURN audit
- COLLECT_INFORMATION stores validated fields; disallowed field → DomainError
- REQUEST_HUMAN escalates (call ESCALATED, session ESCALATED, escalation row REQUESTED); disabled human_escalation_enabled → DomainError
- END_CALL completes call with outcome; marketing call reporting CONFIRMED → DomainError; transactional CONFIRMED ok
- max_turns exceeded → forced handoff without AI call (AI stub asserts not called)
- malformed AI proposal (unknown action) → DomainError, no state change
- AI stub receives system instructions containing purpose class + allowed actions (authority provenance)
- agent cannot run on marketing-disabled config with marketing purpose (request_call already gates; agent begin re-checks class enablement)

### Block D — Campaign execution

**Files:** Create `app/domain/voice/campaign_execution.py` (imports `CampaignService`).

- [ ] `CampaignExecutionService(session, voice_provider, lifecycle=None)`:
  - `async activate(campaign, *, actor_id)` — governed approval rule: purpose is marketing-class (`CALL_PURPOSE_TYPE[CallPurpose(campaign.purpose)] == MARKETING`) and `campaign.brain_version_id is None` → `DomainError("marketing campaigns require a governing Brain version")`. Then `CampaignService.transition_campaign(DRAFT|SCHEDULED → ACTIVE)`.
  - `_in_calling_window(config, now) -> tuple[bool, str]` — deterministic: `allowed_calling_hours` JSONB `{"days": [0-6], "start_hour": int, "end_hour": int}` + `quiet_periods` `[{"start": "MM-DD", "end": "MM-DD"}]` (or null entries = always allowed); timezone from `config.timezone` (fallback UTC). Outside window → `(False, reason)`.
  - `_frequency_check(config, recipient) -> tuple[bool, str]` — `recipient.attempt_count >= config.max_attempts` → deny; `max_daily_attempts`/`max_weekly_attempts` measured against the campaign's recipients attempted today/this week (count campaign recipients with `last_attempt_at` in window) → deny; `customer_frequency_limits` JSONB `{"per_campaign": n}` optional.
  - `async process_campaign(campaign, *, actor_id=None, now=None) -> dict` — campaign must be ACTIVE (else StateTransitionError). For each PENDING recipient, in order:
    1. calling window → outside: `transition_recipient(SKIPPED)` with reason recorded via audit `CAMPAIGN_RECIPIENT_SKIPPED`; continue.
    2. frequency → over limit: SKIPPED (reason=max_attempts) or FAILED when attempts exhausted; continue.
    3. Policy: `CommunicationPolicyService.evaluate(business_id, RecipientContext(recipient_type="CUSTOMER", customer_id=recipient.customer_id, address=recipient.phone_number, channel="VOICE", purpose="MARKETING" if marketing else "TRANSACTIONAL"))` → DENY: `SUPPRESSED` + audit `CAMPAIGN_RECIPIENT_SUPPRESSED`; REQUIRE_APPROVAL/DEFER/ESCALATE: `SKIPPED`; ALLOW: proceed.
    4. Initiate: `lifecycle.request_call(business_id, to_number=recipient.phone_number, purpose=campaign.purpose, provider=voice_provider.provider_name, idempotency_key=f"campaign:{campaign.id}:{recipient.id}:{recipient.attempt_count + 1}", customer_id=recipient.customer_id, campaign linkage via new `campaign_id` param, brain_version_id=campaign.brain_version_id, source="campaign")` → `provider_orchestration.initiate_call(call)`. Success → `CONTACTED` (attempt_count++, last_attempt_at); provider retryable failure → recipient stays CONTACTED (call retryable) — terminal call failure → `FAILED` recipient; call completion (webhook) later drives `COMPLETED` via `complete_campaign_recipient`.
  - `async complete_campaign_recipient(call, outcome)` — on call COMPLETED with linked campaign → recipient `COMPLETED`; campaign auto-completes when all recipients terminal (`_maybe_complete_campaign`: any PENDING/CONTACTED remain → no; else `transition_campaign(COMPLETED)` + outbox `voice.campaign_completed`).
  - Deterministic only: no scheduling loop inside (execution runs when invoked — API endpoint or worker); `SCHEDULED` campaigns processed only after explicit transition to ACTIVE (start_at enforced as: activate refuses ACTIVE before `start_at` when set).

**Tests** `tests/integration/test_phase14b5_campaigns.py`:
- marketing activation without brain_version_id → DomainError; with → ACTIVE
- activation before start_at → DomainError
- calling window: outside allowed hours → SKIPPED recipients; quiet period → SKIPPED
- consent: policy DENY (opted-out customer) → SUPPRESSED; missing channel config (closed-world) → SKIPPED (approval path)
- frequency: attempt_count at max_attempts → SKIPPED/FAILED; per-campaign limit respected
- processing: ALLOW recipient gets VoiceCall (campaign_id set, idempotency key format), CONTACTED, attempt_count=1; provider success persists reference
- retry across runs: second process_campaign does not duplicate calls (idempotency key) for CONTACTED recipients
- terminal call failure marks recipient FAILED; completion marks COMPLETED and auto-completes campaign
- campaign cancel mid-execution → remaining PENDING untouched
- campaign audit events emitted (processing started, suppressed, skipped)

### Block E — API layer

**Files:** Create `app/domain/voice/schemas.py`, `app/api/v1/voice.py`; modify `app/api/router.py`.

- [ ] Schemas (`voice/schemas.py`): `CallAgentConfigRead/Update` (operational fields only; `agent_instructions`, `webhook_signature_secret` write-only optional), `VoiceCallRead`, `VoiceCallListRead`, `CallRequestCreate` (to_number, purpose, call_type?, customer_id?, anchor ids?, idempotency_key optional → server-generated from auth context), `CallInitiateResponse`, `EscalationRead`, `EscalationActionRequest`, `CampaignCreate` (name, description?, purpose, start_at?, end_at?, brain_version_id?), `CampaignRead`, `CampaignTransitionRequest`, `CampaignRecipientCreate` (customer_id, phone_number), `CampaignRecipientRead`, `AgentTurnRequest` (utterance), `AgentTurnResponse`, `OutcomeRequest` (outcome, summary). All `model_config = {"from_attributes": True}`; no `any`; UUID/datetime typed.
- [ ] Router `voice.py` (prefix-less; mounted like communications):
  - `POST /businesses/{business_id}/voice/agent-config` (upsert; ADMIN+) / `GET .../agent-config` (STAFF+)
  - `POST /businesses/{business_id}/voice/calls` (STAFF+): request_call (+authorize) with `initiate: bool = True` → provider orchestration; returns VoiceCallRead; idempotency honored
  - `GET /businesses/{business_id}/voice/calls` (STAFF+, paginated) / `GET /businesses/{business_id}/voice/calls/{call_id}` (STAFF+; repo tenant-scoped → 404-style AuthorizationError on cross-tenant)
  - `POST /businesses/{business_id}/voice/calls/{call_id}/cancel` (STAFF+)
  - `POST /businesses/{business_id}/voice/calls/{call_id}/turns` (STAFF+): agent turn (requires connected+session; builds AI provider from app.state.settings)
  - `GET/POST /businesses/{business_id}/voice/calls/{call_id}/escalations` + `POST .../escalations/{esc_id}/assign|accept|resolve|cancel` (STAFF+; assign requires member id in business)
  - `POST /businesses/{business_id}/voice/campaigns` (ADMIN+), `GET .../campaigns`, `GET .../campaigns/{id}`, `POST .../campaigns/{id}/transition` (ADMIN+), `POST .../campaigns/{id}/recipients` (ADMIN+), `POST .../campaigns/{id}/execute` (ADMIN+; runs process_campaign)
  - `POST /voice/webhooks/{provider}` (public; signature-verified; 401 on invalid signature; 202 accepted/duplicate) — service from Block B; body read as raw bytes for signature check
  - Provider construction: `ProviderFactory.from_settings(request.app.state.settings)` per request (no global state)
- [ ] Mount: `api_router.include_router(voice.router, prefix="", tags=["voice"])` in `api/router.py` with Phase 14B comment.
- [ ] Error mapping follows existing convention: domain exceptions → HTTP via app exception handlers (already registered in main).

**Tests** `tests/integration/test_phase14b6_api.py` (uses `client`/`auth_headers` fixtures):
- unauthenticated request → 401; customer (non-member) → 403; staff of another business → 404/403 (tenant isolation on every GET/POST by call_id/campaign_id)
- config upsert requires ADMIN (staff → 403); GET works for staff
- call request+initiate happy path → 201/200 with status INITIATING, provider_reference persisted (stub provider success)
- idempotent POST with same idempotency_key returns same call id
- cancel endpoint transitions and persists
- escalation endpoints: assign by cross-business member id → 403/404; accept/resolve happy path
- campaign endpoints: create (staff → 403, admin → 201), transition invalid → 409/422 style error, execute happy path, recipient add
- webhook endpoint: valid signature → 202 accepted; invalid → 401; duplicate → 202 duplicate
- API authorization matrix asserted for: calls GET/POST, config, campaigns, webhook

### Block F — Outbox integration

**Files:** Create `app/domain/voice/outbox_integration.py`; modify `app/workers/__init__.py`.

- [ ] `emit_voice_event(session, *, business_id, event_type, aggregate_type, aggregate_id, payload)` — `OutboxRepository.create` with idempotency_key `voice:{event_type}:{aggregate_id}:{slot}`; duplicate → no-op (get_by_idempotency_key first). Event types: `voice.call_initiated`, `voice.call_completed`, `voice.call_failed`, `voice.escalation_requested`, `voice.campaign_completed`.
- [ ] Wire emission points: provider orchestration (initiated/terminal failure), agent (escalation requested), campaign execution (completed). Emission happens inside the same session/transaction as the state change (preserves transactional boundary; worker handles delivery later).
- [ ] `VoiceEventOrchestrator.process_event(...)` — for `voice.*` events: create idempotent Notification (`notification:{outbox_event_id}` idempotency, mirroring 14A `_create_notification`) with title/body from payload; no provider calls.
- [ ] `app/workers/__init__.py`: `process_outbox_events` gains optional `voice_orchestrator=None` param; routing `event.event_type.startswith("voice.")` → voice orchestrator, else 14A orchestrator (14A behavior untouched when param omitted).

**Tests** `tests/integration/test_phase14b7_outbox.py`:
- call initiation emits `voice.call_initiated` once; re-initiation does not duplicate (idempotency key)
- terminal failure emits `voice.call_failed`; agent handoff emits `voice.escalation_requested`; campaign completion emits `voice.campaign_completed`
- worker pass processes voice events → notifications created; second pass no duplicates
- `voice.*` routing does not disturb 14A event processing (14A event in same batch still handled by OrchestrationService)
- no provider calls from voice event processing (stub AI/voice providers untouched)

---

## End-of-phase verification sequence (ordered)

- [ ] 1. Fresh migration verification on scratch DB (drop/recreate `fielded_migration_test`): `alembic upgrade head` → verify 012 stamp + new columns; `downgrade -1` → columns gone; `upgrade head` again; drop scratch DB.
- [ ] 2. Full 14B targeted suite: `pytest tests/integration/test_phase14b*.py -q` (14B.1 56 + new blocks) — all green.
- [ ] 3. ONE complete backend regression: `pytest tests/ -q` against real PostgreSQL — 0 failures.
- [ ] 4. 14A regression confirmation: the regression run includes `tests/integration/test_phase14a_communications.py` + security tests — verify explicitly in the output; no 14A file modified except `communication/models.py` additive column.
- [ ] 5. Architecture synchronization check: verify final tree against FIELDed core rules (AI proposal→schema→validation→deterministic→audit; provider-agnostic adapters; tenant isolation; explicit state machines) and record in the 14B completion report `docs/superpowers/specs/2026-09-19-phase14b2-voice-runtime-implementation-report.md`.

## Assumptions

- Provider callbacks use CallSid as `external_event_id`; generic HMAC header `X-Voice-Signature` (secret per business on CallAgentConfiguration) — Twilio's own signature scheme remains available behind the same verification seam without hardcoding.
- Campaign execution is invocation-driven (API endpoint / worker call), not a cron scheduler — scheduling semantics live in `start_at` gating at activation.
- The agent conversation loop is server-driven via `POST .../turns` (each provider speech event or operator relay submits a turn); no streaming/websocket in 14B scope.
- Mock provider (empty Twilio credentials) returns success with generated reference — tests inject deterministic stub VoiceProvider/AIProvider via constructor injection, never network.
