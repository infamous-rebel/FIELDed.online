# Phase 14C.1 — Real Voice E2E Implementation Report

**Date:** 2026-09-20  
**Phase:** 14C.1 — First Real Outbound Voice Call (TwiML / Gather / Say)  
**Status:** COMPLETE  
**Test Result:** 22/22 PASSED  

---

## Executive Summary

Phase 14C.1 successfully implements the smallest viable real outbound voice conversation using Twilio's `<Gather input="speech">` + `<Say>` approach. The existing governed Call Agent architecture (`VoiceCallAgent`) remains the decision layer; the new work is a transport/integration layer that bridges live telephone audio to the agent.

**Key Achievement:** The system can now initiate a real outbound phone call via Twilio, greet the caller with TTS, collect speech via STT, pass the transcript to the governed agent, and respond with the agent's reply — all while maintaining tenant isolation, signature verification, and the AI-proposal-validated-by-deterministic-rules pattern.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Twilio Cloud                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐  │
│  │ Outbound Call│───▶│ TwiML Webhook│───▶│ Gather Callback      │  │
│  │ (REST API)   │    │ (GET TwiML)  │    │ (POST transcript)    │  │
│  └──────────────┘    └──────────────┘    └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
         │                       │                        │
         ▼                       ▼                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FIELDed Backend (New in 14C.1)                    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ TwiML Transport Layer (app/api/v1/voice.py)                  │  │
│  │  • POST /webhooks/voice/twilio/twiml/{call_id}              │  │
│  │  • POST /webhooks/voice/twilio/gather/{call_id}             │  │
│  │  • POST /webhooks/voice/twilio/status/{call_id}             │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                              │                                       │
│                              ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ TwiML Generation (app/domain/voice/twiml.py)                 │  │
│  │  • gather_response() — <Say> + <Gather input="speech">      │  │
│  │  • say_and_hangup_response() — <Say> + <Hangup/>            │  │
│  │  • hangup_response() — <Hangup/>                            │  │
│  │  • retry_gather_response() — deterministic retry prompt     │  │
│  │  • error_response() — error message + hangup                │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                              │                                       │
│                              ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ Security (app/adapters/voice/twilio_security.py)             │  │
│  │  • verify_twilio_signature() — HMAC-SHA256 validation       │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                              │                                       │
│                              ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ AI Provider (app/adapters/ai/openai_provider.py)             │  │
│  │  • OpenAIProvider — Chat Completions API via httpx          │  │
│  │  • structured_output() — JSON schema enforcement            │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                              │                                       │
│                              ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ Existing Governed Call Agent (app/domain/voice/agent.py)     │  │
│  │  • VoiceCallAgent.begin() — initialize session              │  │
│  │  • VoiceCallAgent.handle_turn() — process transcript        │  │
│  │  • AI proposal → validation → deterministic execution       │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Files Created

| File | Purpose | Lines |
|------|---------|-------|
| `app/adapters/voice/twilio_security.py` | Twilio request signature verification | ~60 |
| `app/domain/voice/twiml.py` | TwiML XML generation (no SDK dependency) | ~120 |
| `app/adapters/ai/openai_provider.py` | OpenAI Chat Completions adapter via httpx | ~160 |
| `tests/integration/test_phase14c1_real_voice_e2e.py` | Targeted integration tests | ~560 |

## Files Modified

| File | Changes |
|------|---------|
| `app/config.py` | Added `public_base_url: str` for Twilio webhook URLs |
| `.env.example` | Added voice/Twilio/AI configuration variables |
| `app/adapters/__init__.py` | Added `openai` to AI provider resolver |
| `app/domain/voice/provider_service.py` | Added `twiml_url` parameter to `initiate_call()` |
| `app/api/v1/voice.py` | Added 3 TwiML webhook endpoints + helper functions |

---

## Implementation Details

### 1. Twilio Signature Verification

**File:** `app/adapters/voice/twilio_security.py`

