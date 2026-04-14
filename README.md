# rfq_chatbot_ms

Phase-0 BACAB scaffold for the RFQ Copilot microservice. This service is intentionally minimal: it provides only the project structure, runtime bootstrap, and smoke endpoints needed before the real architecture brief is applied.

## Architecture

```text
routes/          -> API endpoints
controllers/     -> Reserved for later implementation
datasources/     -> Reserved for later implementation
translators/     -> Reserved for later implementation
models/          -> Reserved for later implementation
connectors/      -> Reserved for later implementation
config/          -> Environment-backed settings
utils/           -> Reserved for later implementation
```

`services/` is intentionally omitted in Phase 0 because there is no real cross-controller business workflow yet.

## Current Scope

- FastAPI application factory
- Fail-fast settings and database seam
- `GET /health`
- `GET /rfq-chatbot/v1/smoke`
- Minimal bootstrap tests and verification script

This scaffold does not include real copilot logic, orchestration, seeded data, business models, tool layers, or frozen persistence models.

## Quick Start

```bash
pip install -r requirements-dev.txt
uvicorn src.app:app --reload --port 8003
```

## Verification

```bash
python scripts/verify.py
```

The verifier runs:

1. `ruff check src tests scripts`
2. `pytest -q`
3. startup/import sanity via `create_app()`

## Configuration

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | Yes | None | SQLAlchemy connection URL. |
| `APP_ENV` | No | `development` | Runtime environment label. |
| `APP_DEBUG` | No | `false` | Enables SQLAlchemy echo logging when true. |
| `APP_PORT` | No | `8003` | Intended local service port. |
| `CORS_ORIGINS` | No | `*` | Comma-separated CORS allowlist. |
## Project Structure

```text
rfq_chatbot_ms/
|-- src/
|   |-- config/
|   |-- connectors/
|   |-- controllers/
|   |-- datasources/
|   |-- models/
|   |-- routes/
|   |-- translators/
|   |-- utils/
|   |-- app.py
|   |-- app_context.py
|   `-- database.py
|-- scripts/
|   `-- verify.py
|-- tests/
|   |-- integration/
|   `-- unit/
|-- requirements.txt
|-- requirements-dev.txt
`-- README.md
```
