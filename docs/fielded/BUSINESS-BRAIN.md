# FIELDed — Business Brain Deep Dive

**Status**: Current State Baseline  
**Last Updated**: 2026-09-24

---

## Overview

The Business Brain is FIELDed's differentiating feature — a **versioned, AI-governed rule system** where AI proposes business knowledge, owners approve proposals, and deterministic rules remain authoritative. The Brain governs all critical business operations: pricing, availability, qualification, policies, escalation, and communication.

---

## Brain Structure

### BusinessBrain Container

Each business has **exactly one** `BusinessBrain`:

```python
class BusinessBrain:
    business_id: UUID (unique)
    active_version_id: UUID (nullable FK to BrainVersion)
    versions: List[BrainVersion]
```

The brain is a container that holds versioned configurations. Only one version is ACTIVE at a time.

### BrainVersion

Each `BrainVersion` is a snapshot of the brain's configuration at a point in time:

```python
class BrainVersion:
    brain_id: UUID
    version_number: int
    status: BrainVersionStatus
    
    # Configuration areas (JSONB)
    identity_config: dict | None
    services_config: dict | None
    pricing_config: dict | None
    availability_config: dict | None
    qualification_config: dict | None
    policies_config: dict | None
    escalation_config: dict | None
    communication_config: dict | None
    
    rules: List[BusinessRule]
```

### BusinessRule

Structured rules within a brain version:

```python
class BusinessRule:
    brain_version_id: UUID
    rule_type: str  # pricing, policy, qualification, availability, escalation
    name: str
    description: str | None
    rule_data: dict  # Structured rule configuration
    priority: int
    is_active: bool
```

---

## Brain Version Lifecycle

### State Machine

```
DRAFT → VALIDATING → REVIEW → APPROVED → ACTIVE → SUPERSEDED
```

**Transitions**:

| From | To | Condition |
|------|-----|-----------|
| DRAFT | VALIDATING | System validation |
| DRAFT | REVIEW | Manual rules (skip validation) |
| VALIDATING | REVIEW | Structural validation passes |
| VALIDATING | DRAFT | Validation fails |
| REVIEW | APPROVED | Owner approval |
| REVIEW | DRAFT | Owner rejects |
| APPROVED | ACTIVE | Activation |
| ACTIVE | SUPERSEDED | New version activated |

### Immutability

Once a version leaves DRAFT status, its configuration is **immutable**:

- DRAFT: Config can be modified
- VALIDATING, REVIEW, APPROVED, ACTIVE, SUPERSEDED: Config cannot be changed
- To make changes, create a new DRAFT version

### Active Version Management

- Only one version is ACTIVE at a time
- `BusinessBrain.active_version_id` points to the active version
- When a new version is activated, the previous active version is marked SUPERSEDED
- Transactions retain the brain version ID that governed them

---

## Configuration Areas

### 1. Identity Configuration

Business identity rules:
- Business name, description, branding
- Contact information
- Location and service area
- Verification status

### 2. Services Configuration

Service catalog rules:
- Service categories
- Service types
- Service descriptions
- Service delivery modes

### 3. Pricing Configuration

Pricing rules and strategies:
- Pricing models (FIXED, HOURLY, QUOTE_REQUIRED, STARTING_AT, CUSTOM)
- Base prices
- Currency
- Pricing rules (discounts, surcharges, tiered pricing)
- Quote generation rules

### 4. Availability Configuration

Availability schedules and rules:
- Operating hours
- Service duration
- Booking lead time
- Capacity constraints
- Holiday schedules
- Blackout periods

### 5. Qualification Configuration

Customer qualification rules:
- Minimum requirements
- Geographic restrictions
- Service-specific qualifications
- Risk assessment criteria

### 6. Policies Configuration

Business policies:
- Cancellation policies
- Refund policies
- Rescheduling policies
- Payment terms
- Service guarantees

### 7. Escalation Configuration

Escalation rules:
- Escalation triggers
- Escalation paths
- Escalation contacts
- Escalation timeouts

### 8. Communication Configuration

Communication preferences:
- Preferred channels (EMAIL, SMS, VOICE, WHATSAPP)
- Communication windows
- Message templates
- Notification preferences

---

## Interactive Co-Brain

### BrainConversation

Conversational sessions between the Brain and the owner:

```python
class BrainConversation:
    brain_id: UUID
    business_id: UUID
    status: BrainConversationStatus  # ACTIVE, ARCHIVED
    title: str | None
    context_summary: str | None
    messages: List[BrainMessage]
    proposals: List[BrainProposal]
```

### BrainMessage

Individual messages within conversations:

```python
class BrainMessage:
    conversation_id: UUID
    role: BrainMessageRole  # BRAIN, OWNER, SYSTEM
    content: str
    metadata: dict | None  # Context, proposal references, confidence scores
```

### BrainProposal

AI-generated proposals for business knowledge:

```python
class BrainProposal:
    brain_id: UUID
    conversation_id: UUID | None
    business_id: UUID
    proposal_type: BrainProposalType
    status: BrainProposalStatus
    confidence: float
    reasoning_summary: str | None
    proposed_change: dict
    affected_area: str | None
    source_message_id: UUID | None
    resolved_at: datetime | None
    is_urgent: bool
```

---

## Proposal Types

| Type | Description |
|------|-------------|
| NEW_SERVICE | Propose new service offer |
| PRICING_RULE | Propose pricing rule change |
| POLICY_RULE | Propose policy rule change |
| AVAILABILITY_RULE | Propose availability rule change |
| QUALIFICATION_RULE | Propose qualification rule change |
| ESCALATION_RULE | Propose escalation rule change |
| IDENTITY_UPDATE | Propose business identity update |
| COMMUNICATION_UPDATE | Propose communication preference update |
| GENERAL_KNOWLEDGE | Propose general business knowledge |

---

## Proposal Lifecycle

### State Machine

```
PENDING → APPROVED / EDITED / REJECTED → APPLIED
```

**Transitions**:

| From | To | Actor |
|------|-----|-------|
| PENDING | APPROVED | Owner |
| PENDING | EDITED | Owner (with modifications) |
| PENDING | REJECTED | Owner |
| APPROVED | APPLIED | System |
| EDITED | APPLIED | System |

### Governance Flow

1. **Conversation**: Owner interacts with Brain
2. **Proposal Generation**: AI generates structured proposal from conversation
3. **Proposal Review**: Owner reviews proposal with confidence score and reasoning
4. **Approval Decision**: Owner approves, edits, or rejects
5. **Application**: Approved proposal applied to Brain state
6. **Version Update**: New Brain version created if needed

---

## AI Intelligence vs Business Authority

### What AI Can Do

- **Interpret** customer enquiries
- **Extract** business knowledge from conversations
- **Propose** new services, pricing rules, policies
- **Suggest** availability and qualification rules
- **Generate** reasoning summaries
- **Provide** confidence scores
- **Recommend** improvements

### What AI Cannot Do

- **Set or change prices** without business rule validation
- **Determine availability** without checking deterministic constraints
- **Override business policies**
- **Authorize customers** or grant permissions
- **Change booking/transaction state** directly
- **Determine review eligibility**
- **Silently mutate** production Brain state

### Deterministic Authority

All critical decisions flow through **deterministic code**:

- Pricing calculation uses configured pricing rules
- Availability checking uses configured availability rules
- Qualification uses configured qualification rules
- Policy enforcement uses configured policies
- State transitions use validated state machines

AI proposes; deterministic rules authorize.

---

## Brain Traceability

### Transaction Traceability

Every transaction retains the brain version that governed it:

- **Enquiry**: `enquiry.brain_version_id`
- **Quote**: `quote.brain_version_id` + `quote.pricing_evidence`
- **Booking**: `booking.brain_version_id` + `booking.decision_evidence`

This ensures **historical reproducibility**: even after a newer brain version is activated, you can trace exactly which rules governed each transaction.

### Evidence Tracking

- Quotes retain pricing evidence (base amount, applied rules, surcharges, discounts)
- Bookings retain decision evidence (brain decision, availability evaluation)
- Proposals retain reasoning summaries and confidence scores

---

## Brain Validation

### Structural Validation

Before a brain version can enter REVIEW status, it must pass structural validation:

- Configuration structure must be valid
- Rule types must be recognized
- Rule data must conform to expected schemas
- Required fields must be present

### Configuration Validation

Each configuration area has specific validation rules:

- **Identity**: Required fields (name, description)
- **Services**: Valid service structures
- **Pricing**: Valid pricing models, positive amounts
- **Availability**: Valid time formats, logical schedules
- **Qualification**: Valid qualification criteria
- **Policies**: Valid policy structures
- **Escalation**: Valid escalation paths
- **Communication**: Valid channel configurations

