# FIELDed — API Conventions

## Base URL

All API routes are versioned under `/api/v1/`.

## Authentication

- Bearer JWT tokens in the `Authorization` header
- Access tokens for API calls
- Refresh tokens for obtaining new access tokens

## Request/Response Format

- Content-Type: `application/json`
- All timestamps in ISO 8601 format with timezone
- UUIDs as strings

## Error Response Format

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Resource not found",
    "details": {},
    "request_id": "abc-123"
  }
}
```

### Error Codes
| HTTP Status | Error Code | Meaning |
|-------------|-----------|---------|
| 400 | VALIDATION_ERROR | Invalid input |
| 401 | AUTHENTICATION_REQUIRED | Not authenticated |
| 403 | NOT_AUTHORIZED | Insufficient permissions |
| 404 | NOT_FOUND | Resource doesn't exist |
| 409 | CONFLICT | State conflict |
| 422 | DOMAIN_ERROR | Business rule violation |
| 500 | INTERNAL_ERROR | Server error |

## Headers

| Header | Direction | Purpose |
|--------|-----------|---------|
| `X-Request-ID` | Response | Unique request identifier |
| `X-Correlation-ID` | Both | Cross-service correlation |
| `Authorization` | Request | Bearer JWT token |

## Pagination

```
GET /api/v1/resources?page=1&page_size=20
```

Response includes:
```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "page_size": 20
}
```

## Resource Naming

- Plural nouns: `/users`, `/businesses`, `/service-offers`
- Nested resources: `/businesses/{id}/service-offers`
- Actions that change state: POST to action endpoint

## State Transition Endpoints

State changes use explicit action endpoints:
```
POST /api/v1/enquiries/{id}/submit
POST /api/v1/bookings/{id}/confirm
POST /api/v1/bookings/{id}/cancel
```

## Idempotency

Mutating operations should include an `Idempotency-Key` header where applicable.
