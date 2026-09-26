# FIELDed — Data Model

**Status**: Current State Baseline  
**Last Updated**: 2026-09-26

---

## Database Technology

- **Database**: PostgreSQL 16
- **ORM**: SQLAlchemy 2.0 (async)
- **Migrations**: Alembic
- **Total Tables**: 56
- **Total Migrations**: 22

---

## Entity Relationship Overview

### Identity Domain

| Entity | Table | Key Fields | Relationships |
|--------|-------|------------|---------------|
| User | `users` | id, email, hashed_password, is_active, is_verified | 1:1 CustomerProfile, 1:N BusinessMember |
| CustomerProfile | `customer_profiles` | id, user_id, first_name, last_name, phone, status | N:1 User |
| Business | `businesses` | id, name, slug, status, currency | 1:1 BusinessProfile, 1:N BusinessMember, 1:N ServiceOffer, 1:1 BusinessBrain |
| BusinessProfile | `business_profiles` | id, business_id, description, logo_url, city, country, average_rating, review_count, public_status | N:1 Business |
| BusinessMember | `business_members` | id, user_id, business_id, role | N:1 User, N:1 Business |

### Service Domain

| Entity | Table | Key Fields | Relationships |
|--------|-------|------------|---------------|
| ServiceOffer | `service_offers` | id, business_id, name, slug, description, pricing_model, base_price, currency, delivery_mode, status | N:1 Business, 1:N Enquiry |
| ServiceCategory | `service_categories` | id, name, slug, description | 1:N ServiceOffer |

### Enquiry Domain

| Entity | Table | Key Fields | Relationships |
|--------|-------|------------|---------------|
| Enquiry | `enquiries` | id, reference, customer_id, business_id, service_offer_id, subject, message, status, brain_version_id | N:1 User, N:1 Business, N:1 ServiceOffer, 1:1 Conversation |
| Conversation | `conversations` | id, enquiry_id, customer_id, business_id, status | N:1 Enquiry, 1:N Message |
| Message | `messages` | id, conversation_id, sender_id, sender_type, content, message_type | N:1 Conversation, N:1 User |

### Quote Domain

| Entity | Table | Key Fields | Relationships |
|--------|-------|------------|---------------|
| Quote | `quotes` | id, reference, customer_id, business_id, enquiry_id, service_offer_id, amount, currency, status, brain_version_id, pricing_evidence | N:1 User, N:1 Business, N:1 Enquiry, N:1 ServiceOffer, 1:N Booking |

### Booking Domain

| Entity | Table | Key Fields | Relationships |
|--------|-------|------------|---------------|
| Booking | `bookings` | id, reference, customer_id, business_id, quote_id, enquiry_id, service_offer_id, requested_at, status, brain_version_id, decision_evidence | N:1 User, N:1 Business, N:1 Quote, N:1 Enquiry, N:1 ServiceOffer |

### Payment Domain

| Entity | Table | Key Fields | Relationships |
|--------|-------|------------|---------------|
| Payment | `payments` | id, idempotency_key, business_id, customer_id, invoice_id, amount, currency, status, provider, provider_reference, refunded_amount | N:1 Business, N:1 User, N:1 Invoice, 1:N PaymentAttempt |
| PaymentAttempt | `payment_attempts` | id, payment_id, attempt_number, provider, provider_reference, status, amount, currency | N:1 Payment |
| PaymentWebhook | `payment_webhooks` | id, payment_id, provider, event_type, payload, status | N:1 Payment |

### Invoice Domain

| Entity | Table | Key Fields | Relationships |
|--------|-------|------------|---------------|
| Invoice | `invoices` | id, business_id, customer_id, booking_id, amount, currency, status, payment_status, paid_amount | N:1 Business, N:1 User, N:1 Booking, 1:N Payment |

### Ledger Domain

| Entity | Table | Key Fields | Relationships |
|--------|-------|------------|---------------|
| LedgerEntry | `ledger_entries` | id, business_id, entry_type, amount, currency, reference_type, reference_id | N:1 Business |

### Service Execution Domain

| Entity | Table | Key Fields | Relationships |
|--------|-------|------------|---------------|
| ServiceExecution | `service_executions` | id, booking_id, business_id, customer_id, status, scheduled_at, started_at, completed_at | N:1 Booking, N:1 Business, N:1 User |

### Review Domain

