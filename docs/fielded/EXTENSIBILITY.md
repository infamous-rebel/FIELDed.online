# FIELDed — Extensibility Guide

**Status**: Current State Baseline  
**Last Updated**: 2026-09-24

---

## Overview

FIELDed's architecture is designed for extensibility. This document describes how new capabilities can be added without breaking the existing architecture.

---

## Extension Points

### 1. New Service Categories

**Existing Abstraction**: `ServiceCategory` model

**Where to Add**:
- Database: Insert into `service_categories` table
- Frontend: Update category browsing UI if needed

**Existing Interfaces**:
- `ServiceCategory` model
- Category listing API endpoints

**Database Impact**: New row in `service_categories`

**API Impact**: New category appears in category listings

**Frontend Impact**: Category appears in browsing UI

**Governance**: No governance implications

**Status**: ✅ Cleanly supported

---

### 2. New Service Types

**Existing Abstraction**: `ServiceOffer` model

**Where to Add**:
- Database: Extend `service_offers` table if needed
- Backend: Add new service type logic
- Frontend: Update service creation/editing UI

**Existing Interfaces**:
- `ServiceOffer` model
- Service offer API endpoints
- Service offer repository

**Database Impact**: May need new columns or related tables

**API Impact**: New service type supported in API

**Frontend Impact**: UI needs to support new service type

**Governance**: Brain may need new service configuration

**Status**: ✅ Cleanly supported

---

### 3. New Business Types

**Existing Abstraction**: `Business` model

**Where to Add**:
- Database: Extend `businesses` table if needed
- Backend: Add new business type logic
- Frontend: Update business onboarding UI

**Existing Interfaces**:
- `Business` model
- Business API endpoints
- Business repository

**Database Impact**: May need new columns

**API Impact**: New business type supported

**Frontend Impact**: UI needs to support new business type

**Governance**: Brain may need new identity configuration

**Status**: ✅ Cleanly supported

---

### 4. New Enquiry Types

**Existing Abstraction**: `Enquiry` model

**Where to Add**:
- Database: Extend `enquiries` table or add related tables
- Backend: Add new enquiry type logic
- Frontend: Update enquiry creation UI

**Existing Interfaces**:
- `Enquiry` model
- Enquiry API endpoints
- Enquiry repository
- Enquiry service

**Database Impact**: May need new columns or tables

**API Impact**: New enquiry type supported

**Frontend Impact**: UI needs to support new enquiry type

**Governance**: Brain may need new qualification rules

**Status**: ✅ Cleanly supported

---

### 5. New Quote Strategies

**Existing Abstraction**: `QuoteService`, pricing rules

**Where to Add**:
- Backend: Extend `QuoteService` or add new pricing logic
- Brain: Add new pricing rules

**Existing Interfaces**:
- `QuoteService`
- `PricingService`
- Brain pricing rules

**Database Impact**: May need new columns in `quotes`

**API Impact**: New quote strategy supported

**Frontend Impact**: Minimal (quote display already flexible)

**Governance**: Brain pricing rules govern new strategies

**Status**: ✅ Cleanly supported

---

### 6. New Booking/Workflow Types

**Existing Abstraction**: `Booking` model, booking service

**Where to Add**:
- Database: Extend `bookings` table if needed
- Backend: Extend booking service or add new workflow logic
- Frontend: Update booking UI

**Existing Interfaces**:
- `Booking` model
- `BookingService`
- Booking API endpoints

**Database Impact**: May need new columns

**API Impact**: New workflow type supported

**Frontend Impact**: UI needs to support new workflow

**Governance**: Brain availability rules may need extension

**Status**: ✅ Cleanly supported

---

### 7. New Payment Providers

**Existing Abstraction**: `PaymentProvider` interface

**Where to Add**:
- Backend: Implement `PaymentProvider` interface
- Adapters: Add new adapter in `app/adapters/payment/`
- Configuration: Add provider to `ProviderFactory`

**Existing Interfaces**:
- `PaymentProvider` abstract class
- `ProviderFactory`

**Database Impact**: None (provider-agnostic)

**API Impact**: New payment provider available

**Frontend Impact**: None (payment UI is provider-agnostic)

**Governance**: Payment provider must follow payment governance

