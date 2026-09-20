# FIELDed — Business Brain Classification Taxonomy

> **Status**: SPECIFIED BUT NOT IMPLEMENTED  
> **Phase**: Architecture + Specification Only  
> **Last Updated**: 2026-09-19

---

## Overview

The Business Brain classification taxonomy defines the complete set of rule categories that govern how a business operates on FIELDed. Each classification is a self-contained domain of operational configuration with its own purpose, fields, rule types, conditions, actions, and constraints.

The taxonomy is **extensible** — new classifications can be added without modifying the core architecture. No industry is hard-coded.

---

## Classification Structure

Every classification specifies:

| Attribute | Description |
|---|---|
| **Purpose** | What operational domain this classification governs |
| **Configuration Fields** | What data can be stored within rules of this classification |
| **Rule Types** | Specific rule categories within this classification |
| **Conditions** | What can be tested in rule conditions |
| **Actions** | What outcomes rules of this classification can produce |
| **Runtime Outputs** | What the evaluation produces at runtime |
| **Applicable Scope** | What scope levels this classification supports |
| **Dependencies** | What other classifications or entities this depends on |
| **Authorization Requirements** | What permissions are needed to manage these rules |
| **Approval Requirements** | What approval is needed before activation |
| **Audit Requirements** | What must be recorded for audit |
| **Explicit Limitations** | What this classification explicitly cannot control |

---

## A. Service Configuration

### Purpose
Defines what services a business provides, how they are categorized, described, and presented to customers.

### Configuration Fields
| Field | Type | Description |
|---|---|---|
| `service_category` | string | Category slug (e.g., "electrical", "plumbing") |
| `service_name` | string | Human-readable service name |
| `description_template` | string | Template for service descriptions |
| `delivery_modes` | string[] | Allowed delivery modes (on_site, remote, in_store) |
| `duration_minutes` | number | Expected service duration |
| `requires_qualification` | boolean | Whether service requires customer qualification |

### Rule Types
| Rule Type | Purpose |
|---|---|
| `service_definition` | Defines what a service includes/excludes |
| `service_bundling` | Defines which services can be bundled |
| `service_exclusion` | Defines what a service explicitly does not cover |
| `service_customization` | Defines allowed customizations per service |

### Conditions
- `service_category`, `delivery_mode`, `customer_type`, `location`

### Actions
- `ALLOW`, `DENY`, `REQUIRE_INFORMATION`

### Runtime Outputs
- Whether a service request is valid for the business
- What information is required before proceeding

### Applicable Scope
- `BUSINESS`, `SERVICE`, `SERVICE_OFFER`

### Dependencies
- `ServiceOffer` entity must exist
- `ServiceCategory` must be valid

### Authorization Requirements
- `BRAIN_CREATE_RULE` with `admin` minimum role

### Approval Requirements
- Standard approval (single approver with `BRAIN_APPROVE`)

### Audit Requirements
- Record who defined/modified service configuration
- Track changes to service definitions

