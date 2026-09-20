# FIELDed — Authorization Model

> **Status**: EXTENDS EXISTING [docs/authorization.md](authorization.md)  
> **Phase**: Architecture + Specification Only  
> **Last Updated**: 2026-09-19

---

## Overview

This document extends the existing authorization model with precise permission definitions for Business Brain operations, expanded role evaluation, and the relationship between roles, permissions, and approval policies.

**Core principle**: Authorization is resolved server-side from authenticated identity and database relationships. The frontend never controls access decisions.

---

## 1. Role Architecture

### 1.1 Existing Roles (Implemented)

| Role | Level | Scope | Current Permissions |
|---|---|---|---|
| `customer` | — | Own data | Search, enquire, view own enquiries/conversations/bookings |
| `owner` | 3 | Business | Full business control |
| `admin` | 2 | Business | Manage services, handle enquiries |
| `staff` | 1 | Business | View and respond to enquiries |
| `platform_admin` | — | Platform | FIELDed platform management (future) |

### 1.2 Evaluated Roles (Future)

The following roles are evaluated for future necessity. They are not confirmed as final:

| Proposed Role | Level | Rationale | Assessment |
|---|---|---|---|
| `manager` | 3 | Between owner and admin | **REJECTED for now** — owner and admin cover this. May be needed when businesses scale. |
| `operations` | 2 | Operations-specific focus | **FUTURE** — when Brain operations become complex |
| `sales` | 1 | Sales/enquiry focus | **FUTURE** — when quote engine is implemented |
| `support` | 1 | Customer support focus | **FUTURE** — when support workflows exist |
| `viewer` | 0 | Read-only access | **USEFUL** — for stakeholders who need visibility without action |

**Decision**: Start with existing roles (owner/admin/staff). Add `viewer` when needed. Evaluate additional roles when Brain operations require finer granularity.

---

## 2. Permission Matrix

### 2.1 Business Brain Permissions

| Permission | Description | owner | admin | staff | viewer |
|---|---|---|---|---|---|
| `BRAIN_VIEW` | View Brain configuration and versions | ✅ | ✅ | ✅ | ✅ |
| `BRAIN_CREATE_RULE` | Create new rules in DRAFT versions | ✅ | ✅ | ❌ | ❌ |
| `BRAIN_EDIT_RULE` | Edit existing rules in DRAFT versions | ✅ | ✅ | ❌ | ❌ |
| `BRAIN_PROPOSE_RULE` | Submit NL for AI Brain proposals | ✅ | ✅ | ❌ | ❌ |
| `BRAIN_APPROVE` | Approve Brain versions for activation | ✅ | ❌ | ❌ | ❌ |
| `BRAIN_ACTIVATE` | Activate approved Brain versions | ✅ | ❌ | ❌ | ❌ |
| `BRAIN_ARCHIVE` | Archive Brain versions | ✅ | ❌ | ❌ | ❌ |
| `BRAIN_ROLLBACK` | Rollback to previous Brain version | ✅ | ❌ | ❌ | ❌ |
| `BRAIN_EVALUATE` | Trigger rule evaluation (debugging) | ✅ | ✅ | ❌ | ❌ |
| `BRAIN_INSPECT_AUDIT` | View Brain audit history | ✅ | ✅ | ❌ | ❌ |

### 2.2 Service Offer Permissions

| Permission | Description | owner | admin | staff | viewer |
|---|---|---|---|---|---|
| `SERVICE_VIEW` | View service offers | ✅ | ✅ | ✅ | ✅ |
| `SERVICE_CREATE` | Create new service offers | ✅ | ✅ | ❌ | ❌ |
| `SERVICE_EDIT` | Edit service offers | ✅ | ✅ | ❌ | ❌ |
| `SERVICE_TRANSITION` | Change offer lifecycle state | ✅ | ✅ | ❌ | ❌ |
| `SERVICE_DELETE` | Soft-delete service offers | ✅ | ❌ | ❌ | ❌ |

