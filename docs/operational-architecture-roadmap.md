# FIELDed — Operational Architecture Roadmap

> **Status**: SPECIFIED — AWAITING APPROVAL  
> **Phase**: Architecture + Specification Only  
> **Last Updated**: 2026-09-19

---

## Overview

This roadmap defines the implementation order for FIELDed's operational layer after specification approval. Each phase builds on the previous one, with explicit dependencies.

---

## Specification Documents

| Document | Coverage |
|---|---|
| [business-brain-specification.md](business-brain-specification.md) | Core Brain definition, rule system, conditions, actions, scope, versioning, AI pipeline, governance, evaluation, database, API, workflow, failure, extensibility |
| [business-brain-classification.md](business-brain-classification.md) | Complete classification taxonomy (A–Q) |
| [ai-governance.md](ai-governance.md) | AI authority levels, capabilities, prohibitions, pipeline, agent specs |
| [customer-journey.md](customer-journey.md) | Complete customer journey from anonymous visitor to review |
| [business-onboarding.md](business-onboarding.md) | Business onboarding flow with implementation status |
| [discovery-ranking.md](discovery-ranking.md) | Discovery + ranking architecture |
| [authorization-model.md](authorization-model.md) | Extended authorization with Brain permissions |
| [audit-and-provenance.md](audit-and-provenance.md) | Audit events, evidence, provenance, reconstruction |
| [operational-state-machines.md](operational-state-machines.md) | Complete state machine specifications |

---

## Cross-Domain Examples

### Example 1: General Service Business (e.g., Electrician)

```
Natural language instruction:
    Business owner: "I charge £80 for a standard socket installation,
    but £120 if it's an emergency same-day job. I need 24 hours notice
    for normal jobs and don't work weekends."

→ AI Proposal:
    {
        classification: "pricing",
        rule_type: "base_pricing",
        conditions: [{field: "service_category", op: "EQUALS", value: "electrical"}],
        actions: [{outcome: "SET_VALUE", parameters: {amount: 80, currency: "GBP"}}]
    }
    + surcharge rule for same-day (+£40)
    + availability rule for minimum_notice (24h) + weekend blackout

→ Schema Validation: PASS
→ Semantic Validation: PASS (no contradictions)
→ Conflict Detection: No conflicts with existing rules

→ Human Review: Owner reviews proposed rules
→ Approval: Owner approves

→ Brain Version: New DRAFT created with 3 rules
→ Validation: All rules valid
→ Review: Submitted by owner
→ Approval: Owner approves (self-approval as owner)
→ Activation: Version becomes ACTIVE

→ Runtime Evaluation (when customer enquires):
    Customer: "I need a socket installed today"
    Context: {service: electrical, notice_hours: 0, day: wednesday}

    Rule evaluation:
    1. Base pricing: £80 (matches)
    2. Same-day surcharge: +£40 (notice_hours < 24 → applies)
    3. Minimum notice: 24h required (notice_hours=0 → DENY)

    Result: DENY — "Minimum 24-hour notice required. Would tomorrow work?"

→ Deterministic Decision: DENY with explanation
→ Authorization: N/A (informational response)
→ Execution: Response drafted within Communication classification guidelines
→ Audit: Full evaluation logged with brain_version_id + matched rules
```

### Example 2: Professional Services (e.g., Solicitor)

```
Natural language instruction:
    Business owner: "For employment law consultations, I need clients to
    provide their employment contract and any correspondence before I
    can quote. Consultations are £250 per hour. Anything over £1000
    needs a partner's approval."

→ AI Proposals:
    1. Qualification rule: required_information = [employment_contract, correspondence]
    2. Pricing rule: base_pricing = £250/hour for employment_law
    3. Approval rule: require_approval when enquiry_value > £1000

→ Validation: PASS
→ Conflict Detection: No conflicts

→ Human Review: Partner reviews
→ Approval: Partner approves (owner-level for pricing + approval rules)

→ Runtime Evaluation:
    Customer enquires about employment law dispute (£1500 estimated)

    Rule evaluation:
    1. Qualification: REQUIRE_INFORMATION (contract + correspondence)
    2. Pricing: SET_VALUE (£250/hour)
    3. Approval: REQUIRE_APPROVAL (value > £1000)

    Result: REQUIRE_INFORMATION + REQUIRE_APPROVAL
    → "Please provide your employment contract and relevant correspondence.
       Your quote will need partner review."

→ Deterministic Decision: Multi-outcome result
→ Workflow: Pause enquiry for information; route to partner for approval
→ Audit: Full chain recorded
```

### Example 3: Appointment-Based Business (e.g., Hair Salon)

