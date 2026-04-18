# rfq_chatbot_ms

Phase 6 baseline for the RFQ Copilot microservice. The service keeps the stable typed persistence contracts and two-mode session model while adding intent-aware routing, grounding-enforced RFQ-specific behavior, disambiguation-capable portfolio handling, soft output guardrails, and structured observability fields.

## What This Service Does

This service keeps the external HTTP/API contract stable while making conversational behavior context-aware across both RFQ-bound and portfolio turns. It classifies turn intent deterministically, routes turns by intent boundary, adapts responses using stage and role context, applies grounding and capability-status rules, and preserves provenance through `source_refs` without expanding response DTO shape.

## Architecture

```text
routes/          -> Health, smoke, session, and chat HTTP endpoints
controllers/     -> Session mode, conversation persistence, prompt assembly, and chat orchestration
datasources/     -> Session and conversation persistence CRUD
translators/     -> Thin request/response translation for session and chat routes
models/          -> Phase 1 typed contracts and ORM persistence models
connectors/      -> Azure OpenAI plus read-only manager/intelligence connectors
config/          -> Environment-backed settings
utils/           -> Shared application errors and future support utilities
```

`services/` is still intentionally omitted. The current controller-led orchestration remains small enough to stay BACAB-aligned without adding a separate services layer.

## Current Scope

- FastAPI application factory
- Lazy settings access and SQLAlchemy database seam
- Phase 1 models and initial Alembic migration
- Phase 2 two-mode session behavior: `rfq_bound`, `portfolio`, `pending_pivot`
- Phase 3 first conversational vertical slice with persisted conversation history
- Phase 4 typed downstream retrieval for RFQ-bound turns
- `GET /health`
- `GET /rfq-chatbot/v1/smoke`
- `POST /rfq-chatbot/v1/sessions`
- `GET /rfq-chatbot/v1/sessions/{id}`
- `POST /rfq-chatbot/v1/sessions/{id}/bind-rfq`
- `POST /rfq-chatbot/v1/sessions/{session_id}/turn`
- `GET /rfq-chatbot/v1/conversations/{conversation_id}`
- Unit and integration tests for the current slice

Phase 5/6 behavior is configured declaratively in:

- `src/config/stage_profiles.py`
- `src/config/role_profiles.py`
- `src/config/intent_patterns.py`
- `src/config/disambiguation_config.py`

This service does not yet include Phase 7+ behavior: LLM-based intent classification, semantic hallucination detection, hard output-guardrail enforcement, portfolio analytics/retrieval tooling, or contract redesign.

The architecture brief and staged implementation roadmap live in:

- `docs/rfq_chatbot_ms_architecture_brief_v2_F.html`
- `docs/implementation_plan_chatbot.md`

## Quick Start

```bash
pip install -r requirements-dev.txt
uvicorn src.app:app --reload --port 8003
```

To exercise the chat path locally, configure Azure OpenAI with the same shape used by the deployment guide:

```bash
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_API_KEY="your-api-key"
export AZURE_OPENAI_API_VERSION="2024-12-01-preview"
export AZURE_OPENAI_CHAT_DEPLOYMENT="gpt-5-nano"
export AZURE_OPENAI_TIMEOUT_SECONDS="30.0"
```

For retrieval-backed turns, set downstream URLs too:

```bash
export MANAGER_BASE_URL="http://localhost:8000"
export INTELLIGENCE_BASE_URL="http://localhost:8002"
```

Phase 4 retrieval is intentionally limited to RFQ-bound sessions whose stored `rfq_id`
is already the downstream RFQ UUID. Human-readable RFQ codes such as `IF-25144`
are not resolved in this phase and will fail with an explicit `422`.

Current Phase 4 retrieval is deterministic keyword-routed retrieval, not Azure
function calling. This is an intentional Phase 4 stabilization choice: true
LLM-driven tool selection is deferred to a later phase.

After retrieval validation succeeds and the user message is persisted, an Azure
completion failure may still leave a user-only turn in conversation history.
This residual behavior is accepted for now because it matches standard chat retry
semantics and avoids a broader transaction refactor in this stabilization pass.

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
| `AZURE_OPENAI_ENDPOINT` | Phase 3 chat only | None | Azure resource root, for example `https://your-resource.openai.azure.com/`. |
| `AZURE_OPENAI_API_KEY` | Phase 3 chat only | None | Azure OpenAI API key for the configured resource. |
| `AZURE_OPENAI_API_VERSION` | No | `2024-12-01-preview` | API version passed to `AzureOpenAI(...)`. |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | Phase 3 chat only | None | Deployment name passed as `model=...`, for example `gpt-5-nano`. |
| `AZURE_OPENAI_TIMEOUT_SECONDS` | No | `30.0` | Per-request timeout for chat completions. |
| `MANAGER_BASE_URL` | Phase 4 retrieval only | None | Manager service root, for example `http://localhost:8000`. |
| `MANAGER_REQUEST_TIMEOUT_SECONDS` | No | `10.0` | Per-request timeout for manager retrieval. |
| `INTELLIGENCE_BASE_URL` | Phase 4 retrieval only | None | Intelligence service root, for example `http://localhost:8002`. |
| `INTELLIGENCE_REQUEST_TIMEOUT_SECONDS` | No | `10.0` | Per-request timeout for intelligence retrieval. |
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
