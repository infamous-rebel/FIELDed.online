# FIELDed — AI Governance

> **Status**: SPECIFIED BUT NOT IMPLEMENTED  
> **Phase**: Architecture + Specification Only  
> **Last Updated**: 2026-09-19

---

## Core Principle

**AI intelligence ≠ business authority.**

AI may interpret, classify, extract, summarize, recommend, or draft. AI must NOT independently control price, availability, policy, authorization, booking state, review eligibility, business capability, permissions, or transaction state.

This document extends [docs/ai-architecture.md](ai-architecture.md) with precise governance specifications.

---

## 1. AI Authority Levels

Every AI interaction operates at one of four authority levels:

| Level | Code | Meaning | Example |
|---|---|---|---|
| **INFORMATIONAL** | `L1` | AI provides information that is displayed without restriction | Displaying search results, summarizing enquiry history |
| **PROPOSAL** | `L2` | AI generates a proposal that requires validation before use | Proposing a Brain rule, drafting a quote explanation |
| **REQUIRES_APPROVAL** | `L3` | AI generates a proposal that requires human approval before any effect | Proposing pricing changes, policy modifications |
| **FORBIDDEN** | `L4` | AI must not perform this action under any circumstances | Activating Brain versions, authorizing users, changing transaction state |

### Level Enforcement

```
L1 (INFORMATIONAL)
    → Display to user
    → Log for audit
    → No validation required (but logged)

L2 (PROPOSAL)
    → Schema validation
    → Semantic validation
    → Conflict detection
    → Display to user for review
    → User accepts/modifies/rejects
    → Log for audit

L3 (REQUIRES_APPROVAL)
    → Schema validation
    → Semantic validation
    → Conflict detection
    → Display to user for review
    → User accepts/modifies/rejects
    → Approval workflow (per approval policy)
    → Log for audit

L4 (FORBIDDEN)
    → Hard block at architecture level
    → No AI code path may reach this action
    → Attempted L4 actions are logged as security events
```

---

## 2. Permitted AI Capabilities

| Capability | Authority Level | Description | Constraints |
|---|---|---|---|
| **Interpret** | L1 | Understand customer natural language input | Must produce structured output validated against schema |
| **Extract** | L1 | Pull structured data from unstructured text | Extracted data validated against field types |
| **Classify** | L1 | Categorize enquiries, services, intents | Classification must map to existing ServiceCategory or defined taxonomy |
| **Summarize** | L1 | Condense conversation history, enquiry details | Summary is informational only — not authoritative |
| **Ask Clarification** | L1 | Generate clarification questions for customers | Questions bounded by Qualification classification (D) |
| **Recommend** | L2 | Suggest services, time slots, approaches | Recommendations based on deterministic data (ServiceOffers, availability) |
| **Draft** | L2 | Create message drafts, quote explanations | Drafts require business member review before sending |
| **Propose** | L3 | Suggest Brain rule changes, pricing adjustments | Proposals require validation + human approval |
| **Escalate** | L1 | Flag situations requiring human intervention | Escalation triggers are deterministic; AI suggests, system routes |

### Capability Boundaries

Each capability has explicit boundaries:

| Capability | CAN | CANNOT |
|---|---|---|
| Interpret | Parse intent, extract keywords, identify service category | Determine pricing, guarantee service availability |
| Extract | Pull names, dates, descriptions from text | Create or modify database records |
| Classify | Map to existing categories | Invent new categories or services |
| Summarize | Condense existing information | Add new information or make inferences beyond source |
| Ask Clarification | Generate relevant questions | Demand information not in Qualification rules |
| Recommend | Suggest from existing data | Guarantee availability or pricing |
| Draft | Create text within policy bounds | Send messages without human review |
| Propose | Generate structured rule proposals | Activate rules or modify Brain state |
| Escalate | Flag issues for human review | Make the human decision |

---

## 3. Prohibited AI Authority

The following actions are **FORBIDDEN** (L4) for AI under all circumstances:

| Prohibited Action | Reason | Architecture Enforcement |
|---|---|---|
| **Set or change prices** | Pricing is deterministic business authority | AI proposes → schema validates → human approves → Brain stores |
| **Determine availability** | Availability is a deterministic constraint | AI suggests → calendar adapter verifies → state machine confirms |
| **Authorize customers** | Authorization is identity-based, server-side | JWT + membership + permissions — no AI involvement |
| **Override business policies** | Policies are governed configuration | Brain stores policies → decision service evaluates → AI cannot bypass |
| **Change booking state** | State machines are authoritative | Only validated state transitions permitted — AI has no transition authority |
| **Change transaction state** | State machines are authoritative | Same as above |
| **Activate Brain versions** | Brain activation requires human approval | Version lifecycle: DRAFT → ... → ACTIVE requires explicit human action |
| **Execute payments** | Payment is an adapter concern | AI has no payment adapter access |
| **Determine review eligibility** | Eligibility is deterministic | Based on completed transaction state — no AI judgment |
| **Modify permissions** | Permissions are authorization concerns | RBAC is identity-based — AI has no permission modification path |
| **Access cross-tenant data** | Tenant isolation is foundational | AI adapter receives only tenant-scoped context |
| **Delete audit records** | Audit trail is immutable | No delete path exists for audit records |

---

## 4. AI Execution Pipeline

Every AI interaction follows this mandatory pipeline:

```
1. INPUT
   ├── Customer/business input received
   ├── Context assembled (tenant-scoped only)
   └── Input logged with request_id + correlation_id

2. AI PROCESSING
   ├── AIProvider.complete() or AIProvider.structured_output()
   ├── Provider-agnostic (no hardcoded provider)
   └── Raw output captured for audit

3. SCHEMA VALIDATION
   ├── Output validated against expected Pydantic schema
   ├── Type checking, required fields, value ranges
   └── INVALID → reject, log, fallback to deterministic behavior

4. SEMANTIC VALIDATION
   ├── Does the output make business sense?
   ├── Are referenced entities valid (ServiceOffer exists, category exists)?
   ├── Are values within reasonable bounds?
   └── INVALID → reject, log, fallback

5. CONFLICT DETECTION
   ├── Does the output conflict with existing Brain rules?
   ├── Does it contradict deterministic constraints?
   └── CONFLICT → flag for human review

6. AUTHORITY CHECK
   ├── What authority level is this output?
   ├── L1 → proceed to display
   ├── L2 → proceed to user review
   ├── L3 → proceed to approval workflow
   └── L4 → BLOCK, log security event

7. HUMAN REVIEW (L2+)
   ├── Display to authorized human
   ├── Accept / Modify / Reject
   └── Decision logged with actor + timestamp

8. APPROVAL (L3)
   ├── Route to qualified approver
   ├── Approve / Reject
   └── Decision logged with actor + timestamp

9. EXECUTION
   ├── If approved/accepted → proceed to deterministic service
   ├── Deterministic service validates again
   └── Execute via appropriate adapter/workflow

10. AUDIT
    ├── Full chain recorded: input → AI output → validation → human decision → execution
    ├── Brain version referenced (if applicable)
    ├── Provenance: AI_PROPOSAL with confidence + provider + timestamp
    └── Immutable audit trail
```

---

## 5. AI Agent Specifications

### 5.1 Discovery AI

**Purpose**: Interpret customer natural language into structured search intent.

**Authority Level**: L1 (INFORMATIONAL) for interpretation; results always from database.

**Pipeline**:
```
Customer: "I need an electrician in Manchester for a fuse box replacement"
    │
    ▼
AI Interpretation:
    {
        "intent": "service_search",
        "service_category": "electrical",
        "specific_service": "fuse_box-replacement",
        "location": "Manchester",
        "urgency": "normal"
    }
    │
    ▼
Schema Validation → DiscoveryIntent Pydantic model
    │
    ▼
Deterministic Matching → Query actual businesses + ServiceOffers
    │
    ▼
Results: Only businesses with ACTIVE status + matching ServiceOffers
```

**Constraints**:
- Must NOT invent businesses or services that don't exist
- Must NOT determine pricing
- Must NOT guarantee availability
- Results always from database, never from AI memory

