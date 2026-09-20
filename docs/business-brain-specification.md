# FIELDed — Business Brain Specification

> **Status**: SPECIFIED BUT NOT IMPLEMENTED  
> **Phase**: Architecture + Specification Only  
> **Last Updated**: 2026-09-19

---

## 1. Definition

The **Business Brain** is the versioned, governed configuration of how a business operates on FIELDed. It represents the complete set of operational rules, policies, pricing logic, availability constraints, qualification requirements, and behavioral preferences that govern every interaction between a business and its customers.

The Business Brain is **configuration, not execution**. It defines *what* a business allows, requires, and prohibits. It does not execute transactions, manage state machines, or replace authorization.

### What the Business Brain IS

- A versioned container of structured operational configuration
- The authoritative source for business-specific rules and policies
- A governance mechanism requiring human approval before activation
- A deterministic configuration that can be evaluated reproducibly
- A historical record linking every transaction to the rules that governed it

### What the Business Brain is NOT

| It must NOT become | Reason |
|---|---|
| An unrestricted AI agent | AI proposes; Brain governs; humans approve |
| A generic database of arbitrary JSON | Structured schema with typed fields and validation |
| A workflow engine | Workflow orchestration is a separate layer |
| An authorization replacement | Authorization resolves from identity + membership + permissions |
| A payment processor | Payment execution is an adapter concern |
| A calendar provider | Calendar integration is an adapter concern |
| A transaction state machine | State machines are authoritative for transaction state |
| An uncontrolled code execution engine | No arbitrary executable expressions |

---

## 2. Architectural Boundaries