---

## Brain API Endpoints

### Brain Management

```
GET    /api/v1/businesses/{business_id}/brain
POST   /api/v1/businesses/{business_id}/brain/versions
GET    /api/v1/businesses/{business_id}/brain/versions
GET    /api/v1/businesses/{business_id}/brain/versions/{version_id}
PATCH  /api/v1/businesses/{business_id}/brain/versions/{version_id}
POST   /api/v1/businesses/{business_id}/brain/versions/{version_id}/transition
```

### Brain Conversations

```
POST   /api/v1/businesses/{business_id}/brain-conversations
GET    /api/v1/businesses/{business_id}/brain-conversations
GET    /api/v1/businesses/{business_id}/brain-conversations/{conversation_id}
POST   /api/v1/businesses/{business_id}/brain-conversations/{conversation_id}/messages
GET    /api/v1/businesses/{business_id}/brain-conversations/{conversation_id}/messages
```

### Brain Proposals

```
GET    /api/v1/businesses/{business_id}/brain-proposals
GET    /api/v1/businesses/{business_id}/brain-proposals/{proposal_id}
POST   /api/v1/businesses/{business_id}/brain-proposals/{proposal_id}/approve
POST   /api/v1/businesses/{business_id}/brain-proposals/{proposal_id}/reject
```

### Brain Knowledge

```
GET    /api/v1/businesses/{business_id}/brain/knowledge
GET    /api/v1/businesses/{business_id}/brain/context
```

---

## Brain Frontend Pages

### Business Brain Page

Located at `/business/brain`:

- View active brain version
- View brain version history
- Create new brain version
- Edit DRAFT brain version
- Transition brain version status
- View brain conversations
- View brain proposals
- Approve/reject proposals

### Brain Conversation UI

- Create new conversation
- Send messages to brain
- View conversation history
- View proposals generated from conversation
- Approve/reject proposals inline

---

## Brain Architecture Risks

### Current Risks

1. **AI Provider Dependency**: Brain conversations depend on AI provider availability
2. **Proposal Application**: Proposal application logic is complex and must be carefully tested
3. **Version Proliferation**: Many brain versions could accumulate over time
4. **Configuration Drift**: Configuration areas could drift out of sync with rules

### Mitigations

1. **Provider Agnostic**: AI provider abstraction allows switching providers
2. **Validation**: Structural validation prevents invalid configurations
3. **Immutability**: Immutable versions prevent accidental mutations
4. **Traceability**: Transaction traceability ensures historical reproducibility

---

## Brain Extension Points

### Adding New Rule Types

1. Add rule type to `BusinessRule.rule_type` enum
2. Add validation logic in `app/domain/business/validation.py`
3. Add evaluation logic in `app/domain/business/evaluator.py`
4. Add registry entry in `app/domain/business/registry.py`

### Adding New Configuration Areas

1. Add configuration field to `BrainVersion` model
2. Add configuration validation in `app/domain/business/validation.py`
3. Add configuration evaluation logic
4. Add API endpoints for configuration management
5. Add frontend UI for configuration editing

### Adding New Proposal Types

1. Add proposal type to `BrainProposalType` enum
2. Add proposal generation logic
3. Add proposal application logic
4. Add frontend UI for proposal review

---

## Brain Testing

### Unit Tests

- `test_brain_conversation_proposal.py`: Brain conversation and proposal tests
- `test_phase09_brain_runtime.py`: Brain runtime tests
- `test_workload_ai_resolvers.py`: AI provider resolver tests

### Integration Tests

- `test_brain_api.py`: Brain API integration tests

### Test Coverage

- Brain version lifecycle
- Brain configuration validation
- Brain proposal generation
- Brain proposal approval/rejection
- Brain proposal application
- Brain conversation messaging
- Brain knowledge context
- AI provider integration

---

## Summary

The Business Brain is a **comprehensive, AI-governed rule system** that:

- Provides versioned business configuration
- Enables AI-assisted business knowledge management
- Maintains deterministic authority over critical decisions
- Ensures historical traceability of all transactions
- Supports interactive co-brain conversations
- Governs pricing, availability, qualification, policies, escalation, and communication

The Brain architecture embodies FIELDed's core principle: **AI intelligence != business authority**. AI proposes; deterministic rules authorize.