### 2.3 Enquiry Permissions

| Permission | Description | owner | admin | staff | viewer |
|---|---|---|---|---|---|
| `ENQUIRY_VIEW` | View enquiries | ✅ | ✅ | ✅ | ✅ |
| `ENQUIRY_RESPOND` | Send messages in enquiries | ✅ | ✅ | ✅ | ❌ |
| `ENQUIRY_TRANSITION` | Change enquiry state | ✅ | ✅ | ✅ | ❌ |
| `ENQUIRY_CREATE_QUOTE` | Create quotes for enquiries | ✅ | ✅ | ❌ | ❌ |
| `ENQUIRY_ASSIGN` | Assign enquiry to team member | ✅ | ✅ | ❌ | ❌ |

### 2.4 Business Management Permissions

| Permission | Description | owner | admin | staff | viewer |
|---|---|---|---|---|---|
| `BUSINESS_VIEW` | View business details | ✅ | ✅ | ✅ | ✅ |
| `BUSINESS_EDIT` | Edit business profile | ✅ | ✅ | ❌ | ❌ |
| `BUSINESS_PUBLISH` | Change public status | ✅ | ❌ | ❌ | ❌ |
| `MEMBER_MANAGE` | Add/remove/modify members | ✅ | ❌ | ❌ | ❌ |
| `MEMBER_INVITE` | Invite new members | ✅ | ✅ | ❌ | ❌ |

---

## 3. Permission Resolution

### 3.1 Resolution Algorithm

```python
def check_permission(user, business_id, permission):
    # 1. Authenticate
    if not user or not user.is_active:
        raise AuthenticationError()

    # 2. Find membership
    membership = get_business_member(user.id, business_id)
    if not membership:
        raise AuthorizationError("Not a member of this business")

    # 3. Resolve role → permissions
    role_permissions = ROLE_PERMISSION_MAP[membership.role]
    if permission not in role_permissions:
        raise AuthorizationError(f"Insufficient permissions: {permission}")

    # 4. Check tenant isolation
    # (membership already scoped to business_id — tenant isolation by design)

    return True
```

### 3.2 Hierarchical Role Resolution

Roles are hierarchical. Higher roles inherit all permissions of lower roles:

```
owner (level 3) ⊇ admin (level 2) ⊇ staff (level 1) ⊇ viewer (level 0)
```

Permission check: `user_role_level >= required_role_level`

### 3.3 Customer vs. Business Authorization

```
Customer endpoints:
    → require_customer (has CustomerProfile)
    → Data scoped to customer_id == user.id

Business endpoints:
    → require_business_member (has BusinessMember)
    → require_business_role(minimum_role) for specific actions
    → Data scoped to business_id in [membership.business_ids]
```

A user can be both a customer AND a business member. The authorization context determines which identity is used.

---

## 4. Tenant Isolation Rules

### 4.1 Customer Isolation

| Resource | Isolation Rule |
|---|---|
| CustomerProfile | `customer_id == user.id` |
| Enquiries | `customer_id == user.id` |
| Conversations | Via enquiry ownership |
| Messages | Via conversation → enquiry ownership |
| Quotes | `customer_id == user.id` |
| Bookings | `customer_id == user.id` (via enquiry) |
| Reviews | `customer_id == user.id` |

### 4.2 Business Isolation

| Resource | Isolation Rule |
|---|---|
| BusinessProfile | `business_id in member.business_ids` |
| ServiceOffers | `business_id in member.business_ids` |
| BusinessBrain | `business_id in member.business_ids` |
| BrainVersions | Via Brain → business membership |
| BusinessRules | Via BrainVersion → business membership |
| Enquiries (business side) | `business_id in member.business_ids` |
| Audit events | `business_id in member.business_ids` |

### 4.3 Cross-Tenant Impossibility