```
┌─────────────────────────────────────────────────────────────────┐
│                        FIELDed Architecture                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Agent Layer                                                     │
│  ├── Discovery AI ──────── interprets customer intent            │
│  ├── Business Assistant ── proposes Brain configuration          │
│  ├── Enquiry Agent ─────── qualifies/interprets enquiries        │
│  ├── Quote Assistant ───── drafts quote explanations             │
│  └── Communication Asst ── drafts responses within policy        │
│       │                                                          │
│       ▼                                                          │
│  Business Brain ─────────── governed configuration/policy        │
│  ├── Versioned rules                                             │
│  ├── Classification taxonomy                                     │
│  ├── Condition evaluation                                        │
│  └── Conflict detection                                          │
│       │                                                          │
│       ▼                                                          │
│  Deterministic Decision Service ─── evaluates rules → decision   │
│  ├── Condition evaluation engine                                 │
│  ├── Rule scope resolution                                       │
│  ├── Conflict detection                                          │
│  └── Result structure (ALLOW/DENY/ESCALATE/etc.)                │
│       │                                                          │
│       ▼                                                          │
│  Authorization Layer ──────── permits/denies based on identity   │
│  ├── JWT authentication                                          │
│  ├── Business membership                                         │
│  ├── Role-based permissions                                      │
│  └── Tenant isolation                                            │
│       │                                                          │
│       ▼                                                          │
│  Workflow Orchestration ───── coordinates multi-step processes   │
│  ├── Enquiry lifecycle                                           │
│  ├── Booking lifecycle                                           │
│  ├── Quote lifecycle                                             │
│  └── Review eligibility                                          │
│       │                                                          │
│       ▼                                                          │
│  Execution Adapters ────────── performs external actions         │
│  ├── AI Provider (complete, structured_output)                   │
│  ├── Email Provider                                              │
│  ├── SMS Provider                                                │
│  ├── Calendar Provider                                           │
│  ├── Storage Provider                                            │
│  └── Payment Provider (future)                                   │
│       │                                                          │
│       ▼                                                          │
│  Audit / Evidence ───────────── records everything               │
│  ├── AuditEvent                                                  │
│  ├── Evidence                                                    │
│  ├── Provenance tracking                                         │
│  └── Historical reconstruction                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Boundary Contract

| Layer | Responsibility | Must NOT |
|---|---|---|
| **Agent** | Interpret, extract, classify, propose, draft | Make authoritative decisions |
| **Business Brain** | Store governed configuration | Execute transactions or manage state |
| **Decision Service** | Evaluate rules deterministically | Modify state or bypass authorization |
| **Authorization** | Permit/deny based on identity | Evaluate business rules |
| **Workflow** | Orchestrate multi-step processes | Override Brain configuration |
| **Execution Adapter** | Perform external actions | Make business decisions |
| **Audit/Evidence** | Record all meaningful actions | Modify any other layer |

---

## 3. Universal Rule System

### 3.1 Rule Ontology

```
Rule
├── id: UUID (primary key)
├── brain_version_id: UUID (FK → BrainVersion)
├── classification: RuleClassification (e.g., PRICING, AVAILABILITY, POLICY)
├── rule_type: str (specific type within classification)
├── rule_subtype: str | null (further specialization)
├── name: str (human-readable)
├── description: str | null
├── conditions: RuleConditionGroup (JSONB — deterministic evaluation)
├── actions: RuleAction[] (JSONB — deterministic outcomes)
├── scope: RuleScope (BUSINESS | SERVICE | SERVICE_OFFER | LOCATION | etc.)
├── scope_entity_id: UUID | null (the specific entity this rule targets)
├── priority: int (higher = evaluated first within same scope)
├── status: RuleStatus (DRAFT | ACTIVE | INACTIVE | ARCHIVED)
├── source: RuleSource (HUMAN | AI_PROPOSAL | IMPORT | TEMPLATE | SYSTEM)
├── provenance: RuleProvenance (JSONB — origin details)
├── effective_from: datetime | null
├── effective_until: datetime | null
├── is_active: bool
├── created_at: datetime
├── updated_at: datetime
└── deleted_at: datetime | null
```

### 3.2 Rule Types

| Concept | Definition |
|---|---|
| **Rule** | A single operational constraint or permission within a Brain version |
| **RuleType** | Classification-level category (e.g., `minimum_notice`, `cancellation_window`) |
| **RuleSubtype** | Optional specialization (e.g., `cancellation_window.customer_initiated`) |
| **RuleCondition** | A single deterministic test (field, operator, value) |
| **RuleConditionGroup** | A set of conditions combined with AND/OR/NOT, supporting nesting |
| **RuleAction** | The deterministic outcome when conditions are met |
| **RuleScope** | The entity level at which this rule operates |
| **RulePriority** | Integer ordering within same classification + scope |
| **RuleStatus** | Lifecycle state of the rule itself |
| **RuleSource** | How the rule was originally created |
| **RuleProvenance** | Complete origin metadata (who/what proposed it, confidence, timestamps) |

### 3.3 Design Tradeoff: Structured Rules vs. Arbitrary JSON

**Chosen approach**: Structured rules with typed JSONB configuration.

**Rejected alternatives**:
1. **Pure arbitrary JSON** — No validation, no deterministic evaluation, no conflict detection. Rejected because it makes the system unpredictable and unauditable.
2. **Fully normalized rule tables** — Every rule type gets its own table with typed columns. Rejected because it requires schema changes for every new rule type, making the system rigid and slow to extend.
3. **Executable rule expressions** — Arbitrary code/expressions evaluated at runtime. Rejected because it creates a code execution engine, violating the core principle that Brain is configuration not execution.

**Tradeoff accepted**: JSONB provides flexibility for diverse rule types while the structured envelope (classification, conditions, actions, scope, priority) provides deterministic evaluation, conflict detection, and auditability. The schema validates the envelope; the JSONB validates the payload per classification.

---

## 4. Condition System

### 4.1 Operators

| Operator | Applicable Types | Example |
|---|---|---|
| `EQUALS` | string, number, boolean, date | `service_category EQUALS "electrical"` |
| `NOT_EQUALS` | string, number, boolean, date | `customer_type NOT_EQUALS "vip"` |
| `GREATER_THAN` | number, date | `enquiry_value GREATER_THAN 500` |
| `LESS_THAN` | number, date | `notice_hours LESS_THAN 24` |
| `GREATER_OR_EQUAL` | number, date | `notice_hours GREATER_OR_EQUAL 72` |
| `LESS_OR_EQUAL` | number, date | `party_size LESS_OR_EQUAL 10` |
| `IN` | set | `service_category IN ["electrical", "plumbing"]` |
| `NOT_IN` | set | `day_of_week NOT_IN ["saturday", "sunday"]` |
| `CONTAINS` | string, list | `tags CONTAINS "urgent"` |
| `NOT_CONTAINS` | string, list | `tags NOT_CONTAINS "excluded"` |
| `IS_EMPTY` | any | `special_requirements IS_EMPTY` |
| `IS_NOT_EMPTY` | any | `customer_phone IS_NOT_EMPTY` |
| `BETWEEN` | number, date | `enquiry_value BETWEEN [100, 1000]` |
| `BEFORE` | date | `requested_date BEFORE 2026-12-25` |
| `AFTER` | date | `requested_date AFTER 2026-01-01` |

### 4.2 Logical Combinators

```
RuleConditionGroup
├── operator: "AND" | "OR" | "NOT"
├── conditions: RuleCondition[]
└── groups: RuleConditionGroup[] (nested)
```

- Groups support arbitrary nesting
- `NOT` applies to the entire group (De Morgan's for distribution)
- Empty condition group = always true (no constraints)
- Maximum nesting depth: 5 (configurable)

### 4.3 Allowed Fields

Fields are defined per classification. Each classification declares its allowed condition fields with types:

```python
ALLOWED_FIELDS = {
    "pricing": {
        "service_category": "string",
        "enquiry_value": "number",
        "customer_type": "string",
        "service_offer_id": "string",
        "delivery_mode": "string",
        "location": "string",
        "day_of_week": "string",
        "is_holiday": "boolean",
        # ... extensible per business needs
    },
    "availability": {
        "day_of_week": "string",
        "date": "date",
        "time": "string",
        "service_offer_id": "string",
        "notice_hours": "number",
        "max_bookings_per_day": "number",
        # ...
    },
    # ... each classification defines its own field schema
}
```

### 4.4 Validation Rules

- Conditions referencing undefined fields → **REJECTED** at validation time
- Conditions with type mismatches (e.g., `GREATER_THAN` on string) → **REJECTED**
- Conditions with null values where null is not permitted → **REJECTED**
- Unsupported operators for a field type → **REJECTED**
- Nested groups exceeding max depth → **REJECTED**

### 4.5 Deterministic Evaluation

- Same input + same rules = same output, always
- No time-dependent implicit behavior (explicit `effective_from`/`effective_until` only)
- No external state dependencies during evaluation
- Evaluation is a pure function: `evaluate(rules, context) → EvaluationResult`

---

## 5. Actions and Decisions

### 5.1 Separation of Concerns

| Layer | Role | Example |
|---|---|---|
| **Configuration** | Brain stores what the business wants | "Minimum 24-hour notice" |
| **Rule Evaluation** | Decision service checks conditions | "This enquiry has 12-hour notice → condition met" |
| **Decision** | Deterministic outcome produced | `REQUIRE_INFORMATION` with message |
| **Workflow Action** | Orchestrator decides next step | "Send information request to customer" |
| **External Execution** | Adapter performs the action | "Email sent via email provider" |

### 5.2 Deterministic Outcomes

| Outcome | Meaning | Layer Responsible |
|---|---|---|
| `ALLOW` | Operation is permitted | Decision Service |
| `DENY` | Operation is prohibited | Decision Service |
| `REQUIRE_INFORMATION` | Additional data needed before decision | Decision Service |
| `REQUIRE_APPROVAL` | Human approval required | Decision Service |
| `ESCALATE` | Human must handle (conflict, ambiguity) | Decision Service |
| `NOTIFY` | Operation allowed but notification triggered | Decision Service → Workflow |
| `PAUSE` | Operation suspended pending external event | Decision Service → Workflow |
| `ROUTE` | Direct to specific handler/person | Decision Service → Workflow |
| `SET_VALUE` | Set a derived value (e.g., surcharge amount) | Decision Service |
| `RESTRICT` | Partially allow with constraints | Decision Service |

### 5.3 Outcome Rules

- Decision Service produces outcomes only — it does not execute
- Workflow layer interprets outcomes and orchestrates actions
- Execution adapters perform external side effects
- No outcome bypasses authorization

---

## 6. Rule Scope + Precedence

### 6.1 Scope Hierarchy

```
BUSINESS          (broadest — applies to entire business)
  └── SERVICE     (applies to a service category)
      └── SERVICE_OFFER  (applies to a specific offer)
          └── LOCATION   (applies to a specific location)
