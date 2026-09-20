# Voice Production E2E Readiness Assessment

Date: 2026-09-20
Scope: Post-14B.2 production readiness gap analysis
Status: **ASSESSED — NOT PRODUCTION READY FOR REAL-TIME VOICE**

---

## 1. CURRENT STATUS

The FIELDed voice system has a complete, verified **governed call lifecycle and conversation runtime** (14B.1 + 14B.2: 180 tests passing, 781-test full regression green). The deterministic domain layer — state machines, Brain governance, provider orchestration, webhook processing, escalation, campaign execution, outbox integration, and REST API — is production-quality code.

However, the system is **not capable of a real-time production voice conversation**. The gap is not in governance or domain logic — it is in the **audio/telephony transport layer** that sits between Twilio and the existing Call Agent runtime. No STT, no TTS, no streaming transport, no TwiML generation, and no real AI provider exist.

The architecture is correctly structured to **receive** these capabilities as an additive layer on top of the existing governed runtime without redesigning it.

---

## 2. WHAT 14B.2 ALREADY PROVIDES

| Capability | Status | Evidence |
|---|---|---|
| VoiceProvider abstraction (ABC) | ✅ Complete | `app/adapters/voice/base.py` — `VoiceProvider` with `initiate_call()` |
| Twilio voice adapter (outbound dial) | ✅ Complete | `app/adapters/voice/twilio.py` — real Twilio REST API call creation |
| Provider orchestration (dial, retry, sync) | ✅ Complete | `app/domain/voice/provider_service.py` (433 lines) |
| Call lifecycle state machine | ✅ Complete | `app/domain/voice/service.py` (855 lines) — 14 states, explicit transitions |
| VoiceCallSession (conversation state) | ✅ Complete | `app/domain/voice/models.py` — JSONB log, collected info, outcome |
| Call Agent runtime (Brain-governed) | ✅ Complete | `app/domain/voice/agent.py` (647 lines) |
| AI proposal → structured schema → validation | ✅ Complete | `AGENT_DECISION_SCHEMA`, `_validate_proposal()` |
| Deterministic tool execution | ✅ Complete | Agent actions execute through `VoiceCallLifecycleService` only |
| Escalation state machine | ✅ Complete | REQUESTED → ASSIGNED → ACCEPTED → RESOLVED |
| Business Brain governance | ✅ Complete | Closed-world: no active Brain + voice_agent section → agent refuses to run |
| Transactional/marketing separation | ✅ Complete | `TRANSACTIONAL_ONLY_OUTCOMES`, `CALL_PURPOSE_TYPE` |
| Consent/DNC/suppression/frequency/timing | ✅ Complete | `CampaignExecutionService` (614 lines) |
| Webhook ingestion + idempotency | ✅ Complete | `app/domain/voice/webhook_service.py` (322 lines) |
| Provider status synchronization | ✅ Complete | Deterministic mapping in `PROVIDER_STATUS_TRANSITIONS` |
| Outbox integration (5 event types) | ✅ Complete | `app/domain/voice/outbox_integration.py` (159 lines) |
| REST API (20+ endpoints) | ✅ Complete | `app/api/v1/voice.py` (682 lines) |
| Tenant isolation + RBAC | ✅ Complete | Server-side authorization on every endpoint |
| Campaign execution | ✅ Complete | `app/domain/voice/campaign_execution.py` (614 lines) |
| AIProvider abstraction | ✅ Complete | `app/adapters/ai/base.py` — `complete()` + `structured_output()` |
| Configuration surface | ✅ Complete | `CallAgentConfiguration` model + env vars |

**In summary**: 14B.2 delivers the entire governed decision layer. What it does NOT deliver is the audio transport between a human caller and that decision layer.

---

## 3. REAL-TIME VOICE CAPABILITY MATRIX

Each capability is classified against the requirement for a real production voice conversation: Customer ↔ Twilio ↔ FIELDed ↔ STT ↔ Agent ↔ TTS ↔ Twilio ↔ Customer.