**How to Add**:
1. Create new class implementing `PaymentProvider`
2. Implement all abstract methods
3. Add provider to `_resolve_payment_provider()` in `app/adapters/__init__.py`
4. Add configuration to `Settings` class
5. Add tests

**Status**: ✅ Cleanly supported

---

### 8. New Communication Providers

**Existing Abstraction**: Channel provider interfaces

**Where to Add**:
- Backend: Implement channel provider interface
- Adapters: Add new adapter in `app/adapters/<channel>/`
- Configuration: Add provider to `ProviderFactory`

**Existing Interfaces**:
- `EmailProvider`
- `SMSProvider`
- `VoiceProvider`
- `WhatsAppProvider`
- `PushProvider`

**Database Impact**: None (provider-agnostic)

**API Impact**: New communication provider available

**Frontend Impact**: None (communication UI is provider-agnostic)

**Governance**: Communication policy governs new providers

**How to Add**:
1. Create new class implementing channel provider interface
2. Implement all abstract methods
3. Add provider to appropriate resolver in `app/adapters/__init__.py`
4. Add configuration to `Settings` class
5. Add tests

**Status**: ✅ Cleanly supported

---

### 9. New AI Providers

**Existing Abstraction**: `AIProvider` interface

**Where to Add**:
- Backend: Implement `AIProvider` interface
- Adapters: Add new adapter in `app/adapters/ai/`
- Configuration: Add provider to `ProviderFactory`

**Existing Interfaces**:
- `AIProvider` abstract class
- `ProviderFactory`

**Database Impact**: None (provider-agnostic)

**API Impact**: New AI provider available

**Frontend Impact**: None (AI is backend-only)

**Governance**: AI governance applies to all providers

**How to Add**:
1. Create new class implementing `AIProvider`
2. Implement `complete()` and `complete_structured()` methods
3. Add provider to `_build_ai_provider()` in `app/adapters/__init__.py`
4. Add configuration to `Settings` class
5. Add tests

**Status**: ✅ Cleanly supported

---

### 10. New AI Workloads

**Existing Abstraction**: Workload-specific AI resolvers

**Where to Add**:
- Backend: Add workload-specific resolver
- Configuration: Add workload-specific settings

**Existing Interfaces**:
- `_resolve_discovery_ai_provider()`
- `_resolve_brain_ai_provider()`
- `_resolve_call_agent_ai_provider()`

**Database Impact**: None

**API Impact**: New workload available

**Frontend Impact**: Depends on workload

**Governance**: AI governance applies

**How to Add**:
1. Add workload-specific settings to `Settings` class
2. Add workload-specific resolver function
3. Use resolver in workload logic
4. Add tests

**Status**: ✅ Cleanly supported

---

### 11. New Business Brain Knowledge

**Existing Abstraction**: Brain configuration areas

**Where to Add**:
- Database: Add new configuration field to `BrainVersion`
- Backend: Add validation and evaluation logic
- Frontend: Add UI for new knowledge area

**Existing Interfaces**:
- `BrainVersion` model
- Brain validation logic
- Brain evaluation logic

**Database Impact**: New JSONB column in `brain_versions`

**API Impact**: New knowledge area in brain API

**Frontend Impact**: UI for new knowledge area

**Governance**: Brain governance applies

**How to Add**:
1. Add new configuration field to `BrainVersion` model
2. Add migration for new column
3. Add validation logic in `app/domain/business/validation.py`
4. Add evaluation logic
5. Add API endpoints
6. Add frontend UI
7. Add tests

**Status**: ✅ Cleanly supported

---

### 12. New Brain Proposal Types

**Existing Abstraction**: `BrainProposalType` enum

**Where to Add**:
- Database: Add new enum value
- Backend: Add proposal generation and application logic
- Frontend: Add UI for new proposal type

**Existing Interfaces**:
- `BrainProposalType` enum
- `BrainProposal` model
- Brain proposal service

**Database Impact**: New enum value

**API Impact**: New proposal type supported

**Frontend Impact**: UI for new proposal type

**Governance**: Brain governance applies

**How to Add**:
1. Add new value to `BrainProposalType` enum
2. Add proposal generation logic
3. Add proposal application logic
4. Add frontend UI
5. Add tests

**Status**: ✅ Cleanly supported

---

### 13. New Business Rules