```

Additional contextual scopes:

| Scope | Applies When |
|---|---|
| `CUSTOMER_TYPE` | Customer matches a type (e.g., VIP, new, returning) |
| `MEMBER_ROLE` | Acting member has a specific role |
| `ENQUIRY` | Specific enquiry context |
| `BOOKING` | Specific booking context |
| `TRANSACTION` | Any transaction context |
| `WORKFLOW` | Specific workflow step |

### 6.2 Precedence Resolution

**Rule**: More specific scope wins. Equal specificity → higher priority wins.

```
Resolution order:
1. SERVICE_OFFER + LOCATION (most specific)
2. SERVICE_OFFER
3. SERVICE + LOCATION
4. SERVICE
5. BUSINESS + LOCATION
6. BUSINESS (broadest)
```

Within same scope level:
- Higher `priority` value wins
- Equal priority → **CONFLICT DETECTED** → escalate

### 6.3 Conflict Handling

The system must **never silently choose** between contradictory rules.

**Example**:
- Business rule: "24-hour minimum notice" (scope: BUSINESS, priority: 10)
- Premium service rule: "72-hour minimum notice" (scope: SERVICE_OFFER, priority: 10)

**Resolution**: SERVICE_OFFER scope is more specific → 72-hour rule applies. No conflict — this is deterministic specificity resolution.

**True conflict example**:
- Rule A: "Allow same-day bookings" (scope: SERVICE_OFFER X, priority: 10)
- Rule B: "Prohibit same-day bookings" (scope: SERVICE_OFFER X, priority: 10)

**Resolution**: Same scope, same priority, contradictory outcomes → `CONFLICT_DETECTED` → `ESCALATE` to human review.

### 6.4 Conflict Detection at Validation Time

When a new rule is proposed or an existing rule is modified:
1. Scan all active rules in the same Brain version
2. Identify rules with overlapping scope + classification
3. Evaluate whether outcomes contradict
4. If contradiction detected → warn at validation time
5. If contradiction reaches runtime → escalate

---

## 7. Versioning + Governance

### 7.1 Entities

| Entity | Purpose | Current Status |
|---|---|---|
| `BusinessBrain` | 1:1 with Business. Container for all versions. Tracks `active_version_id` | **IMPLEMENTED** (model exists) |
| `BrainVersion` | Versioned snapshot of configuration. Has status lifecycle | **IMPLEMENTED** (model + lifecycle) |
| `BusinessRule` | Structured rule within a version | **IMPLEMENTED** (model exists) |

### 7.2 Version Lifecycle

```
Standard path:  DRAFT → VALIDATING → REVIEW → APPROVED → ACTIVE → SUPERSEDED
Shortcut path:  DRAFT → REVIEW (manual rules that skip system validation)
```

| Status | Meaning | Allowed Transitions |
|---|---|---|
| `DRAFT` | Being edited, not yet submitted | → VALIDATING, → REVIEW |
| `VALIDATING` | System validation in progress | → REVIEW, → DRAFT (if validation fails) |
| `REVIEW` | Awaiting human approval | → APPROVED, → DRAFT (if rejected) |
| `APPROVED` | Approved, ready for activation | → ACTIVE |
| `ACTIVE` | Currently governing the business | → SUPERSEDED |
| `SUPERSEDED` | Replaced by newer active version | Terminal state |

**DRAFT → REVIEW shortcut**: When rules are created manually (not by AI), they may skip the VALIDATING step and go directly to REVIEW. System validation is only required for AI-generated rules that need schema and consistency checking.

### 7.3 Governance Rules

- **Immutable ACTIVE versions**: Once ACTIVE, a BrainVersion's configuration cannot be modified. Changes require a new version.
- **Single active version**: Only one BrainVersion per BusinessBrain can be ACTIVE at any time.
- **Automatic superseding**: When a new version becomes ACTIVE, the previous ACTIVE version automatically becomes SUPERSEDED.
- **Version comparison**: Any two versions can be compared to identify rule additions, modifications, deletions.
- **Rollback**: Activating a previous non-SUPERSEDED version is permitted (creates a new activation event).
- **Concurrent edits**: Multiple DRAFT versions can exist simultaneously. Only one can progress through the pipeline at a time (first to reach REVIEW locks the pipeline).
- **Effective dates**: A version can specify `effective_from` and `effective_until` for time-bounded activation.
- **Historical reproducibility**: Every transaction stores `brain_version_id`. Given a brain_version_id + rules at that version, any decision can be reproduced.

---

## 8. AI → Business Brain Pipeline

```
Business owner (natural language)
    │
    ▼