### 5.2 Business Assistant

**Purpose**: Help business owners configure their Brain through natural language.

**Authority Level**: L3 (REQUIRES_APPROVAL) for all Brain modifications.

**Pipeline**:
```
Business Owner: "I don't take bookings less than 3 days in advance"
    │
    ▼
AI Proposal:
    {
        "classification": "availability",
        "rule_type": "minimum_notice",
        "conditions": [],
        "actions": [{
            "outcome": "DENY",
            "parameters": {"minimum_notice_hours": 72}
        }]
    }
    │
    ▼
Schema Validation → Rule structure valid?
    │
    ▼
Conflict Detection → Conflicts with existing rules?
    │
    ▼
Human Review → "AI proposes: [rule]. Conflicts: [list]"
    │
    ▼
Owner approves → New DRAFT rule in Brain version
    │
    ▼
Version lifecycle → VALIDATING → REVIEW → APPROVED → ACTIVE
```

**Constraints**:
- Must NOT directly modify Brain state
- Must NOT activate versions
- Must NOT bypass conflict detection
- Proposals always require human approval

### 5.3 Enquiry Agent

**Purpose**: Help interpret and qualify incoming customer enquiries.

**Authority Level**: L1 for interpretation; L2 for drafting responses.

**Pipeline**:
```
Customer Enquiry: "Hi, I need my garden cleared by Friday. It's about 50sqm."
    │
    ▼
AI Interpretation:
    {
        "service_needed": "garden_clearance",
        "area_size": "50sqm",
        "deadline": "Friday",
        "location_needed": true
    }
    │
    ▼
Qualification Check → What does Brain require?
    │
    ▼
Missing Information:
    {
        "required": ["access_details", "waste_type", "parking_availability"],
        "message": "To provide an accurate quote, could you tell us about..."
    }
    │
    ▼
Draft Response → L2 → Business member reviews before sending
```

**Constraints**:
- Must NOT determine qualification requirements (Brain does that)
- Must NOT send messages without business member review
- Must NOT modify enquiry state

### 5.4 Quote Assistant

**Purpose**: Draft quote explanations and summarize customer information.

**Authority Level**: L2 (PROPOSAL) for all drafts.

**Constraints**:
- Must NOT set prices (Pricing classification does that)
- Must NOT guarantee availability
- All drafts require business member review

### 5.5 Communication Assistant

**Purpose**: Draft customer-facing responses within business policy bounds.

**Authority Level**: L2 (PROPOSAL) for all drafts.

**Constraints**:
- Must NOT send messages without human review
- Must respect Communication classification (I) tone policies
- Must NOT make commitments on behalf of the business

### 5.6 Scheduling Agent (FUTURE)

**Purpose**: Assist with scheduling proposals based on availability rules.

**Authority Level**: L2 (PROPOSAL) for time slot suggestions.

**Constraints**:
- Must NOT confirm bookings (state machine does that)
- Must NOT override availability rules (Availability classification does that)
- Suggestions always verified against deterministic availability

---

## 6. Confidence Handling

### 6.1 Confidence Is Not Authority

| Confidence | Treatment |
|---|---|
| 0.0 - 0.5 | Low confidence — flag for human review, do not auto-apply |
| 0.5 - 0.7 | Medium confidence — present with confidence indicator |
| 0.7 - 0.9 | High confidence — present normally, still requires review for L3 |
| 0.9 - 1.0 | Very high confidence — still requires approval for L3 |

**Critical rule**: No confidence level alone grants authority. Even 100% confidence AI output must go through validation and approval pipelines for L3 actions.

### 6.2 Confidence Sources

- AI provider may return confidence scores
- FIELDed validates confidence against actual outcomes
- Historical confidence accuracy tracked per provider
- Confidence calibration is an ongoing process

---

## 7. Prompt Injection Defense

### 7.1 Threat Model

| Attack Vector | Description | Defense |
|---|---|---|
| Direct injection | Customer input contains instructions to AI | Input sanitization, system/user message separation |
| Indirect injection | External data (web pages, documents) contains instructions | Content validation, output schema enforcement |
| Jailbreaking | Attempts to bypass AI restrictions | System prompt hardening, output validation, authority level enforcement |
| Data extraction | Attempts to extract system prompts or internal data | No sensitive data in prompts, output filtering |