| Entity | Table | Key Fields | Relationships |
|--------|-------|------------|---------------|
| Review | `reviews` | id, business_id, customer_id, service_execution_id, booking_id, enquiry_id, service_offer_id, rating, title, body, status, response_body | N:1 Business, N:1 User, N:1 ServiceExecution, N:1 Booking, N:1 Enquiry, N:1 ServiceOffer |

### Business Brain Domain

| Entity | Table | Key Fields | Relationships |
|--------|-------|------------|---------------|
| BusinessBrain | `business_brains` | id, business_id, active_version_id | N:1 Business, 1:N BrainVersion |
| BrainVersion | `brain_versions` | id, brain_id, version_number, status, identity_config, services_config, pricing_config, availability_config, qualification_config, policies_config, escalation_config, communication_config | N:1 BusinessBrain, 1:N BusinessRule |
| BusinessRule | `business_rules` | id, brain_version_id, rule_type, name, description, rule_data, priority, is_active | N:1 BrainVersion |
| BrainConversation | `brain_conversations` | id, brain_id, business_id, status, title, context_summary | N:1 BusinessBrain, N:1 Business, 1:N BrainMessage, 1:N BrainProposal |
| BrainMessage | `brain_messages` | id, conversation_id, role, content, metadata | N:1 BrainConversation |
| BrainProposal | `brain_proposals` | id, brain_id, conversation_id, business_id, proposal_type, status, confidence, reasoning_summary, proposed_change, affected_area | N:1 BusinessBrain, N:1 BrainConversation, N:1 Business |

### Communication Domain

| Entity | Table | Key Fields | Relationships |
|--------|-------|------------|---------------|
| Communication | `communications` | id, business_id, channel, purpose, status, subject, body | N:1 Business, 1:N CommunicationRecipient |
| CommunicationRecipient | `communication_recipients` | id, communication_id, recipient_type, recipient_id, status | N:1 Communication, 1:N CommunicationAttempt |
| CommunicationAttempt | `communication_attempts` | id, recipient_id, provider, status, provider_reference | N:1 CommunicationRecipient |
| Notification | `notifications` | id, user_id, title, body, priority, read_at | N:1 User |
| CommunicationTemplate | `communication_templates` | id, business_id, name, channel, purpose, subject_template, body_template, status | N:1 Business |
| OutboxEvent | `outbox_events` | id, event_type, payload, status, attempts, lease_expires_at | (standalone) |

### Voice Domain

| Entity | Table | Key Fields | Relationships |
|--------|-------|------------|---------------|
| Call | `calls` | id, business_id, call_type, purpose, status, from_number, to_number | N:1 Business, 1:N CallAttempt, 1:1 CallSession |
| CallAttempt | `call_attempts` | id, call_id, provider, status, provider_reference | N:1 Call |
| CallSession | `call_sessions` | id, call_id, status, started_at, ended_at, outcome | N:1 Call |
| Escalation | `escalations` | id, call_id, business_id, status, assigned_to_id, resolved_at | N:1 Call, N:1 Business, N:1 User |
| Campaign | `campaigns` | id, business_id, name, status, scheduled_at | N:1 Business, 1:N CampaignRecipient |
| CampaignRecipient | `campaign_recipients` | id, campaign_id, recipient_type, recipient_id, status | N:1 Campaign |

### Invitation Domain

| Entity | Table | Key Fields | Relationships |
|--------|-------|------------|---------------|
| BusinessInvitation | `business_invitations` | id, business_id, email, role, token, status, invited_by_id, accepted_by_id | N:1 Business, N:1 User (invited_by), N:1 User (accepted_by) |

### Calendar Domain

| Entity | Table | Key Fields | Relationships |
|--------|-------|------------|---------------|
| CalendarConnection | `calendar_connections` | id, business_id, provider, access_token_encrypted, refresh_token_encrypted, token_expiry, status | N:1 Business |
| CalendarEventSyncRecord | `calendar_event_sync_records` | id, connection_id, booking_id, calendar_event_id, status, last_synced_at, error | N:1 CalendarConnection, N:1 Booking |

### Booking Automation Domain

| Entity | Table | Key Fields | Relationships |
|--------|-------|------------|---------------|
| BookingAutomationStatus | `booking_automation_status` | id, business_id, booking_id, operation_type, triggering_event, status, attempt_count, last_error, next_retry_at, result_evidence | N:1 Business, N:1 Booking |

### Agent Domain