AI interpretation
    │ "I don't take bookings less than 3 days in advance"
    ▼
Structured proposal
    │ { classification: "availability", rule_type: "minimum_notice",
    │   conditions: [...], actions: [{ outcome: "DENY", ... }] }
    ▼
Schema validation
    │ Check proposal conforms to expected structure
    ▼
Semantic validation
    │ Check proposal makes business sense (no contradictions with existing rules)
    ▼
Conflict detection
    │ Check against all active rules in current version
    ▼
Human review
    │ Business owner sees: "AI proposes: [rule]. Conflicts: [none/list]"
    ▼
Approval
    │ Owner approves, modifies, or rejects
    ▼
Brain version (new DRAFT or update to existing DRAFT)
    │
    ▼
Validation → Review → Approval → Activation
```

### 8.1 AI Constraints

- AI **never** directly activates operational rules
- AI **never** transitions a BrainVersion to ACTIVE
- AI proposals always carry provenance (source, confidence, timestamp)
- Confidence alone is **not** an authority mechanism — even 99% confidence requires human approval
- AI proposals can be edited by humans before approval
- Rejected proposals are recorded (not silently discarded)
- Re-proposals after rejection carry reference to original rejection

### 8.2 Proposal Structure

```python
AIProposal
├── id: UUID
├── brain_version_id: UUID
├── source_text: str (original natural language)
├── proposed_rule: dict (structured rule)
├── classification: str
├── confidence: float (0.0 - 1.0)
├── validation_status: PENDING | VALID | INVALID | CONFLICT
├── conflicts: list[ConflictDetail]
├── status: PROPOSED | ACCEPTED | MODIFIED | REJECTED
├── human_edit: dict | null (modified version if edited)
├── rejection_reason: str | null
├── proposed_by: UUID (user who initiated)
├── created_at: datetime
└── resolved_at: datetime | null
```

---

## 9. Human Governance

### 9.1 Approval Policy

| Factor | Description |
|---|---|
| **Role-based approval** | Only members with sufficient role level can approve Brain changes |
| **Rule sensitivity** | Some classifications require higher approval (e.g., pricing changes may require owner) |
| **Single approval** | Default: one qualified approver is sufficient |
| **Multi-approval** | Configurable: some rules may require N approvers |
| **Approval timeout** | Pending approvals expire after configurable duration (default: 7 days) |
| **Rejection** | Any qualified approver can reject; rejection returns version to DRAFT |
| **Escalation** | If no approver acts within escalation threshold, notify higher roles |
| **Re-review** | Any modification to a version in REVIEW resets it to DRAFT |

### 9.2 Relationship: Member → Role → Permission → ApprovalPolicy

```
BusinessMember
├── user_id: UUID
├── business_id: UUID
└── role: str (owner | admin | staff)

Role
├── name: str
├── level: int
└── permissions: list[Permission]

Permission
├── BRAIN_VIEW
├── BRAIN_CREATE_RULE
├── BRAIN_EDIT_RULE
├── BRAIN_PROPOSE_RULE (via AI)
├── BRAIN_APPROVE
├── BRAIN_ACTIVATE
├── BRAIN_ARCHIVE
├── BRAIN_ROLLBACK
├── BRAIN_EVALUATE
├── BRAIN_INSPECT_AUDIT
└── MANAGE_MEMBERS

