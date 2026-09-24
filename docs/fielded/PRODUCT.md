# FIELDed — Product Definition

**Status**: Current State Baseline  
**Last Updated**: 2026-09-24

---

## What FIELDed Is

FIELDed is a **customer-to-business service network** where customers describe what they need, discover businesses capable of fulfilling it, initiate service enquiries, communicate with businesses, receive quotes, book services, and review completed services — while every business operates through its own governed Business Brain.

---

## Currently Implemented Product

### Customer Side

#### Authentication & Profile
- **User Registration**: Email/password signup with bcrypt password hashing
- **User Login**: JWT-based authentication with access/refresh token rotation
- **Customer Profile**: First name, last name, phone, address fields
- **Profile Status**: INCOMPLETE → ACTIVE → SUSPENDED lifecycle

#### Discovery & Search
- **Business Search**: Text-based search across business names and descriptions
- **Service Category Browsing**: Browse businesses by service category
- **Business Profile Pages**: Public-facing business profiles with logo, description, contact info, location
- **Service Offer Viewing**: View individual service offers with pricing, delivery mode, description
- **AI-Powered Discovery**: Natural language search interpretation (when AI provider configured)

#### Enquiry Journey
- **Enquiry Creation**: Customers can initiate enquiries against service offers
- **Enquiry Lifecycle**: DRAFT → SUBMITTED → RECEIVED → IN_REVIEW → NEEDS_INFORMATION → QUOTED → CUSTOMER_ACCEPTED → BOOKING_PROPOSED → BOOKED → IN_PROGRESS → COMPLETED
- **Conversation**: Each enquiry has exactly one conversation for bidirectional messaging
- **Message Exchange**: Customer and business member messaging within conversations
- **Enquiry Reference**: Customer-friendly reference numbers (e.g., ENQ-a1b2c3d4)

#### Quote Management
- **Quote Receipt**: Customers receive quotes with amount, currency, notes
- **Quote Lifecycle**: DRAFT → ISSUED → ACCEPTED / DECLINED / EXPIRED
- **Quote Acceptance**: Customers can accept quotes to proceed to booking
- **Quote Reference**: Customer-friendly reference numbers (e.g., QUO-a1b2c3d4)
- **Pricing Evidence**: Quotes retain brain version ID and pricing evidence for traceability

#### Booking Management
- **Booking Creation**: After quote acceptance, bookings are created with scheduled time
- **Booking Lifecycle**: REQUESTED → PROPOSED → ACCEPTED → CONFIRMED → IN_PROGRESS → COMPLETED
- **Exception States**: DECLINED, CANCELLED, EXPIRED, NO_SHOW
- **Booking Reference**: Customer-friendly reference numbers (e.g., BKG-a1b2c3d4)
- **Brain Traceability**: Bookings retain brain version ID and decision evidence

#### Payment & Financial
- **Payment Initiation**: Customers can initiate payments against invoices
- **Payment Lifecycle**: PENDING → PROCESSING → SUCCEEDED / FAILED / EXPIRED / CANCELLED
- **Refund Track**: SUCCEEDED → REFUNDED / PARTIALLY_REFUNDED
- **Payment Methods**: CARD, BANK_TRANSFER, CASH, DIGITAL_WALLET, OTHER
- **Idempotency**: Payments use idempotency keys to prevent duplicates
- **Invoice Receipt**: Customers receive invoices for services
- **Ledger Access**: Customers can view financial transaction records

#### Service Execution & Completion
- **Service Execution Tracking**: Execution lifecycle SCHEDULED → IN_PROGRESS → COMPLETED
- **Exception States**: CANCELLED, NO_SHOW
- **Completion Cascade**: Service execution completion cascades to booking completion
- **Invoice Generation**: Invoices generated upon service completion
- **Ledger Entries**: Financial ledger entries created for transactions

