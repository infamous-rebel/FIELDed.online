# FIELDed — AI Architecture

## Core Principle

**AI intelligence ≠ business authority.**

AI may interpret, classify, extract, summarize, recommend, or draft. AI must NOT independently control price, availability, policy, authorization, booking state, review eligibility, business capability, permissions, or transaction state.

## Execution Pattern

```
AI proposal
    → structured schema
    → validation
    → deterministic business/domain rules
    → authorization
    → execution
    → audit
```

Never reverse this architecture.

## AI Agents

### Discovery AI
Understands customer intent from natural language. Converts plain English into structured SearchRequest objects. Must NOT invent business capabilities.

### Business Assistant
Works within a Business Brain to help configure operational rules, pricing, policies.

### Enquiry Agent
Helps interpret and qualify incoming customer enquiries.

### Quote Assistant
Drafts quote explanations and summarizes customer information.

### Communication Assistant
Drafts customer-facing responses within business policy bounds.

### Scheduling Agent (future)
Assists with scheduling proposals based on availability rules.

## Provider Agnostism

All AI interactions go through the `AIProvider` abstract base class:
- `complete()` — text generation
- `structured_output()` — schema-constrained generation

Concrete implementations can wrap Gemini, Groq, OpenAI, or any other provider. The core domain never calls a specific provider directly.

## Guardrails

- AI outputs are always validated against schemas
- AI never directly modifies database state
- AI never determines pricing authority
- AI never overrides business rules
- All AI interactions are logged for audit
- Prompt injection defenses required
- Hallucinated services/prices must be caught by deterministic validation
