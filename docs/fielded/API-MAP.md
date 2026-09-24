# FIELDed — API Map

**Status**: Current State Baseline  
**Last Updated**: 2026-09-24

---

## API Overview

- **Base URL**: `/api/v1/`
- **Protocol**: REST over HTTPS
- **Format**: JSON
- **Authentication**: JWT Bearer tokens
- **Total Endpoints**: ~75

---

## Health

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/health` | Health check | No |

---

## Authentication

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/auth/register` | User registration | No |
| POST | `/auth/login` | User login | No |
| POST | `/auth/refresh` | Refresh access token | Refresh Token |
| POST | `/auth/logout` | User logout | Yes |
| GET | `/auth/me` | Get current user | Yes |

---

## Customer

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/customer/profile` | Get customer profile | Yes (Customer) |
| PATCH | `/customer/profile` | Update customer profile | Yes (Customer) |

---

## Businesses

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/businesses` | Create business | Yes |
| GET | `/businesses` | List businesses | Yes |
| GET | `/businesses/{id}` | Get business | Yes |
| PATCH | `/businesses/{id}` | Update business | Yes (Owner/Admin) |
| POST | `/businesses/{id}/transition` | Transition business status | Yes (Owner) |
| GET | `/businesses/{id}/profile` | Get business profile | Yes |
| PATCH | `/businesses/{id}/profile` | Update business profile | Yes (Owner/Admin) |
| GET | `/businesses/{id}/members` | List business members | Yes (Member) |
| POST | `/businesses/{id}/members/invite` | Invite business member | Yes (Owner/Admin) |
| PATCH | `/businesses/{id}/members/{member_id}` | Update member role | Yes (Owner) |
| DELETE | `/businesses/{id}/members/{member_id}` | Remove member | Yes (Owner) |
| GET | `/businesses/{id}/settings` | Get business settings | Yes (Member) |
| PATCH | `/businesses/{id}/settings` | Update business settings | Yes (Owner/Admin) |

---

## Service Offers

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/businesses/{business_id}/service-offers` | Create service offer | Yes (Owner/Admin) |
| GET | `/businesses/{business_id}/service-offers` | List service offers | Yes |
| GET | `/businesses/{business_id}/service-offers/{id}` | Get service offer | Yes |
| PATCH | `/businesses/{business_id}/service-offers/{id}` | Update service offer | Yes (Owner/Admin) |
| POST | `/businesses/{business_id}/service-offers/{id}/transition` | Transition service offer | Yes (Owner/Admin) |

---

## Service Categories

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/categories` | List service categories | No |
| GET | `/categories/{id}` | Get service category | No |

---

## Public

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/public/businesses` | List public businesses | No |
| GET | `/public/businesses/{slug}` | Get public business profile | No |
| GET | `/public/businesses/{slug}/services` | List public service offers | No |
| GET | `/public/businesses/{slug}/services/{offerSlug}` | Get public service offer | No |

---

## Discovery

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/discovery/search` | Search businesses | No |
| POST | `/discovery/interpret` | Interpret search query | No |

---

## Enquiries

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/enquiries` | Create enquiry | Yes (Customer) |
| GET | `/enquiries` | List customer enquiries | Yes (Customer) |
| GET | `/enquiries/{id}` | Get enquiry | Yes (Customer/Business) |
| GET | `/enquiries/{id}/messages` | List messages | Yes (Customer/Business) |
| POST | `/enquiries/{id}/messages` | Send message | Yes (Customer/Business) |

---

## Business Enquiries

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/businesses/{business_id}/enquiries` | List business enquiries | Yes (Member) |
| GET | `/businesses/{business_id}/enquiries/{id}` | Get business enquiry | Yes (Member) |
| POST | `/businesses/{business_id}/enquiries/{id}/transition` | Transition enquiry | Yes (Member) |

---

## Quotes

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/businesses/{business_id}/quotes` | Create quote | Yes (Member) |
| GET | `/businesses/{business_id}/quotes` | List business quotes | Yes (Member) |
| GET | `/businesses/{business_id}/quotes/{id}` | Get quote | Yes (Customer/Business) |
| POST | `/businesses/{business_id}/quotes/{id}/accept` | Accept quote | Yes (Customer) |
| POST | `/businesses/{business_id}/quotes/{id}/decline` | Decline quote | Yes (Customer) |
| GET | `/businesses/my-quotes` | List customer quotes | Yes (Customer) |

---

## Bookings

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/businesses/{business_id}/bookings` | Create booking | Yes (Member) |
| GET | `/businesses/{business_id}/bookings` | List business bookings | Yes (Member) |
| GET | `/businesses/{business_id}/bookings/{id}` | Get booking | Yes (Customer/Business) |
| POST | `/businesses/{business_id}/bookings/{id}/transition` | Transition booking | Yes (Member) |
| GET | `/businesses/my-bookings` | List customer bookings | Yes (Customer) |

---

## Service Executions

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/businesses/{business_id}/service-executions` | Create execution | Yes (Member) |
| GET | `/businesses/{business_id}/service-executions` | List executions | Yes (Member) |
| GET | `/businesses/{business_id}/service-executions/{id}` | Get execution | Yes (Member) |
| POST | `/businesses/{business_id}/service-executions/{id}/start` | Start execution | Yes (Member) |
| POST | `/businesses/{business_id}/service-executions/{id}/complete` | Complete execution | Yes (Member) |

---

## Invoices

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/businesses/{business_id}/invoices` | List business invoices | Yes (Member) |
| GET | `/businesses/{business_id}/invoices/{id}` | Get invoice | Yes (Customer/Business) |
| GET | `/businesses/my-invoices` | List customer invoices | Yes (Customer) |