#### Reviews & Trust
- **Review Submission**: Customers can submit reviews for completed services
- **Review Eligibility**: Deterministic eligibility (completed execution + valid booking + correct customer)
- **Rating System**: Numeric rating (1-5)
- **Review Content**: Title, body, rating
- **Business Response**: Businesses can respond to reviews
- **Review Visibility**: Reviews have visible/hidden status
- **Trust Chain**: Reviews linked to full transaction chain (execution → booking → enquiry → service offer)

#### Customer Dashboard
- **Dashboard Overview**: Summary of enquiries, bookings, payments
- **Enquiries List**: View all customer enquiries with status
- **Bookings List**: View all customer bookings with status
- **Quotes List**: View all customer quotes with status
- **Payments List**: View all customer payments with status
- **Transaction History**: View completed transactions
- **Service History**: View previously used services
- **Profile Management**: Update customer profile information
- **Account Settings**: Manage account settings

---

### Business Side

#### Authentication & Onboarding
- **Business User Registration**: Same as customer registration
- **Business Creation**: Create business with name, slug, currency
- **Business Member Invitation**: Invite other users to join business
- **Member Roles**: OWNER, ADMIN, STAFF with different permissions
- **Business Onboarding Flow**: Guided onboarding for new businesses

#### Business Profile Management
- **Business Profile**: Description, logo, cover image, website, phone, email
- **Location**: Address fields (address line 1/2, city, state, postal code, country)
- **Social Links**: Facebook, Instagram, LinkedIn URLs
- **Service Area**: Structured geographic service area (JSONB)
- **Trust Signals**: Average rating, review count, verification status
- **Public Profile Status**: INCOMPLETE → ACTIVE → SUSPENDED
- **Business Status**: PENDING → ACTIVE → SUSPENDED → DEACTIVATED

#### Service Catalog Management
- **Service Offer Creation**: Create service offers with name, slug, description
- **Pricing Models**: FIXED, HOURLY, QUOTE_REQUIRED, STARTING_AT, CUSTOM
- **Delivery Modes**: ON_SITE, REMOTE, IN_STORE, HYBRID
- **Service Categories**: Categorize services
- **Service Lifecycle**: DRAFT → ACTIVE → PAUSED → ARCHIVED
- **Pricing Configuration**: Base price, currency, pricing rules
- **Service Slug**: URL-friendly service identifiers

#### Business Brain
- **Brain Container**: Each business has exactly one BusinessBrain
- **Brain Versions**: Versioned configurations with lifecycle DRAFT → VALIDATING → REVIEW → APPROVED → ACTIVE → SUPERSEDED
- **Configuration Areas**:
  - Identity: Business identity rules
  - Services: Service catalog rules
  - Pricing: Pricing rules and strategies
  - Availability: Availability schedules and rules
  - Qualification: Customer qualification rules
  - Policies: Business policies
  - Escalation: Escalation rules
  - Communication: Communication preferences
- **Business Rules**: Structured rules within versions (pricing, policy, qualification, availability, escalation)
- **Rule Priority**: Rules have priority ordering
- **Active Version**: Only one version is ACTIVE at a time
- **Immutability**: Once a version leaves DRAFT, its configuration is immutable
- **Brain Conversations**: Interactive conversations between Brain and owner
- **Brain Messages**: Messages within conversations (BRAIN, OWNER, SYSTEM roles)
- **Brain Proposals**: AI-generated proposals for business knowledge
- **Proposal Types**: NEW_SERVICE, PRICING_RULE, POLICY_RULE, AVAILABILITY_RULE, QUALIFICATION_RULE, ESCALATION_RULE, IDENTITY_UPDATE, COMMUNICATION_UPDATE, GENERAL_KNOWLEDGE
- **Proposal Lifecycle**: PENDING → APPROVED / EDITED / REJECTED → APPLIED
- **Proposal Governance**: AI never silently mutates production Brain state
- **Confidence Scoring**: Proposals include confidence scores
- **Reasoning Summary**: Proposals include reasoning summaries