Business A **cannot** access:
- Business B's Brain, rules, versions
- Business B's enquiries, customers, messages
- Business B's quotes, bookings, reviews
- Business B's audit records

This is enforced at the repository layer, not just the API layer. Every query includes tenant scoping.

---

## 5. Authorization for AI Operations

| AI Operation | Required Permission | Authority Level |
|---|---|---|
| Discovery AI (search) | None (public) | L1 |
| Business Assistant (propose rule) | `BRAIN_PROPOSE_RULE` | L3 |
| Enquiry Agent (interpret) | `ENQUIRY_VIEW` | L1 |
| Quote Assistant (draft) | `ENQUIRY_CREATE_QUOTE` | L2 |
| Communication Assistant (draft) | `ENQUIRY_RESPOND` | L2 |

AI operations always require the underlying permission for the action they're assisting with. AI cannot operate in areas where the user has no permission.

---

## 6. Brain-Specific Authorization

### 6.1 Version Lifecycle Authorization

| Action | Required Role | Required Permission |
|---|---|---|
| Create DRAFT version | admin+ | `BRAIN_CREATE_RULE` |
| Add/edit rules in DRAFT | admin+ | `BRAIN_CREATE_RULE` / `BRAIN_EDIT_RULE` |
| Submit for review | admin+ | `BRAIN_CREATE_RULE` |
| Validate version | admin+ | `BRAIN_VIEW` |
| Approve version | owner | `BRAIN_APPROVE` |
| Reject version | owner | `BRAIN_APPROVE` |
| Activate version | owner | `BRAIN_ACTIVATE` |
| Archive version | owner | `BRAIN_ARCHIVE` |
| Rollback | owner | `BRAIN_ROLLBACK` |

### 6.2 Approval Policy Authorization

```python
ApprovalPolicy
├── business_id: UUID
├── classification: str | null  # null = all classifications
├── required_role: str  # minimum role to approve
├── required_count: int  # number of approvers needed
├── timeout_hours: int  # before escalation
└── escalation_role: str | null  # who to escalate to
```

Approval policies are configured per business by owners. They determine:
- Which classifications require owner-level approval (e.g., pricing always requires owner)
- Whether multiple approvers are needed for sensitive changes
- What happens when approvals time out

---

## 7. Security Rules

1. **Never trust client-supplied IDs or roles** — All identity resolution happens server-side
2. **Authorization checked at repository layer** — Not just API layer
3. **Every endpoint protected** — No unauthenticated access to protected resources
4. **Tenant isolation by design** — Queries always scoped
5. **JWT required** — No session cookies, no implicit auth
6. **Token rotation** — Refresh tokens rotate on use
7. **Rate limiting** — Auth endpoints rate-limited
8. **Audit all authorization failures** — Log for security monitoring

---

## 8. Current vs. Future

| Component | Status |
|---|---|
| JWT authentication | ✅ IMPLEMENTED |
| Role hierarchy (owner/admin/staff) | ✅ IMPLEMENTED |
| `get_current_user` dependency | ✅ IMPLEMENTED |
| `require_customer` dependency | ✅ IMPLEMENTED |
| `require_business_member` dependency | ✅ IMPLEMENTED |
| `require_business_role()` factory | ✅ IMPLEMENTED |
| `tenant_scope()` factory | ✅ IMPLEMENTED |
| Customer data isolation | ✅ IMPLEMENTED |
| Business data isolation | ✅ IMPLEMENTED |
| Cross-tenant security tests | ✅ IMPLEMENTED |
| Granular Brain permissions | 📋 SPECIFIED |
| `viewer` role | 📋 SPECIFIED |
| Approval policies | 📋 SPECIFIED |
| Permission audit logging | 📋 SPECIFIED |
| `platform_admin` role | 🔮 FUTURE |
| Fine-grained field-level permissions | 🔮 FUTURE |
| Delegated approval (approve on behalf) | 🔮 FUTURE |