```
Natural language instruction:
    Business owner: "Haircuts are £35, colouring starts at £80.
    I work Tuesday to Saturday, 9am to 6pm. Each appointment slot
    is 45 minutes for cuts and 2 hours for colouring. I need at
    least 48 hours notice for colouring."

→ AI Proposals:
    1. Pricing: haircut=£35, colouring=£80+
    2. Availability: Tue-Sat 9-18, slot_duration varies by service
    3. Minimum notice: 48h for colouring, 24h for cuts

→ Runtime Evaluation:
    Customer: "I'd like a haircut this Saturday at 2pm"

    Rule evaluation:
    1. Availability: Saturday is operating day, 14:00 is within hours
    2. Capacity: Check existing bookings for Saturday 14:00 slot
    3. Notice: 24h required (假设 it's Wednesday → 72h notice → PASS)
    4. Pricing: SET_VALUE £35

    Result: ALLOW with price £35

→ Booking proposed: Saturday 14:00, £35
→ Customer accepts → Booking CONFIRMED
→ Audit: Full chain
```

### Example 4: High-Value / High-Approval Business (e.g., Construction)

```
Natural language instruction:
    Business owner: "For any project over £5000, I need to visit the
    site before quoting. Projects over £20,000 need my personal approval.
    I require a 30% deposit for all work. Cancellation within 7 days
    of start date forfeits the deposit."

→ AI Proposals:
    1. Qualification: REQUIRE_INFORMATION when value > £5000 (site visit needed)
    2. Approval: REQUIRE_APPROVAL (owner) when value > £20,000
    3. Payment: deposit_policy = 30% for all projects
    4. Cancellation: fee = 100% of deposit when notice < 7 days

→ Runtime Evaluation:
    Customer: "I need a full house renovation, budget around £30,000"

    Rule evaluation:
    1. Qualification: REQUIRE_INFORMATION (site visit required, value > £5000)
    2. Approval: REQUIRE_APPROVAL (value > £20,000)
    3. Payment: SET_VALUE deposit = 30% = £9,000
    4. Cancellation: Noted for future (7-day forfeiture rule)

    Result: REQUIRE_INFORMATION + REQUIRE_APPROVAL
    → "For a project of this size, we'll need to visit your property
       before providing a quote. This will be personally reviewed by
       our director. A 30% deposit is required to commence work."

→ Workflow: Schedule site visit → quote → owner approval → deposit → commence
→ Audit: Full chain with Brain version reference
```

---

## Implementation Phases

### Phase 1: Business Brain Domain Contracts

**Objective**: Define the core domain interfaces and contracts for Business Brain operations.

**Deliverables**:
- Brain evaluation service interface
- Rule evaluation result types
- Classification schema definitions (Pydantic models)
- Condition evaluation engine interface
- Conflict detection interface

**Dependencies**: None (foundation)
**Estimated Complexity**: Medium

---

### Phase 2: Persistence + Versioning

**Objective**: Extend BrainVersion and BusinessRule models to support the full specification.

**Deliverables**:
- Database migration: Extend BrainVersion (approval fields, effective dates, parent_version_id)
- Database migration: Extend BusinessRule (classification, scope, conditions, actions, source, provenance)
- Database migration: Create AIProposal table
- Database migration: Create ApprovalRecord table
- Repository implementations for new entities
- Version comparison service

**Dependencies**: Phase 1
**Estimated Complexity**: Medium-High

---

### Phase 3: Rule Validation

**Objective**: Implement deterministic rule validation at proposal time.

**Deliverables**:
- Classification-specific schema validators
- Condition validation (field types, operators, value types)
- Action validation (valid outcomes per classification)
- Scope validation (valid scope per classification)
- Cross-rule conflict detection within a version
- Validation service with structured error responses

**Dependencies**: Phase 1, Phase 2
**Estimated Complexity**: High

---

### Phase 4: Deterministic Evaluation

**Objective**: Implement the rule evaluation engine.

**Deliverables**:
- Condition evaluation engine (all operators)
- Rule scope resolution (specificity ordering)
- Priority-based conflict resolution
- Evaluation result construction
- EvaluationLog persistence
- Reproducibility guarantee (pure function)

**Dependencies**: Phase 1, Phase 3
**Estimated Complexity**: High

---

### Phase 5: Approval + Governance

**Objective**: Implement human governance for Brain changes.

**Deliverables**:
- Approval policy configuration
- Approval workflow (submit → review → approve/reject)
- ApprovalRecord creation and querying
- Timeout handling
- Escalation on timeout
- Re-review after modification

**Dependencies**: Phase 2, Phase 3
**Estimated Complexity**: Medium

---

### Phase 6: Brain APIs

**Objective**: Expose Brain management through API endpoints.