#### Enquiry Handling
- **Enquiry Reception**: Receive customer enquiries
- **Enquiry Review**: Review enquiry details and customer information
- **Conversation Participation**: Business members can participate in enquiry conversations
- **Enquiry Status Management**: Transition enquiry through lifecycle states
- **Business Enquiry List**: View all business enquiries
- **Enquiry Detail**: View individual enquiry with conversation history

#### Quote Management
- **Quote Creation**: Create quotes for enquiries
- **Quote Pricing**: Deterministic pricing from service offer and brain rules
- **Quote Issuance**: Issue quotes to customers
- **Quote Tracking**: Track quote status (DRAFT, ISSUED, ACCEPTED, DECLINED, EXPIRED)
- **Quote List**: View all business quotes

#### Booking Management
- **Booking Creation**: Create bookings after quote acceptance
- **Availability Checking**: Check availability before booking
- **Booking Confirmation**: Confirm bookings
- **Booking Status Management**: Transition booking through lifecycle states
- **Booking List**: View all business bookings
- **Service Execution Start**: Start service execution from confirmed bookings

#### Service Execution Management
- **Execution Creation**: Create service executions for bookings
- **Execution Status Management**: Transition execution through lifecycle states
- **Execution Completion**: Mark executions as completed
- **Completion Cascade**: Completion cascades to booking and enquiry

#### Payment & Financial Management
- **Payment Receipt**: View payments received from customers
- **Payment Status Tracking**: Track payment status
- **Invoice Management**: Create and manage invoices
- **Invoice Lifecycle**: DRAFT → ISSUED → VOID
- **Invoice Payment Status**: UNPAID → PARTIALLY_PAID → PAID → FAILED → REFUNDED
- **Ledger Access**: View financial ledger entries
- **Financial Dashboard**: View financial summary

#### Review Management
- **Review Reception**: View customer reviews
- **Review Response**: Respond to customer reviews
- **Review List**: View all business reviews
- **Rating Aggregation**: Average rating calculated from reviews

#### Communications Hub
- **Communications Dashboard**: View all communications
- **Notification Management**: View notifications
- **Communication History**: View communication history

#### Business Dashboard
- **Dashboard Overview**: Summary of enquiries, bookings, payments, reviews
- **Enquiries List**: View all business enquiries
- **Bookings List**: View all business bookings
- **Quotes List**: View all business quotes
- **Payments List**: View all business payments
- **Services List**: View all service offers
- **Brain Page**: Access Business Brain
- **Finance Page**: View financial information
- **Schedule Page**: View booking schedule
- **Operations Page**: View operational information
- **Settings Page**: Manage business settings

#### Business Settings
- **Business Profile Settings**: Update business profile
- **Communication Settings**: Configure communication preferences
- **Member Management**: Manage business members and roles
- **Business Status Management**: Activate/deactivate business

---

### Business Network

#### Discovery
- **Public Business Directory**: Browse all active businesses
- **Business Search**: Search businesses by name
- **Business Profile Viewing**: View public business profiles
- **Service Offer Viewing**: View service offers from business profiles

---

### Enquiry Lifecycle

The enquiry lifecycle is the core transaction flow:

1. **DRAFT**: Enquiry created but not submitted
2. **SUBMITTED**: Enquiry submitted to business
3. **RECEIVED**: Business received enquiry
4. **IN_REVIEW**: Business reviewing enquiry
5. **NEEDS_INFORMATION**: Business requests more information
6. **QUOTED**: Business issued quote
7. **CUSTOMER_ACCEPTED**: Customer accepted quote
8. **BOOKING_PROPOSED**: Booking proposed
9. **BOOKED**: Booking confirmed
10. **IN_PROGRESS**: Service in progress
11. **COMPLETED**: Service completed

**Terminal States**: DECLINED, CANCELLED, EXPIRED, REJECTED

---

### Service/Offer Model

Service offers represent what businesses provide:

- **Name**: Service name
- **Slug**: URL-friendly identifier
- **Description**: Service description
- **Pricing Model**: FIXED, HOURLY, QUOTE_REQUIRED, STARTING_AT, CUSTOM
- **Base Price**: Base price amount
- **Currency**: ISO 4217 currency code
- **Delivery Mode**: ON_SITE, REMOTE, IN_STORE, HYBRID
- **Category**: Service category
- **Status**: DRAFT, ACTIVE, PAUSED, ARCHIVED
- **Duration**: Estimated duration
- **Business**: Owning business

---

### Quote Lifecycle

1. **DRAFT**: Quote created but not issued
2. **ISSUED**: Quote issued to customer
3. **ACCEPTED**: Customer accepted quote
4. **DECLINED**: Customer declined quote
5. **EXPIRED**: Quote expired

---

### Booking Lifecycle

1. **REQUESTED**: Booking requested
2. **PROPOSED**: Booking proposed to customer
3. **ACCEPTED**: Customer accepted booking
4. **CONFIRMED**: Booking confirmed
5. **IN_PROGRESS**: Service in progress
6. **COMPLETED**: Service completed

**Exception States**: DECLINED, CANCELLED, EXPIRED, RESCHEDULED, NO_SHOW

---

### Payment Lifecycle

1. **PENDING**: Payment initiated
2. **PROCESSING**: Payment being processed
3. **SUCCEEDED**: Payment succeeded
4. **FAILED**: Payment failed
5. **EXPIRED**: Payment expired
6. **CANCELLED**: Payment cancelled

**Refund Track**:
- **SUCCEEDED** → **REFUNDED** (full refund)
- **SUCCEEDED** → **PARTIALLY_REFUNDED**
- **PARTIALLY_REFUNDED** → **REFUNDED**

---

### Service Execution

1. **SCHEDULED**: Execution scheduled
2. **IN_PROGRESS**: Execution in progress
3. **COMPLETED**: Execution completed
4. **CANCELLED**: Execution cancelled
5. **NO_SHOW**: Customer no-show

---

### Completion

Service completion cascades:
1. Service execution marked COMPLETED
2. Booking marked COMPLETED
3. Enquiry marked COMPLETED
4. Invoice generated
5. Ledger entries created
6. Review becomes eligible

---

### Review

Reviews require:
- Completed service execution
- Valid booking (not cancelled/declined)
- Correct customer (owns the transaction)
- Correct business (owns the execution)
- No existing review (UNIQUE constraint)

---

### Communications

#### Channels
- **EMAIL**: Email communications (Resend adapter)
- **SMS**: SMS communications (Twilio adapter)
- **WHATSAPP**: WhatsApp communications (stub)
- **PUSH**: Push notifications (stub)
- **IN_APP**: In-app notifications
- **VOICE**: Voice calls (Twilio adapter)

#### Notification Types
- Transactional notifications
- Service notifications
- Reminders
- Follow-ups
- Authentication
- Payment notifications
- Invoice notifications

---

### Business Brain

#### AI Intelligence vs Business Authority

**AI Can**:
- Interpret customer enquiries
- Extract business knowledge from conversations
- Propose new services, pricing rules, policies
- Suggest availability and qualification rules
- Generate reasoning summaries
- Provide confidence scores

**AI Cannot**:
- Set or change prices without business rule validation
- Determine availability without checking deterministic constraints
- Override business policies
- Authorize customers or grant permissions
- Change booking/transaction state directly
- Determine review eligibility
- Silently mutate production Brain state

#### Governance Flow

1. **Conversation**: Owner interacts with Brain
2. **Proposal Generation**: AI generates structured proposal
3. **Proposal Review**: Owner reviews proposal
4. **Approval Decision**: Owner approves/rejects/edits
5. **Application**: Approved proposal applied to Brain state
6. **Version Update**: New Brain version created if needed

---

### AI/Provider Architecture

#### Provider Abstraction
All external services use adapter interfaces:
- **AIProvider**: AI/LLM services
- **EmailProvider**: Email services
- **SMSProvider**: SMS services
- **VoiceProvider**: Voice call services
- **WhatsAppProvider**: WhatsApp services
- **PushProvider**: Push notification services
- **PaymentProvider**: Payment services