**Existing Abstraction**: `BusinessRule` model

**Where to Add**:
- Database: Add new rule type
- Backend: Add validation and evaluation logic
- Frontend: Add UI for new rule type

**Existing Interfaces**:
- `BusinessRule` model
- Rule validation logic
- Rule evaluation logic

**Database Impact**: New rule type in `business_rules`

**API Impact**: New rule type supported

**Frontend Impact**: UI for new rule type

**Governance**: Brain governance applies

**How to Add**:
1. Add new rule type to registry
2. Add validation logic
3. Add evaluation logic
4. Add frontend UI
5. Add tests

**Status**: ✅ Cleanly supported

---

### 14. New Agents

**Existing Abstraction**: Call agent architecture

**Where to Add**:
- Backend: Add new agent logic
- AI: Configure agent with AI provider

**Existing Interfaces**:
- Call agent service
- AI provider interface

**Database Impact**: May need new tables

**API Impact**: New agent available

**Frontend Impact**: UI for new agent

**Governance**: Agent governance applies

**Status**: ✅ Cleanly supported

---

### 15. New Workflow Adapters

**Existing Abstraction**: Domain services

**Where to Add**:
- Backend: Add new workflow logic
- Frontend: Add UI for new workflow

**Existing Interfaces**:
- Domain services
- API endpoints

**Database Impact**: May need new tables

**API Impact**: New workflow available

**Frontend Impact**: UI for new workflow

**Governance**: Depends on workflow

**Status**: ✅ Cleanly supported

---

### 16. New External Integrations

**Existing Abstraction**: Adapter pattern

**Where to Add**:
- Backend: Implement adapter interface
- Adapters: Add new adapter
- Configuration: Add provider settings

**Existing Interfaces**:
- Provider interfaces
- `ProviderFactory`

**Database Impact**: None (provider-agnostic)

**API Impact**: New integration available

**Frontend Impact**: Depends on integration

**Governance**: Depends on integration

**How to Add**:
1. Define adapter interface
2. Implement adapter
3. Add to `ProviderFactory`
4. Add configuration
5. Add tests

**Status**: ✅ Cleanly supported

---

### 17. New Evidence Sources

**Existing Abstraction**: Evidence fields on entities

**Where to Add**:
- Database: Add evidence field to entity
- Backend: Populate evidence field

**Existing Interfaces**:
- Entity models
- Repository pattern

**Database Impact**: New JSONB column

**API Impact**: Evidence available in API

**Frontend Impact**: Display evidence if needed

**Governance**: Evidence tracking enhanced

**Status**: ✅ Cleanly supported

---

### 18. New Audit Events

**Existing Abstraction**: `AuditEventType` enum

**Where to Add**:
- Database: Add new enum value
- Backend: Generate audit event

**Existing Interfaces**:
- `AuditEventType` enum
- Audit event service

**Database Impact**: New enum value

**API Impact**: New event type available

**Frontend Impact**: Display new event type if needed

**Governance**: Audit trail enhanced

**How to Add**:
1. Add new value to `AuditEventType` enum
2. Generate audit event in appropriate service
3. Add tests

**Status**: ✅ Cleanly supported

---

## Extension Best Practices

1. **Follow Existing Patterns**: Use existing abstractions and patterns
2. **Provider-Agnostic**: Use adapter pattern for external services
3. **Tenant-Scoped**: Ensure new features respect tenant isolation
4. **State Machines**: Use explicit state machines for lifecycles
5. **Audit Trail**: Generate audit events for meaningful actions
6. **Evidence Tracking**: Track evidence for critical decisions
7. **Governance**: Follow AI governance principles
8. **Testing**: Add comprehensive tests
9. **Documentation**: Document new extensions
10. **Migration**: Add database migrations for schema changes

---

## Summary

FIELDed's architecture supports clean extension in all major areas:

- ✅ New service categories, types, business types
- ✅ New enquiry types, quote strategies, booking workflows
- ✅ New payment, communication, AI providers
- ✅ New AI workloads, brain knowledge, proposal types
- ✅ New business rules, agents, workflow adapters
- ✅ New external integrations, evidence sources, audit events

The architecture is **designed for extensibility** while maintaining **deterministic authority**, **tenant isolation**, and **governance**.
