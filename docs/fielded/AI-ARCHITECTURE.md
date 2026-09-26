# FIELDed — AI Architecture

**Status**: Current State Baseline  
**Last Updated**: 2026-09-24

---

## Overview

FIELDed uses a **provider-agnostic AI architecture** where all AI operations flow through abstract provider interfaces. This allows switching between AI providers (Groq, OpenAI, etc.) without modifying domain logic, and supports workload-specific provider configuration.

---

## Provider Abstraction

### AIProvider Interface

All AI operations use the `AIProvider` abstract base class:

```python
class AIProvider(ABC):
    @abstractmethod
    async def complete(self, messages: list[dict], **kwargs) -> str:
        """Generate completion from messages."""
    
    @abstractmethod
    async def complete_structured(self, messages: list[dict], schema: dict, **kwargs) -> dict:
        """Generate structured completion conforming to schema."""
```

### Concrete Providers

| Provider | Class | API | Status |
|----------|-------|-----|--------|
| Groq | `GroqProvider` | Groq API (OpenAI-compatible) | Implemented |
| OpenAI | `OpenAIProvider` | OpenAI API | Implemented |
| Mock/Stub | `StubAIProvider` | Deterministic stub | Implemented |

---

## Provider Configuration

### Global Configuration

Global AI configuration via environment variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `AI_PROVIDER` | Provider name (groq, openai, mock) | mock |
| `AI_API_KEY` | API key for provider | "" |
| `AI_MODEL` | Model name | "" |
| `AI_BASE_URL` | Base URL (for OpenAI-compatible providers) | "" |

### Workload-Specific Configuration

Different AI workloads can use different providers/keys:

| Workload | API Key Variable | Base URL Variable | Fallback |
|----------|-----------------|-------------------|----------|
| Discovery | `DISCOVERY_AI_API_KEY` | `DISCOVERY_AI_BASE_URL` | Global `AI_API_KEY` |
| Brain | `BRAIN_AI_API_KEY` | `BRAIN_AI_BASE_URL` | Global `AI_API_KEY` |
| Call Agent | `CALL_AGENT_AI_API_KEY` | `CALL_AGENT_AI_BASE_URL` | Global `AI_API_KEY` |

### Provider Resolution

Providers are resolved through the `ProviderFactory`:

```python
# Global AI provider
ai_provider = _resolve_ai_provider(settings)

# Workload-specific providers
discovery_provider = _resolve_discovery_ai_provider(settings)
brain_provider = _resolve_brain_ai_provider(settings)
call_agent_provider = _resolve_call_agent_ai_provider(settings)
```

Resolution logic:
1. Check workload-specific API key/base URL
2. If not set, fall back to global AI_API_KEY/AI_BASE_URL
3. Build provider based on `AI_PROVIDER` setting

---

## Groq Provider

### Configuration

```python
class GroqProvider(AIProvider):
    def __init__(self, api_key: str, model: str, api_base: str | None = None):
        # Uses OpenAI-compatible API
        self.client = OpenAI(
            api_key=api_key,
            base_url=api_base or "https://api.groq.com/openai/v1",
        )
        self.model = model or "llama-3.3-70b-versatile"
```

### Supported Models

- `llama-3.3-70b-versatile` (default)
- `llama-3.1-8b-instant`
- `mixtral-8x7b-32768`
- And other Groq models

### API Compatibility

Groq uses the **OpenAI-compatible API**, so the Groq provider is essentially an OpenAI client pointing to Groq's endpoint.

---

## OpenAI Provider

### Configuration

```python
class OpenAIProvider(AIProvider):
    def __init__(self, api_key: str, model: str, api_base: str | None = None):
        self.client = OpenAI(api_key=api_key, base_url=api_base)
        self.model = model or "gpt-4o-mini"
```

### Supported Models

- `gpt-4o-mini` (default)
- `gpt-4o`
- `gpt-4-turbo`
- And other OpenAI models

---

## Stub Provider

### Purpose

The `StubAIProvider` provides deterministic responses for testing and development:

```python
class StubAIProvider(AIProvider):
    async def complete(self, messages: list[dict], **kwargs) -> str:
        return "Stub AI response"
    
    async def complete_structured(self, messages: list[dict], schema: dict, **kwargs) -> dict:
        return {"stub": True}
```