**Deliverables**:
- Brain retrieval endpoints
- Version CRUD endpoints
- Version comparison endpoint
- Rule CRUD endpoints
- Rule validation endpoint
- Governance endpoints (submit, approve, reject, activate, archive, rollback)
- Authorization integration (Brain permissions)

**Dependencies**: Phase 2, Phase 3, Phase 4, Phase 5
**Estimated Complexity**: Medium-High

---

### Phase 7: Pricing Integration

**Objective**: Connect Brain Pricing classification (B) to quote generation.

**Deliverables**:
- Pricing rule evaluation during quote creation
- Surcharge calculation
- Discount application
- Price floor/cap enforcement
- Quote threshold evaluation
- Brain version reference on quotes

**Dependencies**: Phase 4, Phase 6, Quote system implementation
**Estimated Complexity**: High

---

### Phase 8: Availability Integration

**Objective**: Connect Brain Availability classification (C) to booking system.

**Deliverables**:
- Availability rule evaluation during booking proposal
- Operating hours checking
- Minimum notice enforcement
- Capacity limit checking
- Blackout period enforcement
- Brain version reference on bookings

**Dependencies**: Phase 4, Phase 6, Booking system implementation
**Estimated Complexity**: High

---

### Phase 9: Qualification / Policy Integration

**Objective**: Connect Brain Qualification (D) and Policy (E) classifications to enquiry flow.

**Deliverables**:
- Qualification evaluation during enquiry creation
- Information request generation
- Policy evaluation during cancellation/modification
- Fee calculation per policy rules
- Brain version reference on decisions

**Dependencies**: Phase 4, Phase 6
**Estimated Complexity**: Medium-High

---

### Phase 10: Enquiry Integration

**Objective**: Full Brain integration with enquiry lifecycle.

**Deliverables**:
- Brain evaluation at each enquiry transition
- Escalation handling per Brain rules
- Communication policy enforcement
- Brain-aware enquiry processing

**Dependencies**: Phase 4, Phase 6, Phase 9
**Estimated Complexity**: Medium

---

### Phase 11: Booking Integration

**Objective**: Full Brain integration with booking lifecycle.

**Deliverables**:
- Brain evaluation at each booking transition
- Cancellation/rescheduling policy enforcement
- Deposit requirement enforcement
- Completion criteria validation

**Dependencies**: Phase 4, Phase 6, Phase 8
**Estimated Complexity**: Medium

---

### Phase 12: AI Proposal Pipeline

**Objective**: Connect AI agents to Brain configuration pipeline.

**Deliverables**:
- Real AI provider integration (replace StubAIProvider)
- Business Assistant agent implementation
- AI proposal creation and management
- Proposal → validation → review → approval pipeline
- AI proposal audit trail
- Prompt injection defenses
- Hallucination detection

**Dependencies**: Phase 2, Phase 3, Phase 6
**Estimated Complexity**: High

---

### Phase 13: Business Brain Frontend Activation

**Objective**: Build frontend UI for Brain management.

**Deliverables**:
- Brain dashboard (view active version, rules)
- Rule creation/editing UI (structured forms)
- AI proposal interface (natural language → review)
- Version comparison UI
- Approval workflow UI
- Audit history viewer

**Dependencies**: Phase 6, Phase 12
**Estimated Complexity**: High

---

### Phase 14: Audit / Evidence Expansion

**Objective**: Full audit and evidence system.

**Deliverables**:
- AuditEvent entity + migration
- Evidence entity + migration
- EvaluationLog entity + migration
- Audit event creation at every meaningful action
- Evidence storage integration
- Historical reconstruction API
- Audit query endpoints
- Retention policy enforcement

**Dependencies**: Phase 2
**Estimated Complexity**: Medium-High

---

## Phase Dependency Graph

```
Phase 1 (Domain Contracts)
    │
    ├──→ Phase 2 (Persistence)
    │       │
    │       ├──→ Phase 3 (Validation)
    │       │       │
    │       │       ├──→ Phase 4 (Evaluation)
    │       │       │       │
    │       │       │       ├──→ Phase 7 (Pricing Integration)
    │       │       │       ├──→ Phase 8 (Availability Integration)
    │       │       │       ├──→ Phase 9 (Qualification/Policy)
    │       │       │       │       │
    │       │       │       │       ├──→ Phase 10 (Enquiry Integration)
    │       │       │       │       └──→ Phase 11 (Booking Integration)
    │       │       │       │
    │       │       │       └──→ Phase 6 (APIs)
    │       │       │               │
    │       │       │               ├──→ Phase 13 (Frontend)
    │       │       │               └──→ Phase 7, 8, 9, 10, 11
    │       │       │
    │       │       └──→ Phase 5 (Approval + Governance)
    │       │               │
    │       │               └──→ Phase 6
    │       │
    │       ├──→ Phase 12 (AI Pipeline)
    │       │       │
    │       │       └──→ Phase 13
    │       │
    │       └──→ Phase 14 (Audit/Evidence)
    │
    └──→ (can start in parallel with Phase 2)
```

