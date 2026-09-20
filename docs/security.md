# FIELDed — Security

## Authentication

- **Password hashing**: bcrypt (local, no external dependency)
- **Token management**: JWT access + refresh tokens
- **Access tokens**: Short-lived (configurable, default 30 minutes)
- **Refresh tokens**: Longer-lived (configurable, default 7 days)
- **Token rotation**: Refresh endpoint issues new access + refresh token pair

## Authorization

- Server-side only — never trust client-supplied user_id, business_id, or role
- Resolved from authenticated identity + database relationships
- RBAC: customer, business_owner, business_admin, business_staff, platform_admin
- Business member roles: owner > admin > staff (hierarchical)

## Tenant Isolation

- Every database query scoped to authenticated user's tenant
- Repository pattern enforces isolation
- Businesses cannot access another business's data
- Customers can only access their own data
- Security tests verify cross-tenant isolation

## Input Validation

- Pydantic schemas validate all API inputs
- Database constraints enforce data integrity
- String length limits on all text fields
- Email format validation
- Password minimum length (8 characters)

## Transport Security

- HTTPS required in production
- CORS configured explicitly (no wildcard in production)
- Security headers via middleware

## Secrets Management

- No secrets in code — environment variables only
- Production environment validates that default secrets are replaced
- `.env` files excluded from version control

## Audit

- Structured logging with request/correlation IDs
- Every meaningful action generates audit events (Phase 10)
- Audit chain reconstructable for any transaction

## Rate Limiting

- Authentication endpoints rate-limited (future)
- API throttling per user/tenant (future)

## Future Enhancements

- CSRF protection for browser-based clients
- Webhook signature verification
- Prompt injection defenses for AI endpoints
- Two-factor authentication
- Account lockout after failed attempts
