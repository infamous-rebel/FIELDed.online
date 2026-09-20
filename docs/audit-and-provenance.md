# FIELDed — Audit & Provenance

> **Status**: SPECIFIED BUT NOT IMPLEMENTED  
> **Phase**: Architecture + Specification Only  
> **Last Updated**: 2026-09-19

---

## Overview

This document defines how FIELDed answers every audit question for every transaction, rule change, and system event. The audit architecture supports complete historical reconstruction of any decision.

---

## 1. Audit Questions

FIELDed must be able to answer, for any transaction or decision:

| # | Question | Answer Source |
|---|---|---|
| 1 | **Who changed this?** | `AuditEvent.actor_id` → User |
| 2 | **What changed?** | `AuditEvent.change_type` + `AuditEvent.details` |
| 3 | **Why?** | `AuditEvent.reason` + `AuditEvent.provenance` |
| 4 | **When?** | `AuditEvent.created_at` |
| 5 | **Who approved it?** | `ApprovalRecord.approver_id` → User |
| 6 | **Which Brain version?** | `AuditEvent.brain_version_id` → BrainVersion |
| 7 | **Which rule?** | `AuditEvent.rule_id` → BusinessRule |
| 8 | **Which evidence?** | `Evidence.audit_event_id` → Evidence records |
| 9 | **Which transaction was affected?** | `AuditEvent.transaction_id` + `AuditEvent.transaction_type` |

---

## 2. Provenance Classification

Every change or decision has a provenance type:

| Provenance | Code | Description | Example |
|---|---|---|---|
| **HUMAN** | `HUMAN` | Direct human action | Business owner creates a pricing rule |
| **AI_PROPOSAL** | `AI_PROPOSAL` | AI proposed, human approved | AI suggests availability rule, owner approves |
| **IMPORT** | `IMPORT` | Bulk imported from external source | Rules imported from spreadsheet |
| **TEMPLATE** | `TEMPLATE` | Applied from a template | Pre-built rule template applied |
| **SYSTEM** | `SYSTEM` | System-generated automatic action | Auto-expiry of stale enquiry |
| **INTEGRATION** | `INTEGRATION` | From external integration | Calendar sync triggered status change |

### Provenance Metadata

```python
Provenance
├── type: str (HUMAN | AI_PROPOSAL | IMPORT | TEMPLATE | SYSTEM | INTEGRATION)
├── actor_id: UUID | null (null for SYSTEM)
├── ai_provider: str | null (if AI_PROPOSAL)
├── ai_model: str | null (if AI_PROPOSAL)
├── proposal_id: UUID | null (if AI_PROPOSAL → AIProposal.id)
├── confidence: float | null (if AI_PROPOSAL)
├── source_system: str | null (if IMPORT or INTEGRATION)
├── template_id: UUID | null (if TEMPLATE)
├── import_batch_id: UUID | null (if IMPORT)
└── metadata: dict | null (additional context)
```

---

## 3. Entity Relationships

### 3.1 Core Audit Entities

```
AuditEvent
├── id: UUID PK
├── business_id: UUID FK → businesses (tenant scope)
├── actor_id: UUID FK → users | null (null for system events)
├── event_type: str (e.g., "brain_version_activated", "rule_created", "enquiry_transition")
├── resource_type: str (e.g., "brain_version", "business_rule", "enquiry", "booking")
├── resource_id: UUID (the affected resource)
├── brain_version_id: UUID FK → brain_versions | null
├── rule_id: UUID FK → business_rules | null
├── transaction_id: UUID | null (enquiry_id, booking_id, etc.)
├── transaction_type: str | null
├── change_type: str (CREATED | UPDATED | DELETED | TRANSITIONED | ACTIVATED | ARCHIVED)
├── previous_state: str | null
├── new_state: str | null
├── details: JSONB (structured change details)
├── reason: str | null
├── provenance: JSONB (Provenance structure)
├── request_id: str | null
├── correlation_id: str | null
├── ip_address: str | null
├── user_agent: str | null
├── created_at: TIMESTAMPTZ (immutable)
└── deleted_at: TIMESTAMPTZ | null (soft delete — audit records should never be deleted)
```