Implements Twilio's official request validation algorithm:
1. Take the full URL (including query string)
2. Sort all POST parameters alphabetically by key
3. Append the sorted key=value pairs to the URL
4. HMAC-SHA256 the result with the auth token
5. Base64-encode the hash
6. Compare with the `X-Twilio-Signature` header using constant-time comparison

```python
def verify_twilio_signature(
    url: str,
    params: dict[str, str] | list[tuple[str, str]],
    auth_token: str,
    signature: str,
) -> bool:
```

**Security Properties:**
- Fail-closed: missing token, missing signature, or mismatch → rejected
- Constant-time comparison via `hmac.compare_digest()`
- No timing side-channels

### 2. TwiML Generation

**File:** `app/domain/voice/twiml.py`

Generates TwiML XML using `xml.etree.ElementTree` (no external Twilio SDK dependency).

| Function | Purpose |
|----------|---------|
| `gather_response()` | `<Say>` + `<Gather input="speech">` for conversational turns |
| `say_and_hangup_response()` | `<Say>` + `<Hangup/>` for final messages |
| `hangup_response()` | Bare `<Hangup/>` for terminal states |
| `retry_gather_response()` | Deterministic retry prompt ("I didn't catch that...") |
| `error_response()` | Error message + hangup |

**Design Decisions:**
- No external SDK: raw XML construction matches project's provider-agnostic pattern
- Speech timeout: `"auto"` (Twilio default)
- Language/voice: optional parameters for future i18n

### 3. OpenAI AI Provider Adapter

**File:** `app/adapters/ai/openai_provider.py`