ApprovalPolicy
├── business_id: UUID
├── classification: str | null (null = all classifications)
├── required_role: str
├── required_count: int (default: 1)
├── timeout_hours: int (default: 168)
└── escalation_role: str | null
```

---

## 10. Runtime Evaluation Contract

### 10.1 Evaluation Result

Evaluation is **not** true/false. It produces a structured result:

```python
EvaluationResult
├── outcome: str (ALLOW | DENY | REQUIRE_INFORMATION | REQUIRE_APPROVAL |
│                 ESCALATE | NOTIFY | PAUSE | ROUTE | SET_VALUE | RESTRICT)
├── matched_rules: list[MatchedRule]
│   ├── rule_id: UUID
│   ├── classification: str
│   ├── scope: str
│   ├── priority: int
│   └── matched_conditions: list[ConditionResult]
├── rejected_rules: list[RejectedRule]
│   ├── rule_id: UUID
│   └── rejection_reason: str
├── conflicts: list[ConflictDetail]
│   ├── rule_a_id: UUID
│   ├── rule_b_id: UUID
│   └── description: str
├── required_information: list[InformationRequest]
│   ├── field: str
│   ├── reason: str
│   └── message: str
├── required_actions: list[ActionItem]
│   ├── action: str
│   ├── target: str
│   └── parameters: dict
├── approval_required: bool
├── approval_details: ApprovalDetails | null
├── escalation_required: bool
├── escalation_reason: str | null
├── brain_version_id: UUID
├── evaluated_at: datetime
├── provenance: EvaluationProvenance
└── reproducible: bool (always True — deterministic)
```

### 10.2 Determinism Guarantee

Given:
- The same BrainVersion (frozen at activation time)
- The same evaluation context (enquiry data, customer data, service offer data)
- The same timestamp (for time-dependent conditions)

The evaluation **always** produces the same result. This enables:
- Historical reconstruction of any decision
- Audit verification
- Dispute resolution
- Testing and debugging

---

## 11. Workflow + Agent Relationship

```
┌──────────────────────────────────────────────────────────────┐
│                       Execution Flow                          │
│                                                               │
│  Agent                                                        │
│  ├── Interprets customer intent                              │
│  ├── Proposes Brain configuration                            │
│  ├── Drafts responses within policy bounds                   │
│  └── Recommends actions                                      │
│       │                                                       │
│       │ (structured proposal)                                 │
│       ▼                                                       │
│  Business Brain                                               │
│  ├── Stores governed configuration                           │
│  ├── Provides rules for evaluation                           │
│  └── Maintains version history                               │
│       │                                                       │
│       │ (rules + configuration)                               │
│       ▼                                                       │
│  Deterministic Decision Service                               │
│  ├── Evaluates conditions against context                    │
│  ├── Resolves scope + priority                               │
│  ├── Detects conflicts                                       │
│  └── Produces EvaluationResult                               │
│       │                                                       │
│       │ (outcome: ALLOW/DENY/ESCALATE/etc.)                   │
│       ▼                                                       │
│  Authorization                                                │
│  ├── Verifies identity                                       │
│  ├── Checks membership                                       │
│  ├── Validates permissions                                   │
│  └── Enforces tenant isolation                               │
│       │                                                       │
│       │ (permitted/denied)                                    │
│       ▼                                                       │
│  Workflow                                                     │
│  ├── Orchestrates multi-step processes                       │
│  ├── Manages state machine transitions                       │
│  └── Coordinates across domains                              │
│       │                                                       │
│       │ (execution指令)                                       │
│       ▼                                                       │
│  Execution Adapter                                            │
│  ├── Performs external actions                               │
│  └── Returns results                                         │
│       │                                                       │
│       │ (completion record)                                   │
│       ▼                                                       │
│  Audit / Evidence                                             │
│  ├── Records every meaningful action                         │
│  ├── Links to Brain version + rules                          │
│  └── Enables historical reconstruction                       │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

**Critical constraint**: Agents must not bypass the Deterministic Decision Service or Authorization. Every agent proposal flows through the full pipeline.

---

## 12. Failure + Safe-Fallback Model

| Failure Scenario | Safe Behavior |
|---|---|
| AI fails | Fall back to manual configuration. No rule changes without human input. |
| AI returns malformed output | Reject at schema validation. Log for analysis. No partial application. |
| Rule validation fails | Return to DRAFT with specific validation errors. No activation. |
| Rules conflict at runtime | ESCALATE outcome. Human review required. Do not silently choose. |
| Brain version unavailable | DENY by default. Business without active Brain uses most restrictive defaults. |
| Approval rejected | Return to DRAFT. Notify proposer. Allow re-proposal. |
| Authorization fails | 403 response. Log attempt. No information leakage. |
| Deterministic evaluation fails | ESCALATE. Log full context. Do not fall back to AI decision. |
| Database fails | Standard error handling. No state mutation. Retry with backoff. |
| External integration fails | Adapter-level retry. Circuit breaker. Notify business. No data loss. |
| Required information missing | REQUIRE_INFORMATION outcome. Specify what's needed. Pause workflow. |
| Rule expires | Mark inactive. Evaluate next matching rule. If no alternative → ESCALATE. |
| Activation fails | Version stays in APPROVED. Alert business owner. No partial activation. |

**Core principle**: Never silently fall back to AI decisions. Every fallback is either deterministic (DENY/ESCALATE) or requires human intervention.

---

## 13. Database Specification (Proposed)

> **Note**: No migrations created. This is a proposal for implementation.

### 13.1 Existing Entities (Already Implemented)

| Entity | Table | Status |
|---|---|---|
| `BusinessBrain` | `business_brains` | **IMPLEMENTED** |
| `BrainVersion` | `brain_versions` | **IMPLEMENTED** — needs extension |
| `BusinessRule` | `business_rules` | **IMPLEMENTED** — needs extension |

### 13.2 Proposed Extensions

**BrainVersion extensions**:
- Add `approved_by: UUID | null` (FK → User)
- Add `approved_at: datetime | null`
- Add `activated_by: UUID | null` (FK → User)
- Add `activated_at: datetime | null`
- Add `effective_from: datetime | null`
- Add `effective_until: datetime | null`
- Add `rejection_reason: str | null`
- Add `parent_version_id: UUID | null` (FK → BrainVersion, for diff tracking)

**BusinessRule extensions**:
- Restructure `rule_data` JSONB to conform to classification-specific schemas
- Add `classification: str` (normalized from rule_type)
- Add `scope: str` (BUSINESS | SERVICE | SERVICE_OFFER | LOCATION)
- Add `scope_entity_id: UUID | null`
- Add `conditions: JSONB` (RuleConditionGroup structure)
- Add `actions: JSONB` (RuleAction array)
- Add `source: str` (HUMAN | AI_PROPOSAL | IMPORT | TEMPLATE | SYSTEM)
- Add `provenance: JSONB` (origin metadata)
- Add `effective_from: datetime | null`
- Add `effective_until: datetime | null`