---

## Parallel Opportunities

| Phases That Can Run in Parallel | Reason |
|---|---|
| Phase 7 + Phase 8 + Phase 9 | Independent classification integrations |
| Phase 10 + Phase 11 | Independent transaction integrations |
| Phase 12 + Phase 14 | AI pipeline and audit are independent |
| Phase 5 + Phase 4 | Governance and evaluation can develop in parallel |

---

## Open Architectural Questions

| # | Question | Impact | Recommended Decision |
|---|---|---|---|
| 1 | Should BrainVersion support branching? | Complexity vs. flexibility | No — keep linear. Multiple DRAFTs allowed but single pipeline. |
| 2 | Permanent evaluation logs or on-demand? | Storage vs. audit completeness | Permanent — audit requirements demand it. |
| 3 | Maximum rules per Brain version? | Performance vs. freedom | No hard limit initially. Monitor performance. Add limit if needed. |
| 4 | Cross-version rule dependencies? | Hidden coupling risk | Prohibit. Each version is self-contained. |
| 5 | Approval policies: per-business or platform? | Flexibility vs. consistency | Per-business with platform defaults. |
| 6 | When to introduce row-level security (RLS)? | Security depth vs. complexity | Not yet. Repository-layer isolation is sufficient for now. |
| 7 | How to handle Brain configuration for businesses with no Brain? | Default behavior | Use most restrictive defaults. No Brain = minimal automation. |

---

## Risks

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| Over-engineering for early-stage product | High | Medium | Phased implementation. Ship core first. |
| Rule evaluation performance at scale | Medium | Low | Indexing, caching per active version, early termination |
| AI proposal quality inconsistency | Medium | Medium | Provider evaluation, schema validation, human review |
| Classification taxonomy too rigid | Medium | Low | Extensible by design. New classifications don't require core changes. |
| Migration complexity for existing data | Medium | Medium | Existing BrainVersion/BusinessRule data needs migration strategy |
| Scope creep from "just one more classification" | Low | High | Strict phase gating. Classifications added incrementally. |

---

## Tradeoffs

| Decision | Chosen | Rejected | Rationale |
|---|---|---|---|
| Rule storage | Hybrid (normalized + JSONB) | Pure normalized or pure JSONB | Flexibility within structure |
| Ranking approach | Tiered (deterministic) | Numeric weights | No arbitrary weights without evidence |
| AI authority | Proposal-only (L2/L3) | Direct action (L1 for config) | AI must not be authoritative |
| Approval model | Role-based + configurable | Platform-wide fixed | Business autonomy |
| Evaluation storage | Permanent logs | On-demand only | Audit completeness |
| State machine + Brain | Separate layers | Brain replaces state machine | State machines are authoritative |

---

## Final Output Summary

| Deliverable | Document |
|---|---|
| A. Documents created/updated | 9 new documents + this roadmap |
| B. Business Brain architecture | [business-brain-specification.md](business-brain-specification.md) |
| C. Classification taxonomy | [business-brain-classification.md](business-brain-classification.md) |
| D. Rule ontology | [business-brain-specification.md §3-5](business-brain-specification.md) |
| E. Decision/evaluation model | [business-brain-specification.md §10](business-brain-specification.md) |
| F. AI governance model | [ai-governance.md](ai-governance.md) |
| G. Human approval model | [business-brain-specification.md §9](business-brain-specification.md) |
| H. Customer journey | [customer-journey.md](customer-journey.md) |
| I. Business onboarding | [business-onboarding.md](business-onboarding.md) |
| J. Discovery/ranking | [discovery-ranking.md](discovery-ranking.md) |
| K. Authorization model | [authorization-model.md](authorization-model.md) |
| L. Audit/provenance | [audit-and-provenance.md](audit-and-provenance.md) |
| M. State-machine relationships | [operational-state-machines.md](operational-state-machines.md) |
| N. Database proposal | [business-brain-specification.md §13](business-brain-specification.md) |
| O. API proposal | [business-brain-specification.md §14](business-brain-specification.md) |
| P. Extensibility model | [business-brain-specification.md §15](business-brain-specification.md) |
| Q. Failure model | [business-brain-specification.md §12](business-brain-specification.md) |
| R. Implementation roadmap | This document |
| S. Open questions | This document §Open Questions |
| T. Risks/tradeoffs | This document §Risks/Tradeoffs |

---

**STOP. No implementation begins until explicit approval is received.**
