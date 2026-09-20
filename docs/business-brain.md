# FIELDed — Business Brain

## Overview

The Business Brain is the versioned operational rule system for each business. It represents the business's configured knowledge and rules.

## Architecture

```
Business
  └── BusinessBrain (1:1)
        └── BrainVersion (1:N)
              └── BusinessRule (1:N)
```

## Brain Areas

Each Brain version contains structured configuration for:

1. **Identity** — Who the business is
2. **Services** — What it provides
3. **Pricing** — How prices are determined
4. **Availability** — When/how services can be delivered
5. **Qualification** — What information is required from customers
6. **Policies** — What the business allows (cancellation, refunds, etc.)
7. **Escalation** — When humans must intervene
8. **Communication** — How customer communication should be handled

Configuration is stored as JSONB fields on the BrainVersion model.

## Version Lifecycle

```
DRAFT → VALIDATING → REVIEW → APPROVED → ACTIVE → SUPERSEDED
```

- Only one version is ACTIVE at a time
- New activations supersede the previous active version
- Historical transactions retain reference to their governing version

## Immutability Enforcement

BrainVersions are mutable **only** while in DRAFT status. Once a version reaches REVIEW, APPROVED, ACTIVE, or SUPERSEDED, its configuration and rules are immutable. Any attempt to mutate a non-DRAFT version raises a `DomainError`. The correct modification path for a non-DRAFT version is to create a new DRAFT version.

## Structural Validation

All Brain configuration must pass structural validation before entering REVIEW or becoming APPROVED/ACTIVE. This is mandatory for every provenance (HUMAN, AI_PROPOSAL, IMPORT, TEMPLATE, SYSTEM, INTEGRATION) — there is no skip path. Validation checks: required fields, supported configuration area, supported rule type, condition structure, operator validity, action structure, enum values, scope, priority, effective dates, and schema version. Invalid configuration fails safely with structured error details.

## Rule-Type Registry

A code-level registry (`app/domain/business/registry.py`) defines all supported rule and configuration types. It is the single authoritative source for type identifier, category, required/optional fields, supported operators, supported scopes, and schema version. Unknown types are rejected deterministically. The registry is not a database table — it is a typed Python singleton.

## Schema Versioning

All configuration and rule data carries a `schema_version` field. The current schema version is `"1.0"`. Validation rejects unsupported schema versions rather than interpreting them opportunistically. The `BusinessRuleService.add_rule()` method injects the current schema version automatically when not present.

## Approval Policy

Approval authority is represented explicitly via the `ApprovalPolicy` model (`app/domain/business/approval.py`). The default policy permits owner self-approval (matching the frozen architecture decision). Alternative presets (STRICT, ENTERPRISE) are available for future per-business configuration. The policy model covers: who may approve, whether self-approval is permitted, number of required approvals, sensitive rule types requiring elevated approval, and approval timeout.

## Business Rules

Rules are structured objects within a Brain version:
- `rule_type`: must be a known type in the rule-type registry
- `rule_data`: JSON configuration for the rule (validated against registry)
- `priority`: non-negative integer controlling execution order
- `scope`: BUSINESS, SERVICE, SERVICE_OFFER, or LOCATION
- `schema_version`: carried on every rule for forward compatibility
- `is_active`: can be toggled without deleting