### 13.3 New Entities (Proposed)

**AIProposal**:
```
ai_proposals
├── id: UUID PK
├── brain_version_id: UUID FK → brain_versions
├── source_text: TEXT
├── proposed_rule: JSONB
├── classification: str
├── confidence: float
├── validation_status: str
├── conflicts: JSONB
├── status: str
├── human_edit: JSONB | null
├── rejection_reason: TEXT | null
├── proposed_by: UUID FK → users
├── created_at: TIMESTAMPTZ
└── resolved_at: TIMESTAMPTZ | null
```

**ApprovalRecord**:
```
approval_records
├── id: UUID PK
├── brain_version_id: UUID FK → brain_versions
├── approver_id: UUID FK → users
├── action: str (APPROVED | REJECTED)
├── reason: TEXT | null
├── created_at: TIMESTAMPTZ
```

**EvaluationLog**:
```
evaluation_logs
├── id: UUID PK
├── business_id: UUID FK → businesses
├── brain_version_id: UUID FK → brain_versions
├── context: JSONB (input data)
├── result: JSONB (EvaluationResult)
├── triggered_by: UUID | null (enquiry_id, booking_id, etc.)
├── trigger_type: str
├── created_at: TIMESTAMPTZ
```

### 13.4 Storage Strategy Decision

**Chosen**: Hybrid model — normalized relational tables with typed JSONB.

**Rationale**:
- Core entities (Brain, Version, Rule) are normalized for queryability and integrity
- Rule conditions and actions are JSONB for flexibility within the structured envelope
- Classification-specific configuration is JSONB with schema validation at the application layer
- This avoids both rigid over-normalization and arbitrary JSON chaos

---

## 14. API Specification (Proposed)

> **Note**: No APIs implemented. This is a proposal for implementation.

### 14.1 Brain Management

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| GET | `/api/v1/brain` | Get active Brain for current business | `require_business_role("staff")` |
| GET | `/api/v1/brain/versions` | List all versions | `require_business_role("admin")` |
| GET | `/api/v1/brain/versions/{id}` | Get specific version detail | `require_business_role("admin")` |
| POST | `/api/v1/brain/versions` | Create new DRAFT version | `require_business_role("admin")` |
| GET | `/api/v1/brain/versions/{id}/compare?to={id}` | Compare two versions | `require_business_role("admin")` |

### 14.2 Rule Management

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| GET | `/api/v1/brain/versions/{id}/rules` | List rules in version | `require_business_role("staff")` |
| POST | `/api/v1/brain/versions/{id}/rules` | Create rule in DRAFT | `require_business_role("admin")` |
| PUT | `/api/v1/brain/versions/{id}/rules/{rid}` | Update rule in DRAFT | `require_business_role("admin")` |
| DELETE | `/api/v1/brain/versions/{id}/rules/{rid}` | Remove rule from DRAFT | `require_business_role("admin")` |
| POST | `/api/v1/brain/versions/{id}/rules/{rid}/validate` | Validate a rule | `require_business_role("admin")` |

### 14.3 AI Proposals

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| POST | `/api/v1/brain/versions/{id}/propose` | Submit NL for AI proposal | `require_business_role("admin")` |
| GET | `/api/v1/brain/versions/{id}/proposals` | List pending proposals | `require_business_role("admin")` |
| PUT | `/api/v1/brain/proposals/{pid}` | Edit/accept/reject proposal | `require_business_role("admin")` |

### 14.4 Governance

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| POST | `/api/v1/brain/versions/{id}/submit-review` | Submit for review | `require_business_role("admin")` |
| POST | `/api/v1/brain/versions/{id}/approve` | Approve version | `require_business_role("owner")` |
| POST | `/api/v1/brain/versions/{id}/reject` | Reject version | `require_business_role("owner")` |
| POST | `/api/v1/brain/versions/{id}/activate` | Activate approved version | `require_business_role("owner")` |
| POST | `/api/v1/brain/versions/{id}/archive` | Archive a version | `require_business_role("owner")` |
| POST | `/api/v1/brain/rollback` | Rollback to previous version | `require_business_role("owner")` |

### 14.5 Evaluation

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| POST | `/api/v1/brain/evaluate` | Evaluate rules against context | Internal service call |
| GET | `/api/v1/brain/evaluations` | List evaluation history | `require_business_role("admin")` |
| GET | `/api/v1/brain/evaluations/{id}` | Get specific evaluation | `require_business_role("admin")` |

### 14.6 Audit

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| GET | `/api/v1/brain/audit` | Brain audit history | `require_business_role("admin")` |
| GET | `/api/v1/brain/provenance/{rule_id}` | Rule provenance chain | `require_business_role("admin")` |

---

## 15. Extensibility Model

The Business Brain classification system is designed to accommodate future modules without core redesign:

| Future Module | How It Extends | Core Changes Required |
|---|---|---|
| **Documentation** | New classification `DOCUMENTATION` with rules about required/uploaded docs | None — add classification |
| **Resource Allocation** | New classification `RESOURCE` with rules about staff/equipment assignment | None — add classification |
| **SLA** | New classification `SLA` with response time, resolution time rules | None — add classification |
| **Follow-up** | New classification `FOLLOWUP` with post-service check-in rules | None — add classification |
| **Lead Routing** | New classification `ROUTING` with enquiry distribution rules | None — add classification |
| **Case Management** | Enquiry classification already exists; extend with case-specific subtypes | Minor — extend conditions |
| **Industry Compliance** | New classifications per compliance domain; industry-specific condition fields | None — add classification + fields |