| # | Capability | Classification | Evidence |
|---|---|---|---|
| A | Receiving live audio from Twilio | **NOT IMPLEMENTED** | Twilio adapter (`twilio.py`) only has `initiate_call()`. No `<Stream>`, `<Gather>`, or Media Streams WebSocket handler exists. Zero WebSocket/ASGI code in the codebase. |
| B | Streaming audio into STT | **NOT IMPLEMENTED** | No STT provider adapter exists. No `SpeechToTextProvider` ABC. No Deepgram/Whisper/Google STT integration. |
| C | Detecting speech boundaries / turns | **NOT IMPLEMENTED** | No voice activity detection (VAD) or silence detection. Turn boundaries are currently submitted via `POST .../turns` by an external operator. |
| D | Sending transcript into Call Agent | **IMPLEMENTED** (POST-driven) | `VoiceCallAgent.handle_turn(call, user_utterance)` at `agent.py:292` accepts text and processes it through the full governed pipeline. Not connected to live audio. |
| E | Executing deterministic FIELDed tools during a live call | **IMPLEMENTED** (POST-driven) | Agent actions (`COLLECT_INFORMATION`, `REQUEST_HUMAN`, `END_CALL`) execute through deterministic services. Verified by 25 agent tests. Not connected to live audio timing. |
| F | Generating agent response (text) | **IMPLEMENTED** (POST-driven) | `_propose()` at `agent.py:489` produces structured AI proposals. Uses `AIProvider.structured_output()`. Currently resolves to `StubAIProvider` (keyword-based, not conversational). |
| G | Streaming/generated TTS audio back to caller | **NOT IMPLEMENTED** | No TTS provider adapter exists. No `TextToSpeechProvider` ABC. No ElevenLabs/Google TTS/Azure TTS integration. The agent's `reply` string has no audio rendering path. |
| H | Barge-in / interruption handling | **NOT IMPLEMENTED** | No mechanism to interrupt TTS playback or cancel an in-progress AI proposal when the caller starts speaking. Requires streaming transport + VAD. |
| I | Call termination | **IMPLEMENTED** (state machine) | `complete_call()`, `fail_call()`, `cancel_call()` in `service.py`. The state machine is correct. However, there is no TwiML `<Hangup>` generation to actually terminate the telephony session. |
| J | Provider status synchronization | **IMPLEMENTED** | `sync_provider_status()` at `provider_service.py:275` — deterministic mapping of 8 provider statuses. Verified by 24 provider runtime tests. |
| K | Failure/retry handling | **IMPLEMENTED** | Idempotent initiation, attempt limits, retry intervals in `VoiceProviderOrchestrationService`. Verified by tests. |
| L | Escalation to human | **IMPLEMENTED** | Full escalation lifecycle: `VoiceCallEscalation` model, `escalate_call()`, assign/accept/resolve/cancel. Verified by agent + API tests. |
| M | Recording/transcription where configured | **NOT IMPLEMENTED** | `recording_enabled` and `transcription_enabled` toggles exist on `CallAgentConfiguration`. `recording_reference` and `transcript_reference` columns exist on `VoiceCallSession`. No actual media ingestion, storage, or provider integration exists. String references only. |

### Summary

- **IMPLEMENTED**: D, E, F (text-level), I (state machine), J, K, L — 7 of 13
- **NOT IMPLEMENTED**: A, B, C, G, H, M — 6 of 13
- **PARTIALLY IMPLEMENTED**: 0

The implemented capabilities form the complete governed decision layer. The missing capabilities form the audio/telephony transport layer.

---

## 4. REAL TWILIO E2E READINESS

**Verdict: REAL E2E BLOCKED BY CONFIGURATION + IMPLEMENTATION**

### Configuration availability

| Requirement | Status | Evidence |
|---|---|---|
| Twilio credentials in config | ✅ Present | `config.py:91-93` — `twilio_account_sid`, `twilio_auth_token`, `twilio_phone_number` |
| Twilio credentials in .env.example | ❌ Missing | `.env.example` does not include `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`, or `VOICE_PROVIDER` |
| Voice provider selection | ✅ Present | `config.py:88` — `voice_provider: str = "mock"` |
| Public HTTPS webhook URL | ❌ Missing | No configuration for the public URL Twilio should call back to |
| TwiML webhook endpoint | ❌ Missing | No endpoint generates TwiML. Twilio requires a TwiML response when a call connects to know what to do (speak, gather input, stream audio). |
| Status callback URL | ⚠️ Partially present | `POST /api/v1/webhooks/voice/{provider}` exists and processes status callbacks, but Twilio needs this URL configured on the call initiation or phone number |
| Twilio phone number | ❌ Not configured | No phone number provisioned; `twilio_phone_number` defaults to `""` |