| Entity | Table | Key Fields | Relationships |
|--------|-------|------------|---------------|
| AgentCapability | `agent_capabilities` | id, business_id, name, description, handler, requires_approval | N:1 Business |
| AgentDelegation | `agent_delegations` | id, capability_id, business_id, delegate_user_id, status, granted_at, expires_at | N:1 AgentCapability, N:1 Business, N:1 User |
| AgentExecutionLog | `agent_execution_logs` | id, delegation_id, capability_id, business_id, status, input_data, output_data, error | N:1 AgentDelegation, N:1 AgentCapability, N:1 Business |

### Commercial Policy Domain

| Entity | Table | Key Fields | Relationships |
|--------|-------|------------|---------------|
| CommercialPolicy | `commercial_policies` | id, business_id, policy_type, configuration, is_active | N:1 Business |

---

## Migrations

| Migration | Description |
|-----------|-------------|
| 001_initial_schema | Initial database schema |
| 002_identity_auth_tenant | Identity, authentication, tenant tables |
| 003_business_profile_services | Business profiles, service offers |
| 004_enquiry_conversation | Enquiries, conversations, messages |
| 005_enquiry_brain_version | Brain version tracking on enquiries |
| 006_brain_version_active_unique | Active version uniqueness |
| 007_quote_booking | Quotes, bookings |
| 008_currency_columns | Currency columns |
| 009_phase13_service_execution_invoice_ledger | Service execution, invoices, ledger |
| 010_phase14a_communications_notifications | Communications, notifications, outbox |
| 011_phase14b_voice_call_agent | Voice calls, call agent |
| 012_phase14b_voice_runtime | Voice runtime enhancements |
| 013_phase15_payments | Payments, payment attempts, webhooks |
| 014_phase17_reviews | Reviews |
| 015_phase17_member_invitations | Business member invitations |
| 016_phase18_brain_conversation | Brain conversations, messages, proposals |
| 017_stripe_connect | Stripe Connect for business onboarding |
| 018_commercial_policy | Commercial policies for platform fees |
| 019_stripe_webhook | Stripe webhook event tracking |
| 020_agent_capabilities | Agent capabilities, delegations, execution logs |
| 021_calendar_connections | Google Calendar OAuth connections, sync records |
| 022_booking_automation_status | Booking automation operation tracking |

---

## Key Constraints

### Unique Constraints

- `users.email`: Unique email per user
- `businesses.slug`: Unique slug per business
- `service_offers.slug`: Unique slug per business
- `enquiries.reference`: Unique reference per enquiry
- `quotes.reference`: Unique reference per quote
- `bookings.reference`: Unique reference per booking
- `payments.idempotency_key`: Unique idempotency key per payment
- `conversations.enquiry_id`: One conversation per enquiry
- `reviews.service_execution_id`: One review per service execution
- `business_members.user_id, business_id`: One membership per user per business

### Foreign Key Constraints

- All relationships use foreign keys with appropriate cascade rules
- `ON DELETE CASCADE`: Delete child when parent deleted
- `ON DELETE RESTRICT`: Prevent parent deletion if children exist
- `ON DELETE SET NULL`: Set child FK to NULL when parent deleted

### Indexes

- All foreign keys indexed
- All status fields indexed
- All reference fields indexed
- Composite indexes for common queries

---

## Tenant Isolation

Tenant isolation is enforced at the repository layer:

- Every query includes tenant filtering
- Businesses only access their own data
- Customers only access their own data
- Cross-tenant access is impossible by design

---

## Audit Trail

All entities inherit from `BaseModel` which includes:

- `id`: UUID primary key
- `created_at`: Creation timestamp
- `updated_at`: Last update timestamp

Additional audit tracking via:

- `audit_events` table (not shown above)
- `outbox_events` table for event sourcing
- Evidence fields on quotes, bookings, payments

---

## JSONB Fields

Several entities use JSONB for flexible configuration:

- `brain_versions.*_config`: Brain configuration areas
- `business_rules.rule_data`: Structured rule data
- `quotes.pricing_evidence`: Pricing calculation evidence
- `bookings.decision_evidence`: Booking decision evidence
- `payments.provider_evidence`: Payment provider evidence
- `brain_messages.metadata`: Message metadata
- `brain_proposals.proposed_change`: Proposed brain changes

---

## Summary

The FIELDed data model consists of **56 tables** organized into **22 domain modules**, with **22 migrations**, comprehensive constraints, indexes, and tenant isolation. The model supports the complete customer-to-business transaction flow with full traceability and evidence tracking.
