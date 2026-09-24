# FIELDed

Customer-to-business service network.

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 20+
- PostgreSQL 16
- Redis 7+

### Local Development

```bash
# 1. Start infrastructure
docker compose -f docker/docker-compose.yml up -d

# 2. Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example ../.env
uvicorn app.main:app --reload

# 3. Frontend
cd frontend
npm install
npm run dev
```

### Running Tests

```bash
# Backend
cd backend
pytest

# Frontend
cd frontend
npm test
```

## Documentation

### Comprehensive Current-State Documentation

For complete current-state documentation, see [docs/fielded/](docs/fielded/README.md):

- [Product Definition](docs/fielded/PRODUCT.md) — What FIELDed currently is
- [Feature Inventory](docs/fielded/FEATURES.md) — Complete feature status (212 features documented)
- [Architecture](docs/fielded/ARCHITECTURE.md) — System architecture overview
- [Architecture Diagrams](docs/fielded/ARCHITECTURE-DIAGRAMS.md) — Mermaid diagrams
- [Business Brain](docs/fielded/BUSINESS-BRAIN.md) — Brain deep dive
- [AI Architecture](docs/fielded/AI-ARCHITECTURE.md) — AI provider architecture
- [E2E Walkthrough](docs/fielded/E2E.md) — End-to-end transaction guide
- [Integrations](docs/fielded/INTEGRATIONS.md) — External integrations
- [Data Model](docs/fielded/DATA-MODEL.md) — Database schema
- [API Map](docs/fielded/API-MAP.md) — Complete API endpoint map
- [Workflows](docs/fielded/WORKFLOWS.md) — State machines and workflows
- [Extensibility](docs/fielded/EXTENSIBILITY.md) — Extension points
- [Gaps](docs/fielded/GAPS.md) — Architecture and implementation gaps
- [Verification](docs/fielded/VERIFICATION.md) — Test coverage
- [Specifications](docs/fielded/SPECIFICATIONS.md) — Specification status
- [E2E Readiness](docs/fielded/E2E-READINESS.md) — E2E testing readiness

### Additional Documentation

See [docs/](docs/) for additional architectural documentation including:
- [Business Brain Specification](docs/business-brain-specification.md)
- [AI Governance](docs/ai-governance.md)
- [Authorization Model](docs/authorization-model.md)
- [Customer Journey](docs/customer-journey.md)
- [Testing Strategy](docs/testing-strategy.md)
- And more...