```
Evidence
├── id: UUID PK
├── audit_event_id: UUID FK → audit_events
├── evidence_type: str (DOCUMENT | IMAGE | LOG | SNAPSHOT | EXTERNAL)
├── content_type: str (MIME type)
├── storage_reference: str (path/URL to stored evidence)
├── description: str | null
├── metadata: JSONB | null
├── created_at: TIMESTAMPTZ
└── deleted_at: TIMESTAMPTZ | null
```

### 3.2 Relationship Map

```
AuditEvent ──N:1── Business (tenant scope)
AuditEvent ──N:1── User (actor, nullable for system)
AuditEvent ──N:1── BrainVersion | null (governing version)
AuditEvent ──N:1── BusinessRule | null (specific rule)
AuditEvent ──1:N── Evidence (supporting evidence)
AuditEvent ──────── Transaction (via transaction_id + transaction_type)

BrainVersion ──1:N── AuditEvent (all events for this version)
BusinessRule ──1:N── AuditEvent (all events for this rule)
```

---

## 4. Audit Event Types

### 4.1 Brain Events

| Event Type | Resource | When |
|---|---|---|
| `brain_version_created` | BrainVersion | New DRAFT version created |
| `brain_version_submitted` | BrainVersion | Version submitted for review |
| `brain_version_validated` | BrainVersion | Validation completed |
| `brain_version_approved` | BrainVersion | Owner approved version |
| `brain_version_rejected` | BrainVersion | Owner rejected version |
| `brain_version_activated` | BrainVersion | Version became ACTIVE |
| `brain_version_superseded` | BrainVersion | Previous ACTIVE replaced |
| `brain_version_archived` | BrainVersion | Version archived |
| `brain_rollback` | BusinessBrain | Rollback to previous version |

### 4.2 Rule Events

| Event Type | Resource | When |
|---|---|---|
| `rule_created` | BusinessRule | New rule added to version |
| `rule_updated` | BusinessRule | Rule modified in DRAFT |
| `rule_deleted` | BusinessRule | Rule removed from DRAFT |
| `rule_activated` | BusinessRule | Rule became effective |
| `rule_deactivated` | BusinessRule | Rule deactivated |
| `rule_conflict_detected` | BusinessRule | Conflict found during validation |

### 4.3 Transaction Events

| Event Type | Resource | When |
|---|---|---|
| `enquiry_created` | Enquiry | Customer creates enquiry |
| `enquiry_transitioned` | Enquiry | Enquiry state changes |
| `message_sent` | Message | Message sent in conversation |
| `quote_created` | Quote | Quote generated for enquiry |
| `quote_accepted` | Quote | Customer accepts quote |
| `quote_rejected` | Quote | Customer rejects quote |
| `booking_created` | Booking | Booking created |
| `booking_transitioned` | Booking | Booking state changes |
| `booking_completed` | Booking | Service completed |
| `review_submitted` | Review | Customer submits review |

### 4.4 AI Events

| Event Type | Resource | When |
|---|---|---|
| `ai_proposal_created` | AIProposal | AI generates a proposal |
| `ai_proposal_accepted` | AIProposal | Human accepts AI proposal |
| `ai_proposal_modified` | AIProposal | Human modifies AI proposal |
| `ai_proposal_rejected` | AIProposal | Human rejects AI proposal |
| `ai_interpretation` | DiscoveryIntent | AI interprets customer query |
| `ai_validation_failed` | — | AI output failed validation |

### 4.5 System Events

| Event Type | Resource | When |
|---|---|---|
| `enquiry_expired` | Enquiry | System auto-expires stale enquiry |
| `booking_expired` | Booking | System auto-expires stale booking |
| `quote_expired` | Quote | Quote validity expired |
| `approval_timeout` | ApprovalRecord | Approval timed out |
| `integration_failure` | Integration | External integration failed |