### Explicit Limitations
- **Cannot** create new ServiceOffer records (that's a data operation)
- **Cannot** modify ServiceCategory hierarchy
- **Cannot** override pricing (that's Classification B)
- **Cannot** determine availability (that's Classification C)

---

## B. Pricing

### Purpose
Defines how prices are determined for services, including base prices, surcharges, discounts, and pricing models.

### Configuration Fields
| Field | Type | Description |
|---|---|---|
| `pricing_model` | string | fixed, hourly, quote_required, starting_at, custom |
| `base_price` | number | Base price amount |
| `currency` | string | ISO 4217 currency code |
| `minimum_price` | number | Minimum chargeable amount |
| `maximum_price` | number | Maximum chargeable amount (cap) |
| `tax_inclusive` | boolean | Whether prices include tax |
| `surcharge_rules` | object[] | Conditional surcharge definitions |
| `discount_rules` | object[] | Conditional discount definitions |

### Rule Types
| Rule Type | Purpose |
|---|---|
| `base_pricing` | Sets the base price for a service/offer |
| `surcharge` | Adds conditional charges (weekend, holiday, urgency) |
| `discount` | Provides conditional reductions (volume, loyalty, seasonal) |
| `price_floor` | Sets minimum price boundaries |
| `price_cap` | Sets maximum price boundaries |
| `quote_threshold` | Defines when a custom quote is required vs. auto-pricing |
| `payment_terms` | Defines payment timing requirements |

### Conditions
- `service_category`, `service_offer_id`, `customer_type`, `delivery_mode`
- `day_of_week`, `is_holiday`, `time`
- `enquiry_value`, `quantity`, `urgency`
- `location`, `distance`

### Actions
- `ALLOW`, `DENY`, `SET_VALUE` (price amount), `REQUIRE_INFORMATION`, `REQUIRE_APPROVAL`

### Runtime Outputs
- Calculated price or price range
- Whether custom quote is required
- Applicable surcharges and discounts
- Payment terms

### Applicable Scope
- `BUSINESS`, `SERVICE`, `SERVICE_OFFER`, `LOCATION`

### Dependencies
- `ServiceOffer.pricing_model` must be compatible
- Currency must match business configuration

### Authorization Requirements
- `BRAIN_CREATE_RULE` with `admin` minimum role
- `BRAIN_APPROVE` with `owner` role for activation (pricing is sensitive)

### Approval Requirements
- **Owner-level approval required** (pricing directly affects revenue)
- Price changes above configurable threshold require explicit owner sign-off

### Audit Requirements
- Full change history for every pricing rule
- Track who set each price, when, and why
- Link every transaction to the pricing rules that governed it

### Explicit Limitations
- **Cannot** execute payments (that's an adapter concern)
- **Cannot** override ServiceOffer pricing_model (that's a data operation)
- **Cannot** set prices below zero
- **Cannot** bypass quote_threshold to force auto-pricing when custom quote is required
- **Cannot** modify another business's pricing

---

## C. Availability

### Purpose
Defines when and how services can be delivered, including scheduling constraints, notice periods, and capacity limits.

### Configuration Fields
| Field | Type | Description |
|---|---|---|
| `operating_hours` | object | Day-of-week → start/end time mapping |
| `minimum_notice_hours` | number | Minimum hours between booking and service |
| `maximum_advance_days` | number | Maximum days ahead for booking |
| `max_bookings_per_day` | number | Daily capacity limit |
| `max_bookings_per_slot` | number | Per-slot capacity |
| `slot_duration_minutes` | number | Default time slot duration |
| `buffer_minutes` | number | Buffer between consecutive bookings |
| `holiday_closure` | object[] | Dates/date-ranges when business is closed |

### Rule Types
| Rule Type | Purpose |
|---|---|
| `operating_hours` | Defines when business is available |
| `minimum_notice` | Sets minimum advance notice requirements |
| `maximum_advance` | Sets maximum forward booking window |
| `capacity_limit` | Defines capacity constraints |
| `blackout_period` | Defines when service is unavailable |
| `slot_configuration` | Defines time slot structure |
| `concurrent_limit` | Limits simultaneous services |

### Conditions
- `day_of_week`, `date`, `time`, `is_holiday`
- `service_offer_id`, `service_category`
- `notice_hours`, `requested_date`
- `location`, `delivery_mode`
- `current_bookings_count`

### Actions
- `ALLOW`, `DENY`, `RESTRICT` (limited availability), `REQUIRE_INFORMATION`

### Runtime Outputs
- Whether a requested time is available
- Available time slots
- Capacity remaining
- Alternative suggestions when requested time unavailable

### Applicable Scope
- `BUSINESS`, `SERVICE`, `SERVICE_OFFER`, `LOCATION`

### Dependencies
- Calendar adapter (for actual availability checking)
- `ServiceOffer` must exist for offer-scoped rules

### Authorization Requirements
- `BRAIN_CREATE_RULE` with `admin` minimum role

### Approval Requirements
- Standard approval

### Audit Requirements
- Track availability configuration changes
- Log when availability rules reject booking requests

### Explicit Limitations
- **Cannot** manage actual calendar state (that's an adapter)
- **Cannot** confirm bookings (that's the booking state machine)
- **Cannot** override booking cancellation policies (that's Classification G)
- **Cannot** create or modify ServiceOffer records

---

## D. Qualification

### Purpose
Defines what information must be collected from customers before a service can be provided, quoted, or booked.

### Configuration Fields
| Field | Type | Description |
|---|---|---|
| `required_fields` | object[] | Fields that must be provided |
| `optional_fields` | object[] | Fields that may be provided |
| `field_validation` | object | Validation rules per field |
| `information_purpose` | string | Why the information is needed |

### Rule Types
| Rule Type | Purpose |
|---|---|
| `required_information` | Defines mandatory customer-provided data |
| `conditional_information` | Defines data required under specific conditions |
| `document_requirement` | Defines documents that must be uploaded |
| `verification_requirement` | Defines what must be verified before proceeding |
| `eligibility_check` | Defines customer eligibility criteria |

### Conditions
- `service_category`, `service_offer_id`, `customer_type`
- `enquiry_value`, `delivery_mode`, `location`
- `has_documents`, `customer_verified`

### Actions
- `ALLOW`, `DENY`, `REQUIRE_INFORMATION` (with specific field list)

### Runtime Outputs
- List of required information fields
- Whether customer has provided sufficient information
- Specific questions to ask the customer

### Applicable Scope
- `BUSINESS`, `SERVICE`, `SERVICE_OFFER`

### Dependencies
- `Enquiry` metadata structure
- `CustomerProfile` fields

### Authorization Requirements
- `BRAIN_CREATE_RULE` with `admin` minimum role

### Approval Requirements
- Standard approval

### Audit Requirements
- Track what information was required and when
- Log qualification decisions

### Explicit Limitations
- **Cannot** access customer data beyond what the customer provides
- **Cannot** verify information externally (that's an integration)
- **Cannot** block enquiries permanently (only pause for information)
- **Cannot** modify CustomerProfile directly

---

## E. Policy

### Purpose
Defines business policies governing customer interactions, including cancellation, refunds, modifications, and general terms.

### Configuration Fields
| Field | Type | Description |
|---|---|---|
| `policy_type` | string | cancellation, refund, modification, terms |
| `policy_text` | string | Human-readable policy description |
| `policy_rules` | object[] | Structured policy conditions |
| `effective_date` | date | When policy takes effect |

### Rule Types
| Rule Type | Purpose |
|---|---|
| `cancellation_policy` | Defines cancellation windows, fees, conditions |
| `refund_policy` | Defines refund eligibility and amounts |
| `modification_policy` | Defines what can be changed and when |
| `terms_of_service` | Defines general service terms |
| `liability_policy` | Defines liability limitations |
| `guarantee_policy` | Defines service guarantees |
| `complaint_policy` | Defines complaint handling procedures |

### Conditions
- `service_category`, `service_offer_id`, `customer_type`
- `time_before_service`, `time_since_booking`
- `enquiry_value`, `cancellation_reason`
- `service_status`, `booking_status`

### Actions
- `ALLOW`, `DENY`, `SET_VALUE` (fee amount), `REQUIRE_APPROVAL`, `ESCALATE`

### Runtime Outputs
- Whether a cancellation/refund/modification is permitted
- Applicable fees or penalties
- Whether human review is required

### Applicable Scope
- `BUSINESS`, `SERVICE`, `SERVICE_OFFER`

### Dependencies
- `Enquiry` status
- `Booking` status (when implemented)

### Authorization Requirements
- `BRAIN_CREATE_RULE` with `admin` minimum role
- `BRAIN_APPROVE` with `owner` for policy changes

### Approval Requirements
- Owner-level approval (policies affect customer experience and legal standing)

### Audit Requirements
- Full policy change history
- Link every policy decision to the specific policy version
- Track policy application in disputes

### Explicit Limitations
- **Cannot** override legal requirements
- **Cannot** modify transaction state directly (that's the state machine)
- **Cannot** process refunds (that's a payment adapter)
- **Cannot** enforce policies without human oversight in dispute scenarios

---

## F. Booking

### Purpose
Defines how bookings are created, confirmed, and managed — configuring the booking state machine behavior.

### Configuration Fields
| Field | Type | Description |
|---|---|---|
| `booking_model` | string | instant, request, approval |
| `confirmation_window_hours` | number | Time allowed for confirmation |
| `auto_confirm` | boolean | Whether bookings auto-confirm under conditions |
| `requires_deposit` | boolean | Whether deposit is required |
| `deposit_percentage` | number | Deposit as percentage of total |

### Rule Types
| Rule Type | Purpose |
|---|---|
| `booking_creation` | Defines how bookings can be initiated |
| `confirmation_rules` | Defines confirmation requirements |
| `deposit_rules` | Defines deposit requirements |
| `reminder_schedule` | Defines pre-service reminder timing |
| `auto_confirmation` | Defines conditions for automatic confirmation |

### Conditions
- `service_offer_id`, `service_category`, `customer_type`
- `enquiry_value`, `booking_value`
- `time_before_service`, `customer_history`
- `has_deposit`, `qualification_complete`

### Actions
- `ALLOW`, `DENY`, `REQUIRE_APPROVAL`, `REQUIRE_INFORMATION`, `SET_VALUE`

### Runtime Outputs
- Whether a booking can be created
- Whether auto-confirmation applies
- Deposit requirements
- Reminder schedule

### Applicable Scope
- `BUSINESS`, `SERVICE`, `SERVICE_OFFER`

### Dependencies
- Booking state machine
- Availability classification (C)
- Qualification classification (D)

### Authorization Requirements
- `BRAIN_CREATE_RULE` with `admin` minimum role

### Approval Requirements
- Standard approval

### Audit Requirements
- Track booking rule configuration changes
- Log booking decisions with rule references

### Explicit Limitations
- **Cannot** change booking state directly (that's the state machine)
- **Cannot** process payments (that's an adapter)
- **Cannot** override availability rules (that's Classification C)
- **Cannot** modify calendar entries (that's an adapter)

---

## G. Cancellation

### Purpose
Defines cancellation-specific behavior, complementing the Policy classification with booking-state-machine-aware rules.

### Configuration Fields
| Field | Type | Description |
|---|---|---|
| `cancellation_windows` | object[] | Time-based cancellation tiers |
| `fee_structure` | object[] | Fee calculations per window |
| `allowed_reasons` | string[] | Accepted cancellation reasons |
| `auto_cancel_hours` | number | Auto-cancel after inactivity |

### Rule Types
| Rule Type | Purpose |
|---|---|
| `cancellation_window` | Time-based cancellation eligibility |
| `cancellation_fee` | Fee calculation rules |
| `cancellation_reason` | Which reasons are accepted |
| `auto_cancellation` | Automatic cancellation conditions |
| `cancellation_approval` | When cancellation requires approval |

### Conditions
- `time_before_service`, `cancellation_reason`
- `booking_status`, `service_offer_id`
- `customer_type`, `cancellation_count`

### Actions
- `ALLOW`, `DENY`, `SET_VALUE` (fee), `REQUIRE_APPROVAL`, `ESCALATE`

### Runtime Outputs
- Whether cancellation is permitted
- Applicable cancellation fee
- Whether approval is needed

### Applicable Scope
- `BUSINESS`, `SERVICE`, `SERVICE_OFFER`

### Dependencies
- Booking state machine
- Policy classification (E)

### Authorization Requirements
- `BRAIN_CREATE_RULE` with `admin` minimum role

### Approval Requirements
- Standard approval; owner-level for fee changes

### Audit Requirements
- Full cancellation decision trail
- Fee calculation transparency

### Explicit Limitations
- **Cannot** cancel bookings directly (that's the state machine)
- **Cannot** process refunds (that's an adapter)
- **Cannot** override policy classification (E) — works alongside it

---

## H. Rescheduling

### Purpose
Defines rules for rescheduling existing bookings.

### Configuration Fields
| Field | Type | Description |
|---|---|---|
| `allowed_reschedule_windows` | object[] | When rescheduling is permitted |
| `max_reschedules` | number | Maximum reschedules per booking |
| `reschedule_fee` | number | Fee for rescheduling |
| `requires_requalification` | boolean | Whether reschedule triggers re-qualification |

### Rule Types
| Rule Type | Purpose |
|---|---|
| `reschedule_window` | When rescheduling is allowed |
| `reschedule_limit` | How many times a booking can be rescheduled |
| `reschedule_fee` | Fee calculation for rescheduling |
| `reschedule_availability` | Whether new time must satisfy availability |

### Conditions
- `time_before_service`, `reschedule_count`
- `booking_status`, `service_offer_id`
- `new_requested_date`, `customer_type`

### Actions
- `ALLOW`, `DENY`, `SET_VALUE` (fee), `REQUIRE_INFORMATION`, `REQUIRE_APPROVAL`

### Runtime Outputs
- Whether rescheduling is permitted
- Applicable fee
- Whether re-qualification is needed

### Applicable Scope
- `BUSINESS`, `SERVICE`, `SERVICE_OFFER`

### Dependencies
- Booking state machine
- Availability classification (C)

### Authorization Requirements
- `BRAIN_CREATE_RULE` with `admin` minimum role

### Approval Requirements
- Standard approval

### Audit Requirements
- Track all reschedule decisions
- Record fee applications

### Explicit Limitations
- **Cannot** modify booking state (that's the state machine)
- **Cannot** change calendar entries (that's an adapter)
- **Cannot** override availability rules (that's Classification C)

---

## I. Communication

### Purpose
Defines how the business communicates with customers throughout the service lifecycle.

### Configuration Fields
| Field | Type | Description |
|---|---|---|
| `response_time_target_hours` | number | Target response time |
| `preferred_channels` | string[] | Preferred communication channels |
| `tone_guidelines` | string | Communication tone/style |
| `template_preferences` | object | Template selection preferences |

### Rule Types
| Rule Type | Purpose |
|---|---|
| `response_time` | Target response time per context |
| `channel_preference` | Preferred communication channel per context |
| `tone_policy` | Communication tone requirements |
| `template_selection` | Which templates to use for which messages |
| `auto_response` | Automated response rules |
| `escalation_notification` | When to notify business members |

### Conditions
- `enquiry_status`, `booking_status`, `customer_type`
- `time_since_last_message`, `message_count`
- `service_category`, `service_offer_id`
- `sender_type`

### Actions
- `ALLOW`, `DENY`, `NOTIFY`, `ESCALATE`, `ROUTE`, `SET_VALUE` (response template)

### Runtime Outputs
- Whether a communication is permitted
- Which channel to use
- Which template to apply
- Whether escalation is needed

### Applicable Scope
- `BUSINESS`, `SERVICE`, `SERVICE_OFFER`

### Dependencies
- Email/SMS adapters
- Enquiry/Conversation system

### Authorization Requirements
- `BRAIN_CREATE_RULE` with `staff` minimum role

### Approval Requirements
- Standard approval

### Audit Requirements
- Track communication policy changes
- Log communication decisions

### Explicit Limitations
- **Cannot** send messages directly (that's an adapter)
- **Cannot** modify conversation state (that's the enquiry system)
- **Cannot** override AI content guardrails (that's AI governance)
- **Cannot** access customer contact info beyond what's in CustomerProfile

---

## J. Escalation

### Purpose
Defines when and how issues are escalated to human handlers.

### Configuration Fields
| Field | Type | Description |
|---|---|---|
| `escalation_levels` | object[] | Tiered escalation structure |
| `escalation_triggers` | object[] | What triggers escalation |
| `notification_channels` | string[] | How to notify escalations |
| `response_sla_hours` | number | Expected response time for escalations |

### Rule Types
| Rule Type | Purpose |
|---|---|
| `value_threshold` | Escalate when value exceeds threshold |
| `complexity_trigger` | Escalate based on complexity indicators |
| `customer_request` | Escalate when customer explicitly requests human |
| `conflict_escalation` | Escalate on rule conflicts |
| `timeout_escalation` | Escalate when response time exceeded |
| `repeat_escalation` | Escalate after N failed automated attempts |

### Conditions
- `enquiry_value`, `service_category`, `customer_type`
- `time_without_response`, `attempt_count`
- `conflict_detected`, `customer_requested_human`
- `service_offer_id`

### Actions
- `ESCALATE`, `NOTIFY`, `ROUTE` (to specific role/person)

### Runtime Outputs
- Escalation level
- Who to notify
- Why escalation was triggered
- Required response time

### Applicable Scope
- `BUSINESS`, `SERVICE`, `SERVICE_OFFER`

### Dependencies
- BusinessMember structure
- Notification system

### Authorization Requirements
- `BRAIN_CREATE_RULE` with `admin` minimum role

### Approval Requirements
- Standard approval

### Audit Requirements
- Full escalation trail
- Response time tracking
- Resolution recording

### Explicit Limitations
- **Cannot** assign enquiries to specific people (that's workflow)
- **Cannot** modify enquiry state (that's the state machine)
- **Cannot** send notifications directly (that's an adapter)

---

## K. Fulfilment / Service Execution

### Purpose
Defines how services are delivered and tracked during execution.

### Configuration Fields
| Field | Type | Description |
|---|---|---|
| `completion_criteria` | object[] | What constitutes service completion |
| `evidence_requirements` | object[] | What evidence is needed |
| `milestone_definitions` | object[] | Service progress milestones |
| `quality_checks` | object[] | Quality verification steps |

### Rule Types
| Rule Type | Purpose |
|---|---|
| `completion_definition` | What constitutes "done" |
| `evidence_requirement` | What proof of completion is needed |
| `milestone_check` | Progress verification points |
| `quality_gate` | Quality requirements before completion |
| `handover_protocol` | How service is handed to customer |

### Conditions
- `service_offer_id`, `service_category`, `delivery_mode`
- `service_status`, `milestone_reached`
- `evidence_provided`, `quality_check_passed`

### Actions
- `ALLOW`, `DENY`, `REQUIRE_INFORMATION`, `REQUIRE_APPROVAL`

### Runtime Outputs
- Whether service can be marked complete
- What evidence is still needed
- Whether quality check is required

### Applicable Scope
- `BUSINESS`, `SERVICE`, `SERVICE_OFFER`

### Dependencies
- Booking state machine
- Evidence/Audit system

### Authorization Requirements
- `BRAIN_CREATE_RULE` with `admin` minimum role

### Approval Requirements
- Standard approval

### Audit Requirements
- Track completion decisions
- Record evidence references

### Explicit Limitations
- **Cannot** change service state (that's the state machine)
- **Cannot** collect evidence directly (that's an adapter)
- **Cannot** determine review eligibility (that's the trust system)

---

## L. Payment

### Purpose
Defines payment-related configuration (complementing Pricing which defines amounts).

### Configuration Fields
| Field | Type | Description |
|---|---|---|
| `payment_methods` | string[] | Accepted payment methods |
| `payment_timing` | string | before, after, split, milestone |
| `invoice_required` | boolean | Whether invoice is generated |
| `deposit_rules` | object | Deposit configuration |

### Rule Types
| Rule Type | Purpose |
|---|---|
| `payment_method` | Which payment methods are accepted |
| `payment_timing` | When payment is collected |
| `invoice_policy` | Invoice generation rules |
| `deposit_policy` | Deposit requirements |
| `installment_policy` | Installment plan availability |

### Conditions
- `service_offer_id`, `enquiry_value`, `customer_type`
- `booking_status`, `service_status`
- `payment_method`

### Actions
- `ALLOW`, `DENY`, `REQUIRE_INFORMATION`, `REQUIRE_APPROVAL`

### Runtime Outputs
- Whether payment can be collected
- Which methods are available
- Whether deposit is required
- Invoice generation trigger

### Applicable Scope
- `BUSINESS`, `SERVICE`, `SERVICE_OFFER`

### Dependencies
- Payment adapter (future)
- Pricing classification (B)

### Authorization Requirements
- `BRAIN_CREATE_RULE` with `owner` minimum role (payment is financial)

### Approval Requirements
- Owner-level approval required

### Audit Requirements
- Full payment policy change history
- Link every payment decision to governing rules

### Explicit Limitations
- **Cannot** process payments (that's an adapter)
- **Cannot** set prices (that's Classification B)
- **Cannot** issue refunds directly (that's an adapter + Policy E)
- **Cannot** modify transaction state

---

## M. Compliance / Restrictions

### Purpose
Defines legal, regulatory, and business-specific restrictions.

### Configuration Fields
| Field | Type | Description |
|---|---|---|
| `regulatory_requirements` | object[] | Applicable regulations |
| `age_restrictions` | object | Age-related restrictions |
| `location_restrictions` | object[] | Geographic restrictions |
| `license_requirements` | object[] | Required licenses/certifications |

### Rule Types
| Rule Type | Purpose |
|---|---|
| `age_restriction` | Minimum/maximum age requirements |
| `location_restriction` | Service area limitations |
| `license_requirement` | Required business/customer licenses |
| `regulatory_compliance` | Regulatory requirement checks |
| `safety_restriction` | Safety-related limitations |
| `capacity_restriction` | Physical capacity limitations |

### Conditions
- `customer_age`, `customer_location`, `service_location`
- `service_category`, `service_offer_id`
- `license_held`, `safety_certified`

### Actions
- `ALLOW`, `DENY`, `REQUIRE_INFORMATION`, `ESCALATE`

### Runtime Outputs
- Whether service can be provided
- What restrictions apply
- What documentation is required

### Applicable Scope
- `BUSINESS`, `SERVICE`, `SERVICE_OFFER`, `LOCATION`

### Dependencies
- CustomerProfile (for age, location)
- External verification services (future)

### Authorization Requirements
- `BRAIN_CREATE_RULE` with `owner` minimum role (compliance is sensitive)

### Approval Requirements
- Owner-level approval required

### Audit Requirements
- Full compliance rule history
- Every compliance decision must be traceable
- Regulatory change tracking

### Explicit Limitations
- **Cannot** verify external documents (that's an integration)
- **Cannot** override legal requirements (rules must comply with law)
- **Cannot** provide legal advice
- **Cannot** modify CustomerProfile data

---

## N. AI Behaviour

### Purpose
Defines how AI agents behave when interacting with this business's customers and data.

### Configuration Fields
| Field | Type | Description |
|---|---|---|
| `ai_personality` | string | Tone/style for AI-generated content |
| `allowed_capabilities` | string[] | Which AI capabilities are permitted |
| `prohibited_topics` | string[] | Topics AI must not discuss |
| `confidence_threshold` | number | Minimum confidence for AI proposals |

### Rule Types
| Rule Type | Purpose |
|---|---|
| `capability_permission` | Which AI capabilities are allowed |
| `topic_restriction` | Topics AI must avoid |
| `response_style` | How AI should communicate |
| `confidence_floor` | Minimum confidence for automated actions |
| `human_handoff_trigger` | When AI must defer to human |

### Conditions
- `ai_capability` (interpret, extract, classify, summarize, recommend, draft, propose, escalate)
- `context_type` (enquiry, conversation, discovery, brain_config)
- `confidence_score`, `topic`

### Actions
- `ALLOW`, `DENY`, `ESCALATE` (to human)

### Runtime Outputs
- Whether an AI action is permitted
- What restrictions apply to AI-generated content
- Whether human handoff is required

### Applicable Scope
- `BUSINESS`

### Dependencies
- AI provider adapter
- AI governance framework

### Authorization Requirements
- `BRAIN_CREATE_RULE` with `owner` minimum role (AI behavior is sensitive)

### Approval Requirements
- Owner-level approval required

### Audit Requirements
- Track all AI behavior configuration changes
- Log every AI decision with governing rules
- Full provenance chain

### Explicit Limitations
- **Cannot** override AI governance hard rules (see ai-governance.md)
- **Cannot** make AI authoritative over business decisions
- **Cannot** bypass schema validation
- **Cannot** allow AI to activate Brain versions

---

## O. Human Approval

### Purpose
Defines approval workflows for business operations.

### Configuration Fields
| Field | Type | Description |
|---|---|---|
| `approval_categories` | object[] | What requires approval |
| `approval_levels` | object[] | Who can approve what |
| `timeout_hours` | number | Approval timeout |
| `auto_approve_conditions` | object[] | When auto-approval is permitted |

### Rule Types
| Rule Type | Purpose |
|---|---|
| `approval_requirement` | What operations require approval |
| `approver_qualification` | Who can approve |
| `approval_timeout` | What happens when approval times out |
| `auto_approval` | When approval is automatically granted |
| `multi_approval` | When multiple approvers are needed |

### Conditions
- `operation_type`, `value`, `classification`
- `requester_role`, `approver_role`
- `time_pending`, `urgency`

### Actions
- `REQUIRE_APPROVAL`, `ALLOW` (auto-approve), `ESCALATE` (timeout escalation)

### Runtime Outputs
- Whether approval is required
- Who can approve
- Timeout behavior
- Escalation path

### Applicable Scope
- `BUSINESS`

### Dependencies
- BusinessMember + Role structure
- Notification system

### Authorization Requirements
- `BRAIN_CREATE_RULE` with `owner` minimum role

### Approval Requirements
- Owner-level approval required

### Audit Requirements
- Full approval decision trail
- Timeout tracking
- Escalation recording

### Explicit Limitations
- **Cannot** approve on behalf of humans
- **Cannot** bypass authorization
- **Cannot** modify approval records after creation
- **Cannot** override Brain governance lifecycle

---

## P. Integration Behaviour

### Purpose
Defines how external integrations behave for this business.

### Configuration Fields
| Field | Type | Description |
|---|---|---|
| `enabled_integrations` | string[] | Which integrations are active |
| `sync_preferences` | object | Sync timing and direction |
| `webhook_config` | object | Webhook endpoints and events |
| `retry_policy` | object | Retry configuration for failures |

### Rule Types
| Rule Type | Purpose |
|---|---|
| `integration_enablement` | Which integrations are active |
| `sync_direction` | Data flow direction per integration |
| `webhook_subscription` | Which events trigger webhooks |
| `retry_configuration` | How failures are handled |
| `data_mapping` | How FIELDed data maps to external systems |

### Conditions
- `integration_type`, `event_type`, `data_type`
- `failure_count`, `last_success`

### Actions
- `ALLOW`, `DENY`, `PAUSE` (integration), `NOTIFY`

### Runtime Outputs
- Whether an integration action is permitted
- Sync direction and timing
- Webhook trigger decisions

### Applicable Scope
- `BUSINESS`

### Dependencies
- Integration entity
- Adapter implementations

### Authorization Requirements
- `BRAIN_CREATE_RULE` with `owner` minimum role

### Approval Requirements
- Owner-level approval required

### Audit Requirements
- Track integration configuration changes
- Log integration events and decisions

### Explicit Limitations
- **Cannot** execute integrations directly (that's adapters)
- **Cannot** access external systems without adapter
- **Cannot** modify Integration entity directly
- **Cannot** bypass adapter error handling

---

## Q. Governance / Provenance

### Purpose
Defines meta-rules about how the Brain itself is governed.

### Configuration Fields
| Field | Type | Description |
|---|---|---|
| `version_policy` | object | How versions are managed |
| `approval_policy` | object | Approval requirements per classification |
| `audit_retention_days` | number | How long audit records are kept |
| `rollback_policy` | object | Rollback permissions and constraints |

### Rule Types
| Rule Type | Purpose |
|---|---|
| `version_lifecycle` | How versions progress through lifecycle |
| `classification_approval` | Approval requirements per classification |
| `audit_retention` | How long records are maintained |
| `rollback_permission` | Who can rollback and when |
| `brain_freeze` | When Brain changes are prohibited |

### Conditions
- `classification`, `version_status`, `requester_role`
- `time_since_activation`, `active_transactions_count`

### Actions
- `ALLOW`, `DENY`, `REQUIRE_APPROVAL`, `PAUSE` (freeze changes)

### Runtime Outputs
- Whether a Brain operation is permitted
- Approval requirements for specific changes
- Whether Brain is frozen

### Applicable Scope
- `BUSINESS`

### Dependencies
- BusinessBrain + BrainVersion entities
- Audit system

### Authorization Requirements
- `BRAIN_CREATE_RULE` with `owner` minimum role

### Approval Requirements
- Owner-level approval required; governance changes require highest scrutiny

### Audit Requirements
- All governance rule changes are themselves audited
- Immutable audit trail for governance decisions

### Explicit Limitations
- **Cannot** modify the Brain architecture itself
- **Cannot** bypass version lifecycle
- **Cannot** delete audit records
- **Cannot** override tenant isolation

---

## Classification Dependency Map

```
Q (Governance) ─── governs all other classifications
    │
    ├── N (AI Behaviour) ─── constrains AI interactions
    │
    ├── A (Service) ─── defines what's offered
    │   ├── B (Pricing) ─── how much it costs
    │   ├── C (Availability) ─── when it's available
    │   ├── D (Qualification) ─── what's needed
    │   ├── K (Fulfilment) ─── how it's delivered
    │   └── M (Compliance) ─── restrictions
    │
    ├── E (Policy) ─── general policies
    │   ├── F (Booking) ─── booking behavior
    │   ├── G (Cancellation) ─── cancellation rules
    │   └── H (Rescheduling) ─── rescheduling rules
    │
    ├── I (Communication) ─── how we talk
    ├── J (Escalation) ─── when humans intervene
    ├── L (Payment) ─── payment handling
    ├── O (Human Approval) ─── approval workflows
    └── P (Integration) ─── external systems
```

---

## Implementation Priority

| Priority | Classification | Rationale |
|---|---|---|
| Phase 1 | A (Service), B (Pricing), C (Availability), D (Qualification) | Core transaction support |
| Phase 2 | E (Policy), F (Booking), G (Cancellation) | Transaction lifecycle |
| Phase 3 | I (Communication), J (Escalation) | Customer interaction |
| Phase 4 | N (AI Behaviour), O (Human Approval) | AI governance |
| Phase 5 | K (Fulfilment), L (Payment), M (Compliance) | Extended operations |
| Phase 6 | H (Rescheduling), P (Integration), Q (Governance) | Advanced features |