### Use Cases

- Unit testing
- Integration testing
- Development without API keys
- CI/CD pipelines

---

## AI Workloads

### 1. Discovery Workload

**Purpose**: Interpret natural language search queries

**Input**: User search text
**Output**: Structured search intent (category, keywords, location, etc.)

**Flow**:
1. User enters search query
2. Discovery interpreter calls AI provider
3. AI interprets query and extracts intent
4. Structured intent used to match businesses

**Configuration**:
- Uses `DISCOVERY_AI_API_KEY` if set
- Falls back to `AI_API_KEY`

**Status**: Implemented, verified with Groq/OpenAI

### 2. Brain Workload

**Purpose**: Business Brain conversational AI

**Input**: Owner messages in brain conversations
**Output**: Brain responses, proposal generation

**Flow**:
1. Owner sends message in brain conversation
2. Brain service calls AI provider
3. AI generates response
4. AI may generate structured proposals
5. Proposals presented to owner for approval

**Configuration**:
- Uses `BRAIN_AI_API_KEY` if set
- Falls back to `AI_API_KEY`

**Note**: The Brain evaluator is currently **entirely deterministic** and does not call AI. The AI provider is available for future Brain workloads (rule drafting, intent classification).

**Status**: Implemented, deterministic evaluator verified

### 3. Call Agent Workload

**Purpose**: AI-powered voice call agent

**Input**: Call context, conversation history
**Output**: Agent actions (continue, collect information, request human, end call)

**Flow**:
1. Call initiated
2. Call agent calls AI provider with conversation context
3. AI generates agent action
4. Action validated against governance rules
5. Action executed (continue conversation, collect info, escalate)

**Configuration**:
- Uses `CALL_AGENT_AI_API_KEY` if set
- Falls back to `AI_API_KEY`

**Status**: Implemented, verified with Groq/OpenAI

---

## AI Governance

### AI Intelligence vs Business Authority

**AI Can**:
- Interpret customer enquiries
- Extract business knowledge from conversations
- Propose new services, pricing rules, policies
- Suggest availability and qualification rules
- Generate reasoning summaries
- Provide confidence scores
- Recommend improvements

**AI Cannot**:
- Set or change prices without business rule validation
- Determine availability without checking deterministic constraints
- Override business policies
- Authorize customers or grant permissions
- Change booking/transaction state directly
- Determine review eligibility
- Silently mutate production Brain state

### Governance Flow

```
AI proposal → structured schema → validation → deterministic rules → authorization → execution → audit
```

All AI proposals flow through:
1. **Structured schema**: AI output conforms to defined schema
2. **Validation**: Output validated against business rules
3. **Deterministic rules**: Critical decisions use deterministic logic
4. **Authorization**: Owner approval required for Brain changes
5. **Execution**: Approved changes executed through domain services
6. **Audit**: All actions logged with audit events

---

## Provider Selection

### When to Use Groq

- **Cost-effective**: Groq is generally cheaper than OpenAI
- **Fast inference**: Groq offers very fast inference times
- **OpenAI-compatible**: Easy migration from OpenAI
- **Good for**: Discovery, Brain conversations, Call Agent

### When to Use OpenAI

- **Advanced models**: GPT-4o, GPT-4-turbo
- **Complex reasoning**: Better for complex tasks
- **Established ecosystem**: Wide model selection
- **Good for**: Complex Brain proposals, advanced discovery

### When to Use Mock/Stub

- **Testing**: Unit and integration tests
- **Development**: Development without API costs
- **CI/CD**: CI/CD pipelines without API keys
- **Good for**: All testing and development

---

## Secret Management

### Secret Names (Never Values)

| Secret Name | Purpose | Used By |
|-------------|---------|---------|
| `AI_API_KEY` | Global AI provider API key | All workloads (fallback) |
| `DISCOVERY_AI_API_KEY` | Discovery workload API key | Discovery interpreter |
| `BRAIN_AI_API_KEY` | Brain workload API key | Brain conversations |
| `CALL_AGENT_AI_API_KEY` | Call Agent workload API key | Voice call agent |
| `AI_BASE_URL` | Global AI provider base URL | All workloads (fallback) |
| `DISCOVERY_AI_BASE_URL` | Discovery workload base URL | Discovery interpreter |
| `BRAIN_AI_BASE_URL` | Brain workload base URL | Brain conversations |
| `CALL_AGENT_AI_BASE_URL` | Call Agent workload base URL | Voice call agent |
| `AI_MODEL` | AI model name | All workloads |