#### Provider Configuration
Providers are selected via environment variables:
- `AI_PROVIDER`: mock, openai, groq
- `EMAIL_PROVIDER`: mock, resend
- `SMS_PROVIDER`: mock, twilio
- `VOICE_PROVIDER`: mock, twilio
- `PAYMENT_PROVIDER`: mock, stripe

#### Workload-Specific AI Providers
Different AI workloads can use different providers/keys:
- **Discovery**: `DISCOVERY_AI_API_KEY`, `DISCOVERY_AI_BASE_URL`
- **Brain**: `BRAIN_AI_API_KEY`, `BRAIN_AI_BASE_URL`
- **Call Agent**: `CALL_AGENT_AI_API_KEY`, `CALL_AGENT_AI_BASE_URL`

Fallback to global `AI_API_KEY` and `AI_BASE_URL` when workload-specific keys not set.

---

### Governance/Approval Model

#### Brain Version Approval
1. DRAFT → VALIDATING (system validation)
2. VALIDATING → REVIEW (structural validation required)
3. REVIEW → APPROVED (owner approval)
4. APPROVED → ACTIVE (activation)
5. ACTIVE → SUPERSEDED (when new version activated)

#### Proposal Approval
1. PENDING (AI proposed)
2. APPROVED / EDITED / REJECTED (owner decision)
3. APPLIED (approved change applied to Brain state)

---

### Audit/Evidence Model

#### Audit Events
Every meaningful action generates audit events:
- Communication events (REQUESTED, SENT, DELIVERED, FAILED)
- Call events (REQUESTED, INITIATED, CONNECTED, COMPLETED, FAILED)
- Payment events (INITIATED, PROCESSING, SUCCEEDED, FAILED, REFUNDED)
- Review events (SUBMITTED, RESPONDED)
- Member events (INVITED, ACCEPTED, ROLE_CHANGED, REMOVED)
- Business events (STATUS_CHANGED, PROFILE_STATUS_CHANGED)

#### Evidence Tracking
- Quotes retain pricing evidence
- Bookings retain decision evidence
- Payments retain provider evidence
- Reviews linked to full transaction chain
- Brain versions retain configuration snapshots

---

## Intended/Future Product

The following capabilities are specified or intended but not fully implemented:

### Not Yet Fully Implemented
- Real payment processing (Stripe adapter exists but not fully tested E2E)
- Real email delivery (Resend adapter exists but not fully tested E2E)
- Real SMS delivery (Twilio adapter exists but not fully tested E2E)
- Real voice calls (Twilio adapter exists but not fully tested E2E)
- Real WhatsApp integration (stub only)
- Real push notifications (stub only)
- Advanced availability scheduling
- Complex pricing rules (tiered, volume-based)
- Multi-currency support (currency field exists but not fully implemented)
- Advanced search filters
- Business verification workflow
- Platform admin dashboard
- Advanced reporting and analytics
- Mobile apps

### Extension Points
The architecture supports future extension in these areas:
- New service categories
- New service types
- New business types
- New enquiry types
- New quote strategies
- New booking/workflow types
- New payment providers
- New communication providers
- New AI providers
- New AI workloads
- New Business Brain knowledge types
- New Brain proposal types
- New business rules
- New agents
- New workflow adapters
- New external integrations
- New evidence sources
- New audit events

See [EXTENSIBILITY.md](EXTENSIBILITY.md) for detailed extension point documentation.

---

## Summary

FIELDed currently implements a complete customer-to-business service network with:
- Full customer journey from discovery to review
- Complete business operations platform
- AI-governed Business Brain with proposal/approval workflow
- Comprehensive state machines for all lifecycles
- Provider-agnostic architecture
- Tenant isolation
- Audit trail
- Evidence tracking

The architecture is designed for extensibility while maintaining deterministic authority over critical business logic.