### Implementation gaps for E2E

| Requirement | Status | Evidence |
|---|---|---|
| TwiML generation for outbound calls | ❌ Missing | Twilio adapter sends `Url` parameter for callback but no endpoint serves TwiML |
| TwiML generation for call behavior | ❌ Missing | No `<Say>`, `<Gather>`, `<Stream>`, `<Record>`, `<Hangup>` generation anywhere |
| Inbound call handling | ❌ Missing | No inbound webhook handler — only outbound call initiation + status callbacks |
| Media streaming WebSocket | ❌ Missing | No WebSocket endpoint in the FastAPI application |
| STT provider | ❌ Missing | No adapter, no credentials, no integration |
| TTS provider | ❌ Missing | No adapter, no credentials, no integration |
| Real AI provider | ❌ Missing | `_resolve_ai_provider()` always returns `StubAIProvider` (keyword-based discovery stub) |
| Provider-specific webhook verification | ⚠️ Partially present | Generic HMAC; Twilio uses URL+params HMAC (see Section 8) |

---

## 5. STREAMING GAP

**The current report explicitly identifies**: "Server-driven turn loop (POST turns); no streaming/websocket transport."

### Does production conversational voice require a new streaming layer?

**Yes.** The POST-driven turn model cannot deliver the sub-second latency required for natural voice conversation. A human caller expects <500ms response time after finishing speech. The current model requires an external system to POST each turn — there is no such system.

### Smallest required architecture

The preferred approach preserves the existing governed runtime and adds a transport/orchestration layer around it:

```
Twilio Media Streams (WebSocket)
    ↓ raw audio chunks
Streaming Adapter (new — transport layer)
    ↓ audio segments
STT Provider (new — adapter + provider)
    ↓ transcript text
Voice Call Agent (EXISTING — agent.py)
    ↓ structured proposal (reply text)
TTS Provider (new — adapter + provider)
    ↓ audio bytes
Streaming Adapter (new — transport layer)
    ↓ audio chunks
Twilio Media Streams (WebSocket)
    ↓ audio
Customer
```

**Key architectural constraints**:
- The Call Agent runtime (`agent.py`) is NOT redesigned — it receives text, returns text
- The streaming layer is a **transport adapter** that wraps the existing runtime
- All deterministic authority boundaries remain: price, availability, booking, authorization, policy, consent, DNC, escalation rules, transaction state, review eligibility
- The LLM proposes; the deterministic layer executes

**New components required**:
1. WebSocket/ASGI endpoint for Twilio Media Streams
2. `SpeechToTextProvider` ABC + concrete adapter (Deepgram, Whisper, or Google)
3. `TextToSpeechProvider` ABC + concrete adapter (ElevenLabs, Google, or Azure)
4. `StreamingTurnOrchestrator` — bridges audio segments to text turns and back
5. Voice activity detection (VAD) or Twilio's built-in speech detection via `<Gather>`

**Alternative simpler approach**: Use TwiML `<Gather input="speech">` which lets Twilio handle STT and POSTs the transcript back. This avoids the Media Streams WebSocket complexity but adds ~1s latency per turn and limits control over the audio experience.

---

## 6. STT GAP

**Status: NOT IMPLEMENTED**

- No `SpeechToTextProvider` ABC exists
- No STT adapter of any kind exists
- No STT-related environment variables in `config.py`
- No STT-related dependencies in `pyproject.toml`

