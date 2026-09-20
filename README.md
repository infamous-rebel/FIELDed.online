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

## Architecture

See [docs/](docs/) for full architectural documentation.