Implements the `AIProvider` interface using the OpenAI Chat Completions API via `httpx` (matching the project's existing HTTP client pattern — no additional SDK dependency).

**Key Features:**
- `complete()` — text completion
- `structured_output()` — JSON schema enforcement via `response_format={"type": "json_object"}`
- Error handling: timeout, HTTP errors, non-JSON responses
- Provider-agnostic: implements the same ABC as the stub

**AI Authority Limitation Preserved:**
The OpenAI provider only PROPOSES actions. Every proposal is validated by `VoiceCallAgent._validate_proposal()` against the Business Brain's allowed actions before execution.

### 4. TwiML Webhook Endpoints

**File:** `app/api/v1/voice.py`

Three new public endpoints for Twilio callbacks:

#### 4.1 Initial TwiML Webhook
```
POST /webhooks/voice/twilio/twiml/{call_id}
```

**Flow:**
1. Verify Twilio signature (fail-closed for `twilio` provider)
2. Resolve call by `CallSid` (provider_reference) with cross-check against URL `call_id`
3. If call is terminal → `<Hangup/>`
4. Drive call to CONNECTED if still in INITIATING/RINGING (timing issue: TwiML webhook and status callback are independent)
5. Start agent session via `agent.begin()` if not already active (idempotent)
6. Generate deterministic greeting (not LLM-generated)
7. Return `<Say>` + `<Gather input="speech">` with Gather callback URL

#### 4.2 Gather Callback
```
POST /webhooks/voice/twilio/gather/{call_id}
```

**Flow:**
1. Verify Twilio signature
2. Resolve call by `CallSid`
3. If terminal → `<Hangup/>`
4. If empty speech → deterministic retry (no LLM call)
5. Pass transcript to `agent.handle_turn(call, speech_result)`
6. If agent returns `END_CALL` or `REQUEST_HUMAN` → `<Say>` + `<Hangup/>`
7. Otherwise → `<Say>` reply + `<Gather>` for next turn

#### 4.3 Status Callback
```
POST /webhooks/voice/twilio/status/{call_id}
```

**Flow:**
1. Verify Twilio signature
2. Parse form-encoded data (`CallSid`, `CallStatus`)
3. Feed into existing `VoiceWebhookService.process_event()` pipeline
4. Preserve existing webhook behavior (no duplication)

### 5. Call Initiation with TwiML URL

**File:** `app/domain/voice/provider_service.py`

Modified `initiate_call()` to accept an optional `twiml_url` parameter:

```python
async def initiate_call(
    self, call, *, actor_id=None, twiml_url=None
) -> VoiceCall:
    request = VoiceCallRequest(
        to=call.to_number,
        from_number=call.from_number,
        callback_url=twiml_url,  # Twilio fetches TwiML from this URL
        metadata={...},
    )
```

When `callback_url` is provided, Twilio makes an HTTP request to that URL to fetch TwiML instructions instead of using a hardcoded `<Say>` or `<Gather>`.

### 6. Configuration

**File:** `app/config.py`

Added `public_base_url: str` for constructing public webhook URLs:

```python
# Phase 14C — Public base URL for Twilio webhooks
public_base_url: str = ""
```

**File:** `.env.example`

Added voice/Twilio/AI configuration:

```bash
# Voice / Twilio (Phase 14C)
VOICE_PROVIDER=mock
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=
PUBLIC_BASE_URL=

# AI Provider (Phase 14C)
AI_PROVIDER=mock
AI_API_KEY=
AI_MODEL=
```

---

## Security Model

### Tenant Isolation

All TwiML webhook endpoints are **public** (no JWT auth) because Twilio callbacks are system-authority events. Tenant isolation is preserved through:

1. **Signature Verification:** Only Twilio can generate valid `X-Twilio-Signature` headers
2. **Call Resolution by CallSid:** The `CallSid` is a Twilio-generated identifier that maps to a specific call
3. **Cross-Check:** The URL `call_id` must match the resolved call's actual `id` (fail-closed)
4. **Signed URLs:** The `call_id` is embedded in the signed URL, so only Twilio can construct valid callback URLs

### AI Authority Limitation

The existing governed Call Agent pattern is preserved:

```
AI proposal → structured schema → validation → deterministic rules → authorization → execution → audit
```

- The OpenAI provider only PROPOSES actions
- `VoiceCallAgent._validate_proposal()` validates against Business Brain's `allowed_actions`
- State mutations go through `VoiceCallLifecycleService` (deterministic state machine)
- All turns are audited

### Webhook Security

- **Fail-closed:** Missing auth token, missing signature, or mismatch → rejected
- **Constant-time comparison:** `hmac.compare_digest()` prevents timing attacks
- **URL reconstruction:** Public URL is reconstructed from `PUBLIC_BASE_URL` + request path (not trusted from headers)

---

## Test Coverage

**File:** `tests/integration/test_phase14c1_real_voice_e2e.py`  
**Result:** 22/22 PASSED  

| Test Class | Tests | Coverage |
|------------|-------|----------|
| `TestTwilioSignatureVerification` | 6 | Valid, invalid, missing, tampered params, tampered URL |
| `TestTwiMLGeneration` | 5 | Valid XML, Gather, Say, Hangup, retry, error |
| `TestConversationalAIProvider` | 2 | Schema satisfaction, provider name |
| `TestTwiMLWebhookEndpoint` | 3 | Initial Gather, terminal Hangup, nonexistent call |
| `TestGatherCallbackEndpoint` | 3 | Transcript processing, empty speech retry, terminal hangup |
| `TestCrossTenantIsolation` | 1 | Wrong CallSid rejected |
| `TestIdempotency` | 1 | Duplicate TwiML doesn't create duplicate sessions |
| `TestTwilioURLConstruction` | 1 | twiml_url passed to provider |

**Test Infrastructure:**
- `StubVoiceProvider` — deterministic call initiation
- `StubConversationalAI` — returns valid `AGENT_DECISION_SCHEMA` responses
- Real PostgreSQL 16 (per-test schema recreate + rollback)
- `monkeypatch` for AI provider resolver injection

---

## Timing Issues Resolved

### TwiML Webhook vs Status Callback

**Problem:** Twilio's TwiML request and status callback are independent HTTP requests that may arrive in any order. The call might still be in INITIATING/RINGING when the TwiML webhook arrives.

**Solution:** The TwiML endpoint drives the call to CONNECTED if it's still in INITIATING/RINGING state:

```python
current_status = CallStatus(call.status)
if current_status in (CallStatus.INITIATING, CallStatus.RINGING):
    if current_status is CallStatus.INITIATING:
        call = await lifecycle.mark_ringing(call, reason="twilio twiml webhook")
    call = await lifecycle.mark_connected(call, reason="twilio twiml webhook")
```

This is safe because the lifecycle service validates state transitions.

### Session Idempotency

**Problem:** Twilio may retry the TwiML webhook, potentially creating duplicate agent sessions.

**Solution:** The TwiML endpoint checks for an existing active session before calling `agent.begin()`:

```python
active_session = await session_repo.get_active_for_call(call.id)
if active_session is None:
    active_session = await agent.begin(call)
```

---

## Configuration for Production

To enable real voice calls with Twilio:

1. **Set environment variables:**
   ```bash
   VOICE_PROVIDER=twilio
   TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_AUTH_TOKEN=your_auth_token
   TWILIO_PHONE_NUMBER=+1234567890
   PUBLIC_BASE_URL=https://api.fielded.com
   
   AI_PROVIDER=openai
   AI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   AI_MODEL=gpt-4o-mini
   ```

2. **Configure Business Brain:**
   - Set `communication_config.voice_agent.allowed_actions` to uppercase enum values: `["COLLECT_INFORMATION", "END_CALL", "REQUEST_HUMAN"]`
   - Set `max_turns` (default: 10)
   - Set `escalation_triggers`

3. **Configure Call Agent:**
   - Enable `transactional_calling_enabled` or `marketing_calling_enabled`
   - Set `default_from_number`

4. **Deploy with public HTTPS endpoint:**
   - Twilio requires HTTPS for webhook URLs
   - `PUBLIC_BASE_URL` must be publicly accessible

---

## What's NOT in Phase 14C.1

The following are explicitly out of scope for this phase:

- **WebSockets / Media Streams:** No real-time audio streaming
- **Deepgram / ElevenLabs:** No external STT/TTS providers
- **Voice Activity Detection (VAD):** No barge-in detection
- **Streaming TTS:** Twilio's `<Say>` is non-streaming
- **Call recording:** No audio recording
- **Multi-language support:** English-only (Twilio default)
- **DTMF input:** Only speech input via `<Gather input="speech">`

These features are candidates for Phase 14C.2 (streaming voice).

---

## Backward Compatibility

All existing 14B tests remain passing. The changes are additive:

- Existing webhook endpoints unchanged
- Existing `VoiceCallAgent` API unchanged
- Existing `VoiceProvider` interface unchanged
- New endpoints are additive (no breaking changes)

---

## Next Steps

### Phase 14C.2 — Streaming Voice (Future)

- WebSocket-based real-time audio streaming
- Twilio Media Streams or Twilio Voice SDK
- External STT (Deepgram, AssemblyAI)
- External TTS (ElevenLabs, Azure)
- Voice Activity Detection (VAD) for barge-in
- Low-latency conversational AI

### Immediate Production Readiness

Before deploying to production:

1. **Load testing:** Verify TwiML endpoint latency under load
2. **Error handling:** Test Twilio timeout/retry behavior
3. **Monitoring:** Add metrics for TwiML webhook latency, error rates
4. **Logging:** Verify structured logging with correlation IDs
5. **Security audit:** Review signature verification implementation
6. **Twilio webhook registration:** Register webhook URLs in Twilio Console

---

## Conclusion

Phase 14C.1 successfully implements the first real end-to-end voice call using Twilio's `<Gather>` + `<Say>` approach. The implementation:

- ✅ Preserves the governed Call Agent architecture
- ✅ Maintains tenant isolation and signature verification
- ✅ Follows the AI-proposal-validated-by-deterministic-rules pattern
- ✅ Uses provider-agnostic adapters (no SDK dependencies)
- ✅ Includes comprehensive test coverage (22/22 tests passing)
- ✅ Resolves timing issues between TwiML webhook and status callback
- ✅ Provides a clear path to Phase 14C.2 (streaming voice)

The system is now ready for real outbound voice calls with Twilio, pending production configuration and deployment.