---

## 5. Historical Reconstruction

### 5.1 Reconstruction Algorithm

Given a transaction (e.g., enquiry), reconstruct the complete decision chain:

```python
def reconstruct_decision(enquiry_id):
    # 1. Find the enquiry
    enquiry = get_enquiry(enquiry_id)

    # 2. Find the Brain version that governed it
    brain_version = get_brain_version(enquiry.brain_version_id)

    # 3. Find all audit events for this enquiry
    events = get_audit_events(transaction_id=enquiry_id)

    # 4. Find all rules that were evaluated
    evaluation_logs = get_evaluation_logs(transaction_id=enquiry_id)

    # 5. Find all evidence
    evidence = get_evidence_for_events([e.id for e in events])

    # 6. Reconstruct timeline
    timeline = build_timeline(events)

    # 7. Return complete reconstruction
    return DecisionReconstruction(
        enquiry=enquiry,
        brain_version=brain_version,
        rules_at_version=brain_version.rules,
        evaluation_results=evaluation_logs,
        evidence=evidence,
        timeline=timeline,
        provenance_chain=build_provenance_chain(events)
    )
```

### 5.2 Reproducibility

Given:
- A `brain_version_id`
- The rules that existed in that version
- The evaluation context at the time

The decision can be **reproduced exactly** because:
- BrainVersions are immutable once ACTIVE/SUPERSEDED
- Rules within a version don't change
- Evaluation is deterministic (pure function)
- Context is preserved in EvaluationLog

---

## 6. Audit Query Patterns

### 6.1 Common Queries

| Query | Purpose |
|---|---|
| All events for a transaction | Full history of an enquiry/booking |
| All events for a Brain version | What happened during this version's lifetime |
| All events for a rule | Complete rule lifecycle |
| All events by an actor | What did this user do |
| All AI proposals for a business | AI interaction history |
| All approval decisions | Approval audit trail |
| All conflicts detected | Conflict history |
| Events in time range | Activity monitoring |
| Events by provenance type | Human vs AI vs system breakdown |

### 6.2 Indexing Strategy

| Index | Purpose |
|---|---|
| `(business_id, created_at)` | Tenant-scoped time queries |
| `(transaction_id, transaction_type)` | Transaction history |
| `(brain_version_id, created_at)` | Version-scoped events |
| `(rule_id, created_at)` | Rule lifecycle |
| `(actor_id, created_at)` | Actor activity |
| `(event_type, created_at)` | Event type monitoring |
| `(provenance->>'type', created_at)` | Provenance-type queries |

---

## 7. Retention Policy

| Record Type | Retention | Rationale |
|---|---|---|
| AuditEvent | Indefinite (while business exists) | Legal + dispute requirements |
| Evidence | Indefinite (while referenced by audit events) | Supporting documentation |
| EvaluationLog | Indefinite (while business exists) | Decision reproducibility |
| AIProposal (resolved) | 2 years after resolution | Historical reference |
| AIProposal (pending) | Until resolved or 90 days | Cleanup |

---

## 8. Current vs. Future

| Component | Status |
|---|---|
| Structured logging (structlog) | ✅ IMPLEMENTED |
| Request ID middleware | ✅ IMPLEMENTED |
| Correlation ID middleware | ✅ IMPLEMENTED |
| Enquiry transition logging | ✅ IMPLEMENTED |
| Message logging | ✅ IMPLEMENTED |
| AuditEvent entity | 📋 SPECIFIED |
| Evidence entity | 📋 SPECIFIED |
| EvaluationLog entity | 📋 SPECIFIED |
| AIProposal audit trail | 📋 SPECIFIED |
| Historical reconstruction | 📋 SPECIFIED |
| Audit query API | 📋 SPECIFIED |
| Evidence storage integration | 🔮 FUTURE |
| Retention policy enforcement | 🔮 FUTURE |
| Audit dashboard | 🔮 FUTURE |