**Required for production**:
- STT provider ABC (provider-agnostic, matching FIELDed's adapter pattern)
- Concrete adapter (Deepgram for real-time streaming, or Twilio's built-in via `<Gather>`)
- Configuration: `stt_provider`, `stt_api_key`, `stt_model` in `config.py`
- Integration with the streaming transport layer

---

## 7. TTS GAP

**Status: NOT IMPLEMENTED**

- No `TextToSpeechProvider` ABC exists
- No TTS adapter of any kind exists
- No TTS-related environment variables in `config.py`
- No TTS-related dependencies in `pyproject.toml`

**Required for production**:
- TTS provider ABC (provider-agnostic)
- Concrete adapter (ElevenLabs, Google Cloud TTS, or Twilio's built-in `<Say>`)
- Configuration: `tts_provider`, `tts_api_key`, `tts_voice` in `config.py`
- Integration with the streaming transport layer

---

## 8. WEBHOOK SECURITY GAP

### Current verification mechanism

`verify_webhook_signature()` in `webhook_service.py:67-98`:
- Generic HMAC-SHA256 hex digest over the **raw request body**
- Secret from `CallAgentConfiguration.webhook_signature_secret`
- Header: `X-Voice-Signature` (also accepts `X-Twilio-Signature`)
- Timing-safe comparison via `hmac.compare_digest()`
- Fail-closed: missing secret or signature → reject (except `mock` provider)

### Twilio's required production verification mechanism

Twilio uses **request URL validation** ([Twilio docs](https://www.twilio.com/docs/usage/security)):
1. Take the **full request URL** (including query string)
2. Collect **all POST parameters** (form-encoded, not JSON body)
3. Sort parameters alphabetically by name
4. Concatenate: `URL + sorted_param_pairs`
5. Compute HMAC-SHA256 using the **Twilio Auth Token** as the key
6. Base64-encode the result
7. Compare against the `X-Twilio-Signature` header

### Exact compatibility gap

| Aspect | Current implementation | Twilio production requirement |
|---|---|---|
| Input to HMAC | Raw request body bytes | URL + sorted POST parameters |
| HMAC key | Per-business `webhook_signature_secret` | Twilio Auth Token |
| Encoding | Hex digest | Base64 |
| Header name | `X-Voice-Signature` / `X-Twilio-Signature` | `X-Twilio-Signature` ✅ (matches) |
| Content type | JSON body expected | Form-encoded POST parameters |

**The current implementation is incompatible with Twilio's production verification.** The algorithm, key source, and encoding are all different.

### Can the existing abstraction support provider-specific verification?

**Yes.** The `verify_webhook_signature()` function already accepts a `provider: str` parameter. Adding a Twilio-specific branch (`if provider == "twilio"`) that uses URL+params HMAC with base64 encoding is a small, additive, architecturally consistent change. The generic HMAC path remains available for other providers.

---

## 9. RECORDING/TRANSCRIPTION GAP

**Status: NOT IMPLEMENTED (configuration scaffolding only)**

The persistence layer has:
- `CallAgentConfiguration.recording_enabled` (Boolean, default False)
- `CallAgentConfiguration.transcription_enabled` (Boolean, default False)
- `VoiceCallSession.recording_reference` (String(500), nullable)
- `VoiceCallSession.transcript_reference` (String(500), nullable)

What is missing:
- No integration with Twilio Recording API (`/Recordings` resource)
- No integration with Twilio Transcription API
- No media storage adapter to persist audio files
- No mechanism to receive recording/transcription webhooks from Twilio
- No processing pipeline to link recording URLs to session references

This is a **later-phase concern** — not a blocker for the initial real-time voice E2E.

---

## 10. CAMPAIGN SCHEDULING GAP

**Status: Invocation-driven (by design)**

The 14B.2 report explicitly identifies: "Campaign execution is invocation-driven (endpoint / worker call), not a cron scheduler."

- `CampaignExecutionService.process_campaign()` processes all PENDING recipients
- `start_at` gates activation
- No recurring scheduler or cron runner exists

**Required for production campaigns**: A scheduled runner (Celery Beat, cron, or similar) that periodically invokes `process_campaign()` for ACTIVE campaigns. This is a **deployment/operational concern**, not a code gap in the voice system itself.

---

## 11. PRODUCTION CONFIGURATION REQUIREMENTS

### Environment variables required for real E2E

| Variable | Purpose | Current state |
|---|---|---|
| `VOICE_PROVIDER=twilio` | Select Twilio voice provider | Defaults to `mock` |
| `TWILIO_ACCOUNT_SID` | Twilio account identifier | Present in config, missing from .env.example |
| `TWILIO_AUTH_TOKEN` | Twilio auth token (also for webhook verification) | Present in config, missing from .env.example |
| `TWILIO_PHONE_NUMBER` | E.164 phone number for outbound calls | Present in config, missing from .env.example |
| `AI_PROVIDER` | Real AI provider (e.g. `openai`, `gemini`) | Defaults to `mock`; only `stub` resolves |
| `AI_API_KEY` | AI provider API key | Present in config |
| `AI_MODEL` | AI model identifier | Present in config |
| `STT_PROVIDER` | Speech-to-text provider | ❌ Does not exist in config |
| `STT_API_KEY` | STT provider API key | ❌ Does not exist in config |
| `TTS_PROVIDER` | Text-to-speech provider | ❌ Does not exist in config |
| `TTS_API_KEY` | TTS provider API key | ❌ Does not exist in config |
| `PUBLIC_BASE_URL` | Public HTTPS URL for Twilio webhooks | ❌ Does not exist in config |
| `TWILIO_WEBHOOK_SECRET` | Alternative: per-business webhook secret | Exists as DB column, not env var |

### Deployment requirements

| Requirement | Status |
|---|---|
| Public HTTPS endpoint | ❌ Not configured |
| WebSocket support (for Media Streams) | ❌ Not in current ASGI config |
| Twilio phone number provisioned | ❌ Not provisioned |
| Twilio Status Callback URL configured on phone number | ❌ Not configured |
| Twilio Voice URL (TwiML webhook) configured on phone number | ❌ Not configured |
| DNS / TLS certificate | ❌ Not configured |

---

## 12. EXACT BLOCKERS

### CODE GAP blockers

| # | Blocker | Scope | Classification |
|---|---|---|---|
| 1 | No TwiML generation endpoint | Twilio needs TwiML instructions when a call connects | **CODE GAP** |
| 2 | No STT provider adapter | No speech-to-text capability | **CODE GAP** |
| 3 | No TTS provider adapter | No text-to-speech capability | **CODE GAP** |
| 4 | No streaming transport layer | No WebSocket endpoint for Twilio Media Streams | **CODE GAP** |
| 5 | No real AI provider adapter | `StubAIProvider` is a keyword-based discovery stub, not a conversational agent | **CODE GAP** |
| 6 | Twilio webhook signature algorithm mismatch | Current HMAC uses body+hex; Twilio requires URL+params+base64 | **CODE GAP** (small, additive) |

### CONFIGURATION GAP blockers

| # | Blocker | Classification |
|---|---|---|
| 7 | No `PUBLIC_BASE_URL` configuration | **CONFIGURATION GAP** |
| 8 | No STT/TTS environment variables in config.py | **CONFIGURATION GAP** |
| 9 | Twilio credentials missing from .env.example | **CONFIGURATION GAP** |
| 10 | `VOICE_PROVIDER` defaults to `mock` | **CONFIGURATION GAP** |

### DEPLOYMENT GAP blockers

| # | Blocker | Classification |
|---|---|---|
| 11 | No public HTTPS endpoint deployed | **DEPLOYMENT GAP** |
| 12 | No WebSocket support in deployment | **DEPLOYMENT GAP** |
| 13 | No Twilio phone number provisioned | **EXTERNAL PROVIDER DEPENDENCY** |
| 14 | No Twilio Status Callback URL configured on phone number | **EXTERNAL PROVIDER DEPENDENCY** |

### NOT REQUIRED for initial E2E (optional, later phase)

| Item | Classification |
|---|---|
| Recording/transcription integration | NOT REQUIRED for initial E2E |
| Campaign scheduler (cron runner) | NOT REQUIRED for initial E2E |
| Barge-in / interruption handling | NOT REQUIRED for initial E2E (can use `<Gather>` approach) |
| Operator escalation UI | NOT REQUIRED for initial E2E |
| Inbound call handling | NOT REQUIRED for initial E2E (outbound-only first) |

---

## 13. RECOMMENDED NEXT IMPLEMENTATION BLOCK

The smallest production-E2E implementation block, preserving all existing architecture:

### Phase 14C — Real-Time Voice Transport (proposed scope)

**Block 1: TwiML generation + simpler turn model** (smallest viable E2E)
- TwiML endpoint: `GET/POST /api/v1/webhooks/voice/twilio/twiml/{call_id}` → returns `<Gather input="speech" action="...">` + `<Say>` verbs
- This lets Twilio handle STT natively via `<Gather>` and POST transcripts back
- Agent reply text → `<Say>` verb in TwiML response
- Eliminates the need for a separate STT provider and WebSocket transport initially

**Block 2: Twilio webhook security fix** (small, additive)
- Add `verify_twilio_signature(url, params, auth_token, signature)` to `webhook_service.py`
- Branch in `verify_webhook_signature()` for `provider == "twilio"`
- Use Twilio Auth Token from settings as the HMAC key

**Block 3: Real AI provider adapter**
- `AIProvider` concrete implementation (OpenAI, Gemini, or Anthropic)
- Configuration: `AI_PROVIDER=openai`, `AI_API_KEY`, `AI_MODEL`
- The Call Agent runtime needs zero changes — it already uses `AIProvider.structured_output()`

**Block 4: Configuration surface**
- Add `PUBLIC_BASE_URL` to `config.py` and `.env.example`
- Add Twilio-specific env vars to `.env.example`
- Wire `callback_url` on call initiation to `PUBLIC_BASE_URL + /api/v1/webhooks/voice/twilio/twiml/...`

**Block 5 (later): Streaming transport** (if `<Gather>` latency is unacceptable)
- WebSocket endpoint for Twilio Media Streams
- STT provider adapter (Deepgram recommended for real-time)
- TTS provider adapter (ElevenLabs or Google Cloud TTS)
- `StreamingTurnOrchestrator` wrapping the existing Call Agent

This phasing ensures the **fastest path to a real voice conversation** (Blocks 1-4) while keeping the streaming architecture available for later refinement (Block 5).

---

## 14. TESTS RUN

No tests were run as part of this assessment. This is a **read-only inspection** task.

The authoritative test results remain those from the 14B.2 verification:
- 14B targeted suite: **180 passed** (1212.47s)
- Full backend regression: **781 passed, 0 failures** (2645.38s)
- Fresh migration 012 verification: **PASS**
- 14A regression: **CONFIRMED**

---

## 15. TEST RESULTS

N/A — no code changes were made. See Section 14.

---

## 16. FILES CHANGED

**None.** This assessment is a read-only inspection. No files were created, modified, or deleted.

### Files inspected (evidence sources)

| File | Lines | Role |
|---|---|---|
| `backend/app/adapters/voice/base.py` | 75 | VoiceProvider ABC |
| `backend/app/adapters/voice/twilio.py` | 115 | Twilio voice adapter |
| `backend/app/adapters/ai/base.py` | 79 | AIProvider ABC |
| `backend/app/adapters/ai/stub.py` | 136 | Stub AI provider |
| `backend/app/adapters/__init__.py` | 162 | Provider factory |
| `backend/app/domain/voice/models.py` | 518 | Voice domain models |
| `backend/app/domain/voice/service.py` | 856 | Call lifecycle service |
| `backend/app/domain/voice/provider_service.py` | 434 | Provider orchestration |
| `backend/app/domain/voice/webhook_service.py` | 323 | Webhook processing |
| `backend/app/domain/voice/agent.py` | 648 | Call Agent runtime |
| `backend/app/domain/voice/campaign_execution.py` | 614 | Campaign execution |
| `backend/app/domain/voice/outbox_integration.py` | 160 | Outbox integration |
| `backend/app/domain/voice/schemas.py` | 237 | API schemas |
| `backend/app/domain/voice/repository.py` | 461 | Repositories |
| `backend/app/domain/common/enums.py` | 923 | State machines + enums |
| `backend/app/api/v1/voice.py` | 683 | API endpoints |
| `backend/app/api/router.py` | 63 | Router registration |
| `backend/app/config.py` | 131 | Application settings |
| `.env.example` | 52 | Environment template |
| `docs/superpowers/specs/2026-09-19-phase14b2-voice-runtime-implementation-report.md` | 326 | 14B.2 implementation report |

---

## CONCLUSION

The FIELDed voice system has a **production-quality governed decision layer** but **no audio transport layer**. A real production voice conversation requires six code gaps and four configuration/deployment gaps to be closed. The recommended approach is a two-phase strategy:

1. **Phase 14C.1** (Blocks 1-4): Use TwiML `<Gather>` + `<Say>` for the simplest viable E2E. This lets Twilio handle STT, the existing Call Agent processes transcripts, and TwiML `<Say>` renders agent replies as audio. Estimated scope: ~4-6 new files, ~1500-2000 lines, no redesign of existing code.

2. **Phase 14C.2** (Block 5): Add streaming transport (WebSocket + STT/TTS providers) if `<Gather>` latency is unacceptable for production quality. This is a larger effort but can be deferred until the simpler approach is validated.

**14B.2 remains CLOSED.** This assessment establishes the gap; implementation belongs to a new phase.