---

## Ledger

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/businesses/{business_id}/ledger` | List business ledger entries | Yes (Member) |
| GET | `/businesses/my-ledger` | List customer ledger entries | Yes (Customer) |

---

## Payments

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/payments` | Create payment | Yes (Customer) |
| GET | `/payments` | List customer payments | Yes (Customer) |
| GET | `/payments/{id}` | Get payment | Yes (Customer/Business) |
| POST | `/payments/{id}/refund` | Refund payment | Yes (Member) |
| POST | `/payments/webhooks/stripe` | Stripe webhook | No (Verified) |
| GET | `/businesses/{business_id}/payments` | List business payments | Yes (Member) |

---

## Reviews

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/reviews` | Create review | Yes (Customer) |
| GET | `/reviews` | List reviews | No |
| GET | `/reviews/{id}` | Get review | No |
| POST | `/reviews/{id}/respond` | Respond to review | Yes (Member) |
| GET | `/businesses/{business_id}/reviews` | List business reviews | No |

---

## Business Brain

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/businesses/{business_id}/brain` | Get business brain | Yes (Member) |
| POST | `/businesses/{business_id}/brain/versions` | Create brain version | Yes (Owner/Admin) |
| GET | `/businesses/{business_id}/brain/versions` | List brain versions | Yes (Member) |
| GET | `/businesses/{business_id}/brain/versions/{id}` | Get brain version | Yes (Member) |
| PATCH | `/businesses/{business_id}/brain/versions/{id}` | Update brain version | Yes (Owner/Admin) |
| POST | `/businesses/{business_id}/brain/versions/{id}/transition` | Transition version | Yes (Owner/Admin) |
| GET | `/businesses/{business_id}/brain/knowledge` | Get brain knowledge | Yes (Member) |
| GET | `/businesses/{business_id}/brain/context` | Get brain context | Yes (Member) |

---

## Brain Conversations

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/businesses/{business_id}/brain-conversations` | Create conversation | Yes (Owner/Admin) |
| GET | `/businesses/{business_id}/brain-conversations` | List conversations | Yes (Member) |
| GET | `/businesses/{business_id}/brain-conversations/{id}` | Get conversation | Yes (Member) |
| POST | `/businesses/{business_id}/brain-conversations/{id}/messages` | Send message | Yes (Owner/Admin) |
| GET | `/businesses/{business_id}/brain-conversations/{id}/messages` | List messages | Yes (Member) |

---

## Brain Proposals

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/businesses/{business_id}/brain-proposals` | List proposals | Yes (Member) |
| GET | `/businesses/{business_id}/brain-proposals/{id}` | Get proposal | Yes (Member) |
| POST | `/businesses/{business_id}/brain-proposals/{id}/approve` | Approve proposal | Yes (Owner/Admin) |
| POST | `/businesses/{business_id}/brain-proposals/{id}/reject` | Reject proposal | Yes (Owner/Admin) |

---

## Communications

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/communications` | List communications | Yes |
| GET | `/communications/{id}` | Get communication | Yes |
| GET | `/notifications` | List notifications | Yes |
| POST | `/notifications/{id}/read` | Mark notification read | Yes |

---

## Voice

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/voice/calls` | Request call | Yes (Member) |
| GET | `/voice/calls` | List calls | Yes (Member) |
| GET | `/voice/calls/{id}` | Get call | Yes (Member) |
| POST | `/voice/calls/{id}/cancel` | Cancel call | Yes (Member) |
| POST | `/voice/webhooks/twilio` | Twilio webhook | No (Verified) |
| POST | `/voice/campaigns` | Create campaign | Yes (Owner/Admin) |
| GET | `/voice/campaigns` | List campaigns | Yes (Member) |

---

## Member Invitations

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/members/accept-invitation` | Accept invitation | Yes |

---

## Summary

**Total Endpoints by Category**:

| Category | Count |
|----------|-------|
| Health | 1 |
| Authentication | 5 |
| Customer | 2 |
| Businesses | 13 |
| Service Offers | 5 |
| Service Categories | 2 |
| Public | 4 |
| Discovery | 2 |
| Enquiries | 5 |
| Business Enquiries | 3 |
| Quotes | 6 |
| Bookings | 5 |
| Service Executions | 5 |
| Invoices | 3 |
| Ledger | 2 |
| Payments | 6 |
| Reviews | 5 |
| Business Brain | 8 |
| Brain Conversations | 5 |
| Brain Proposals | 4 |
| Communications | 4 |
| Voice | 6 |
| Member Invitations | 1 |
| **TOTAL** | **~102** |

---

## Authentication Requirements

- **No Auth**: Public endpoints (health, register, login, public business profiles, search)
- **JWT Auth**: Protected endpoints (customer operations, business operations)
- **Role-Based**: Some endpoints require specific roles (Owner, Admin, Staff)
- **Tenant-Scoped**: All protected endpoints are tenant-scoped

---

## Error Responses

All errors follow this format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message",
    "details": {},
    "request_id": "uuid"
  }
}
```

Common error codes:
- `VALIDATION_ERROR`: Request validation failed
- `UNAUTHORIZED`: Authentication required
- `FORBIDDEN`: Insufficient permissions
- `NOT_FOUND`: Resource not found
- `STATE_TRANSITION_ERROR`: Invalid state transition
- `INTERNAL_ERROR`: Internal server error