### Extensibility Guarantees

1. **No core architecture changes** needed to add a new classification
2. **No schema migrations** needed for classification-specific configuration (JSONB)
3. **New condition fields** can be added per classification without affecting existing ones
4. **New outcome types** can be added to the evaluation result without breaking existing consumers
5. **New scopes** can be added to the scope hierarchy without restructuring

### What Extensibility Does NOT Mean

- Adding classifications does not automatically create UI, API, or workflow integration
- Each new classification requires: schema definition, validation rules, evaluation logic, API endpoints, frontend support
- Extensibility means the *core architecture* doesn't break — not that new features are free

---

## 16. Architectural Self-Review

### Challenge Questions

| # | Question | Answer |
|---|---|---|
| 1 | Can a new business vertical use Brain without modifying core architecture? | **YES** — Classifications are extensible. New verticals add classifications + condition fields, not core changes. |
| 2 | Can a non-technical business owner configure rules? | **YES** — via AI proposal pipeline (natural language → structured rule → approval). Direct configuration also possible via structured UI. |
| 3 | Can AI propose configuration without becoming authoritative? | **YES** — AI produces proposals. Proposals require schema validation + human approval before activation. |
| 4 | Can deterministic services reproduce decisions? | **YES** — Same BrainVersion + same context = same result. Evaluation is a pure function. |
| 5 | Can rule conflicts be detected safely? | **YES** — Conflict detection at validation time (proposal) and runtime (evaluation). Conflicts escalate, never silently resolve. |
| 6 | Can historical decisions be reconstructed? | **YES** — Every transaction references brain_version_id. EvaluationLogs preserve full context + result. |
| 7 | Can every change be traced? | **YES** — Every rule has source + provenance. Every version has approval records. Every activation is audited. |
| 8 | Can authorization prevent unauthorized changes? | **YES** — Role-based permissions on every Brain operation. Tenant isolation enforced at repository layer. |
| 9 | Can future rule types be added? | **YES** — New classifications added without core changes. JSONB allows flexible rule_data. |
| 10 | Can the system fail safely? | **YES** — Every failure mode has explicit safe behavior. No silent fallback to AI decisions. |
| 11 | Does Brain remain configuration/policy rather than execution? | **YES** — Brain stores rules. Decision Service evaluates. Workflow orchestrates. Adapters execute. |
| 12 | Does it preserve existing state machines? | **YES** — Brain configures policy around state machines. State machines remain authoritative for state. |
| 13 | Does it preserve tenant isolation? | **YES** — Brain is 1:1 with Business. All queries tenant-scoped. No cross-tenant access possible. |
| 14 | Does it preserve Service Offer as transaction anchor? | **YES** — Rules can scope to SERVICE_OFFER. ServiceOffer remains the bridge between intent and capability. |
| 15 | Can it support multiple industries without industry-specific hacks? | **YES** — Classifications are generic. Condition fields are per-classification. No industry hardcoded in core. |

---

## 17. Open Questions

| # | Question | Impact | Status |
|---|---|---|---|
| 1 | Should BrainVersion support branching (multiple DRAFT versions from same base)? | Complexity vs. flexibility | UNRESOLVED |
| 2 | Should evaluation results be stored permanently or only on demand? | Storage cost vs. audit completeness | UNRESOLVED — leaning toward permanent for audit |
| 3 | Should there be a maximum number of active rules per Brain version? | Performance vs. business freedom | UNRESOLVED |
| 4 | How should cross-version rule dependencies be handled? | Edge case but could create hidden coupling | UNRESOLVED — leaning toward prohibition |
| 5 | Should approval policies be per-business or platform-configurable? | Flexibility vs. consistency | UNRESOLVED |

---

## 18. Risks and Tradeoffs

| Risk | Severity | Mitigation |
|---|---|---|
| JSONB flexibility leads to inconsistent rule structures | Medium | Classification-specific schema validation at application layer |
| Rule evaluation performance with many rules | Medium | Indexing strategy, rule caching per active version, early termination |
| Conflict detection complexity grows with rule count | Medium | Scope-based partitioning, priority-based early resolution |
| AI proposal quality varies by provider | Low | Provider-agnostic adapter; quality controlled by validation + human review |
| Version proliferation (too many versions) | Low | Archival policy, UI filtering, version comparison tools |
| Over-engineering for early-stage product | High | Phased implementation — start with core classifications, extend as needed |

| Tradeoff | Decision | Rationale |
|---|---|---|
| Flexibility vs. Rigidity | Hybrid (structured envelope + JSONB payload) | Enough flexibility for diverse businesses; enough structure for deterministic evaluation |
| Normalization vs. JSONB | Hybrid | Core entities normalized; configuration payload JSONB |
| Simplicity vs. Completeness | Phased approach | Ship core Brain first; extend classifications incrementally |
| AI assistance vs. Manual only | AI proposes + human approves | Reduces configuration burden while maintaining authority |

---

## 19. Classification-to-Configuration Mapping

The 17 Business Brain classifications (A–Q) map to the 8 persisted configuration areas as follows:

