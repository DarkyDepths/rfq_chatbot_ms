# rfq_chatbot_ms

Phase 2 foundation for the RFQ Copilot microservice. The service currently includes typed persistence contracts, Alembic migration support, and the two-mode session model. It does not yet include the Phase 3 turn pipeline, Azure OpenAI integration, tool execution, or downstream manager/intelligence connectors.

## Architecture

```text
routes/          -> Health, smoke, and session HTTP endpoints
controllers/     -> Session mode orchestration and transition rules
datasources/     -> Session persistence CRUD
translators/     -> Thin request/response translation for current session routes
models/          -> Phase 1 typed contracts and ORM persistence models
connectors/      -> Reserved for later implementation
config/          -> Environment-backed settings
utils/           -> Shared application errors and future support utilities
```

`services/` is still intentionally omitted. The current Phase 2 orchestration is small enough to stay controller-led and BACAB-aligned.

## Current Scope

- FastAPI application factory
- Lazy settings access and SQLAlchemy database seam
- Phase 1 models and initial Alembic migration
- Phase 2 two-mode session behavior: `rfq_bound`, `portfolio`, `pending_pivot`
- `GET /health`
- `GET /rfq-chatbot/v1/smoke`
- `POST /rfq-chatbot/v1/sessions`
- `GET /rfq-chatbot/v1/sessions/{id}`
- `POST /rfq-chatbot/v1/sessions/{id}/bind-rfq`
- Unit and integration tests for the current slice

This service does not yet include chat turns, Azure OpenAI runtime behavior, context building, conversation orchestration, tool execution, manager/intelligence connectors, or Phase 3+ guardrails.

The architecture brief and staged implementation roadmap live in:

- `docs/rfq_chatbot_ms_architecture_brief_v2_F.html`
- `docs/implementation_plan_chatbot.md`

## Quick Start

```bash
pip install -r requirements-dev.txt
uvicorn src.app:app --reload --port 8003
```

## Verification

```bash
ruff check .
pytest
```

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
|-- docs/
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
|-- migrations/
|-- alembic.ini
|-- requirements.txt
|-- requirements-dev.txt
`-- README.md
```