### Secret Storage

- **Development**: `.env` file (never committed)
- **Production**: Environment variables (Cloudflare Workers, Cloud Run, etc.)
- **CI/CD**: GitHub Secrets

### Secret Rotation

Secrets can be rotated by:
1. Updating environment variable
2. Restarting application
3. New requests use new secret

---

## Model Configuration

### Model Selection

Model is configured via `AI_MODEL` environment variable:

| Provider | Default Model | Alternative Models |
|----------|---------------|-------------------|
| Groq | `llama-3.3-70b-versatile` | `llama-3.1-8b-instant`, `mixtral-8x7b-32768` |
| OpenAI | `gpt-4o-mini` | `gpt-4o`, `gpt-4-turbo` |

### Model Fallback

If `AI_MODEL` is not set:
- Groq: Uses `llama-3.3-70b-versatile`
- OpenAI: Uses `gpt-4o-mini`

---

## Error Handling

### AI Provider Errors

AI provider errors are handled at multiple levels:

1. **Provider Level**: Provider raises exception on API error
2. **Service Level**: Domain service catches exception and handles gracefully
3. **API Level**: API returns appropriate error response
4. **Frontend Level**: Frontend displays error message to user

### Fallback Behavior

If AI provider is unavailable:
- Discovery: Falls back to text-based search (no AI interpretation)
- Brain: Brain conversations unavailable (deterministic evaluator still works)
- Call Agent: Call agent unavailable (calls can still be made manually)

---

## Testing

### Unit Tests

- `test_workload_ai_resolvers.py`: Tests AI provider resolvers
- `test_discovery_interpreter.py`: Tests discovery interpreter with mock AI
- `test_phase09_brain_runtime.py`: Tests Brain runtime with mock AI

### Integration Tests

- `test_brain_api.py`: Tests Brain API with mock AI
- `test_discovery.py`: Tests discovery with mock AI

### Test Configuration

Tests use the `StubAIProvider` by default:

```python
# In test configuration
AI_PROVIDER=mock
```

---

## Architecture Extension Points

### Adding New AI Provider

1. Create provider class implementing `AIProvider` interface
2. Add provider to `_build_ai_provider()` in `app/adapters/__init__.py`
3. Add provider configuration to `Settings` class
4. Add tests for new provider

### Adding New AI Workload

1. Define workload purpose and input/output
2. Add workload-specific API key/base URL settings
3. Add workload-specific provider resolver
4. Implement workload logic using provider
5. Add tests for new workload

### Adding New AI Capabilities

1. Define capability purpose and input/output
2. Add capability to appropriate domain service
3. Use AI provider for capability
4. Ensure governance flow is followed
5. Add tests for new capability

---

## Current Limitations

1. **No Streaming**: AI completions are not streamed (full response returned at once)
2. **No Caching**: AI responses are not cached
3. **No Rate Limiting**: AI provider calls are not rate-limited by FIELDed
4. **No Cost Tracking**: AI usage costs are not tracked
5. **No Fallback Chain**: No automatic fallback between providers

### Future Enhancements

1. **Streaming**: Add streaming support for better UX
2. **Caching**: Cache AI responses for identical inputs
3. **Rate Limiting**: Rate-limit AI provider calls
4. **Cost Tracking**: Track AI usage costs per workload
5. **Fallback Chain**: Automatic fallback to backup provider

---

## Summary

FIELDed's AI architecture provides:

- **Provider-agnostic interface**: Switch between Groq, OpenAI, or other providers
- **Workload-specific configuration**: Different keys/models for different workloads
- **Governance flow**: AI proposes, deterministic rules authorize
- **Fallback behavior**: Graceful degradation when AI unavailable
- **Testing support**: Mock/stub providers for testing

The architecture embodies FIELDed's core principle: **AI intelligence != business authority**.