| Classification | Persisted Config Area | Notes |
|---|---|---|
| A. Service | `service_config` | Direct mapping |
| B. Pricing | `pricing_config` | Direct mapping |
| C. Availability | `availability_config` | Direct mapping |
| D. Qualification | `qualification_config` | Direct mapping |
| E. Policy | `policy_config` | Cancellation, rescheduling, deposit policies |
| F. Booking | `policy_config` | Booking rules are policy configuration, not separate config area |
| G. Cancellation | `policy_config` | Cancellation is a policy type within policy_config |
| H. Rescheduling | `policy_config` | Rescheduling is a policy type within policy_config |
| I. Communication | `communication_config` | Direct mapping |
| J. Escalation | `policy_config` | Escalation is a policy type |
| K. Fulfilment | **Conceptual only** | Not persisted as config; governed by workflow engine |
| L. Payment | **Conceptual only** | Not persisted; handled by payment adapter |
| M. Compliance | **Conceptual only** | Not persisted; enforced by platform rules |
| N. AI Behaviour | `ai_config` (future) | Maps to ai_config when implemented |
| O. Human Approval | **Governance process** | Not configuration; part of approval workflow |
| P. Integration | **Conceptual only** | Not persisted; handled by adapter layer |
| Q. Governance | **Governance process** | Not configuration; part of Brain lifecycle itself |

**Key decisions:**
- E, F, G, H, J all map to `policy_config` — they are different policy types within the same configuration area
- K, L, M, P are conceptual classifications that guide system behavior but are not persisted as Brain configuration
- O, Q are governance processes, not configuration
- N maps to a future `ai_config` area (not yet implemented)

---

## 20. Architectural Decisions (Resolved)

These decisions were identified during the forensic verification report and resolved here.

### DECISION-1: Concurrency Strategy for Brain Version Activation

**Decision**: Use `SELECT FOR UPDATE` (pessimistic row lock) on the `business_brains` row during activation.

**Rationale**: 
- Optimistic locking (version column) would require retry logic and could fail silently
- Pessimistic locking is simpler, guarantees correctness, and activation is infrequent
- The lock scope is narrow (one business's brain row) so contention is minimal

**Implementation**: `BusinessBrainRepository.get_by_business_id_for_update()` uses `.with_for_update()`.

### DECISION-2: BusinessRule Field Structure

**Decision**: Keep `BusinessRule` as a generic model with `rule_type: str` and `rule_data: JSONB`. Do NOT create 17 separate rule tables.

**Rationale**:
- 17 tables would be massive over-engineering for an early-stage product
- JSONB with classification-specific schema validation provides flexibility without schema explosion
- The existing model already supports this pattern
- Schema validation at the application layer ensures type safety per classification

**Implementation**: Application-layer validators check `rule_data` structure based on `rule_type`.

### DECISION-3: Rescheduling Mechanism

**Decision**: Rescheduling = cancel old booking (→ CANCELLED) + create new booking. No direct RESCHEDULED state transition.

**Rationale**:
- Each booking instance has a clean, immutable lifecycle
- Audit trail is clearer: old booking shows cancellation reason = "rescheduled", new booking references old
- No need to add a RESCHEDULED state with complex transition rules
- Consistent with the principle that state machines control transaction lifecycle authoritatively

### DECISION-4: Self-Approval Policy

**Decision**: Owners (level 3) CAN self-approve Brain versions. Admins (level 2) cannot.

**Rationale**:
- Owners have full authority over their business — restricting self-approval adds friction without security benefit
- The owner is the business authority; their approval IS the business decision
- For future enterprise scenarios, a separate approval policy can be configured per Brain
- This is the simplest production-safe decision

### DECISION-5: Mandatory vs. Skippable Validation

**Decision**: VALIDATING step is mandatory for AI-generated rules, skippable for manually-created rules.

**Rationale**:
- AI-generated rules need schema validation, consistency checking, and hallucination detection
- Manually-created rules by the business owner are already "validated" by human intent
- The DRAFT → REVIEW shortcut allows manual rules to skip VALIDATING
- This is already implemented in `BRAIN_VERSION_TRANSITIONS`

### DECISION-6: Historical Brain Version Linkage

**Decision**: Every Enquiry stores `brain_version_id` (nullable FK to `brain_versions`). NULL means no active Brain at creation time.

**Rationale**:
- Enables full historical reproducibility: given a brain_version_id + rules, any decision can be reproduced
- Nullable: not all businesses have an active Brain
- SET NULL on delete: if a brain version is deleted, the enquiry remains valid
- This is the minimum viable linkage; other entities (Booking, Quote) can be added later

### DECISION-7: PricingModel Canonical Values

**Decision**: The canonical PricingModel enum is: `FIXED`, `HOURLY`, `QUOTE_REQUIRED`, `STARTING_AT`, `CUSTOM`.

**Rationale**:
- This matches the existing implementation
- `CUSTOM` is more descriptive than `custom_quote`
- `STARTING_AT` covers the "starting price" use case
- Specification documents updated to match

### DECISION-8: Brain Classification Count vs. Config Area Count

**Decision**: 17 classifications are conceptual categories; 8 config areas are persisted configuration. Not all classifications need a config area.

**Rationale**:
- Classifications help organize Brain capabilities conceptually
- Some classifications (Fulfilment, Payment, Compliance, Integration) are handled by other system layers
- Forcing 1:1 mapping would either collapse distinct concepts or create unnecessary config areas
- See Section 19 for the complete mapping

### DECISION-9: Tenant Isolation Enforcement

**Decision**: `tenant_scope()` must filter by `customer_id` or `business_id` in the WHERE clause. No exceptions.

**Rationale**:
- This is a security fix — the previous implementation computed `business_ids` but never used them
- Every model using `tenant_scope()` must have either `customer_id` or `business_id` column
- Cross-tenant access must be impossible by design, not by convention
- Regression tests verify this behavior