### 7.2 Defense Layers

1. **Input separation**: System prompts never mixed with user input
2. **Schema enforcement**: AI output always validated against expected schema
3. **Authority enforcement**: Even successful injection cannot bypass L4 blocks
4. **Output filtering**: AI output checked for unexpected content before use
5. **Audit logging**: All AI interactions logged for post-incident analysis
6. **Rate limiting**: AI endpoints rate-limited to prevent abuse

---

## 8. Hallucination Prevention

### 8.1 Prevention Mechanisms

| Mechanism | How It Works |
|---|---|
| **Schema validation** | AI output must conform to expected structure — hallucinated fields rejected |
| **Entity verification** | Referenced entities (services, categories, businesses) verified against database |
| **Price verification** | Any price mentioned verified against ServiceOffer pricing |
| **Availability verification** | Any availability claim verified against deterministic availability |
| **Capability verification** | AI cannot claim a business provides a service without matching ServiceOffer |
| **Output grounding** | AI prompted with actual data, not asked to generate from memory |

### 8.2 Detection

- Cross-reference AI output against database records
- Flag any entity reference that doesn't exist
- Flag any price that doesn't match ServiceOffer
- Flag any availability claim not supported by rules
- Log all discrepancies for analysis

---

## 9. AI Provider Management

### 9.1 Provider Agnostism

```python
class AIProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str, **kwargs) -> str: ...

    @abstractmethod
    async def structured_output(self, prompt: str, schema: type[BaseModel], **kwargs) -> BaseModel: ...
```

- No code in the domain layer calls a specific provider
- Provider selection is configuration-based
- Provider can be swapped without domain changes
- Multiple providers can be used for different agents (future)

### 9.2 Provider Evaluation

When selecting AI providers, evaluate:
- Structured output reliability
- Latency characteristics
- Cost per interaction
- Data privacy guarantees
- Rate limits
- Model update frequency

---

## 10. Audit Requirements

Every AI interaction must produce an audit record containing:

| Field | Description |
|---|---|
| `request_id` | Correlates with HTTP request |
| `correlation_id` | Correlates across services |
| `agent_type` | Which AI agent (discovery, business_assistant, etc.) |
| `provider` | Which AI provider was used |
| `model` | Which model was used |
| `input_summary` | Hashed/summarized input (not full prompt in audit) |
| `output_summary` | Structured output received |
| `authority_level` | L1/L2/L3/L4 |
| `validation_result` | VALID/INVALID/CONFLICT |
| `human_decision` | ACCEPTED/MODIFIED/REJECTED (if applicable) |
| `confidence` | AI-reported confidence |
| `latency_ms` | Processing time |
| `tenant_id` | Business context |
| `timestamp` | When the interaction occurred |

---

## 11. Current vs. Future Status

| Capability | Status |
|---|---|
| AIProvider interface | **IMPLEMENTED** |
| StubAIProvider (keyword-based) | **IMPLEMENTED** |
| DiscoveryInterpreter | **IMPLEMENTED** |
| Schema validation for AI output | **IMPLEMENTED** |
| Real AI provider integration | **SPECIFIED BUT NOT IMPLEMENTED** |
| Business Assistant agent | **SPECIFIED BUT NOT IMPLEMENTED** |
| Enquiry Agent | **SPECIFIED BUT NOT IMPLEMENTED** |
| Quote Assistant | **SPECIFIED BUT NOT IMPLEMENTED** |
| Communication Assistant | **SPECIFIED BUT NOT IMPLEMENTED** |
| Scheduling Agent | **SPECIFIED BUT NOT IMPLEMENTED** |
| Prompt injection defenses | **SPECIFIED BUT NOT IMPLEMENTED** |
| Hallucination detection pipeline | **PARTIALLY IMPLEMENTED** (entity verification exists) |
| Confidence tracking | **NOT YET SPECIFIED** |
| Provider evaluation framework | **NOT YET SPECIFIED** |
