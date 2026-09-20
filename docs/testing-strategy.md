# FIELDed — Testing Strategy

## Test Categories

### Unit Tests
Test individual functions and business logic in isolation.
- Password hashing and verification
- JWT token creation and validation
- State machine transition validation
- Configuration loading and validation
- Authorization role hierarchy
- Pricing rule evaluation (future)
- Availability calculation (future)

### Integration Tests
Test component interactions with real database.
- Authentication flow (register → login → access protected route → refresh)
- Database migrations apply cleanly
- Tenant isolation at repository layer
- CRUD operations on domain entities
- Business Brain version lifecycle

### Security Tests
Verify that authorization and isolation work correctly.
- Cross-tenant access attempts fail
- Invalid/expired tokens rejected
- Missing auth headers rejected
- Different users see different data
- Malformed tokens rejected
- Request ID present in all responses

### AI Evaluation Tests (future)
- Intent extraction accuracy
- Hallucinated services prevented
- Hallucinated prices prevented
- Prompt injection resistance
- Malformed structured output handling
- Ambiguous request handling

### E2E Tests (future)
- Customer: signup → search → business → enquiry → message → quote → booking → completion → review
- Business: signup → Brain setup → publish → enquiry → response → quote → booking → completion

## Test Infrastructure

### Backend
- **Framework**: pytest + pytest-asyncio
- **HTTP client**: httpx (AsyncClient with ASGITransport)
- **Database**: Dedicated test database (fielded_test), tables created/dropped per session
- **Fixtures**: Test users, auth headers, database sessions with rollback
- **Factories**: Factory functions for all domain models

### Frontend
- **Framework**: Vitest
- **Component tests**: React Testing Library (future)

## Test Organization

```
tests/
├── conftest.py          # Shared fixtures
├── factories.py         # Test data factories
├── unit/                # Pure logic tests
├── integration/         # Component interaction tests
└── security/            # Authorization/isolation tests
```

## Running Tests

```bash
# All tests
cd backend && pytest

# Unit only
pytest tests/unit/

# Integration (requires test database)
pytest tests/integration/

# Security
pytest tests/security/

# With coverage
pytest --cov=app --cov-report=html
```

## Test Rules

- No mock behavior presented as production behavior
- Tests must use real database (no SQLite substitutes)
- Security tests mandatory for all authorization changes
- State machine tests mandatory for all lifecycle changes
