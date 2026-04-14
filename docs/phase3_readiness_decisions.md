# Phase 3 Readiness Decisions

This note records the last non-runtime decisions taken before Phase 3 starts.
It is intentionally practical and phase-bounded.

## DB Execution Model

Decision:
Keep synchronous SQLAlchemy database access for Phase 3.

Why:
The current service is fully sync, the session slice is stable, and Phase 3's
first vertical slice is already a large step because it introduces the first
LLM-backed turn pipeline. Switching the database stack to async at the same
time would add migration risk without solving a proven bottleneck in the
current repo.

Accepted tradeoff:
Phase 3 may need careful seams around any async Azure/OpenAI usage so that async
network work does not force an immediate async ORM rewrite. This is acceptable
for the first turn slice because throughput is not the current constraint.

What this means for Phase 3:
- Keep the existing sync `database.py` model and request-scoped SQLAlchemy session.
- If an async connector is introduced, isolate it behind a connector/controller
  seam instead of letting async concerns leak across the app.
- Revisit async DB access only if the turn pipeline proves it necessary, not
  speculatively before the first vertical slice lands.

## Observability Posture

Current state:
The service currently has basic application logging and explicit JSON error
responses. It does not yet have structured logs, correlation IDs, request/turn
 tracing, or metrics endpoints.

What is intentionally missing:
- No correlation ID propagation
- No structured log schema
- No LLM/tool call telemetry
- No `/metrics` endpoint

What must be added in or after Phase 3:
- Introduce a request/correlation ID direction as Phase 3 grows the turn path,
  so one user request can be traced through route, controller, connector, and
  persistence logs.
- Keep the first addition lightweight: request-scoped correlation in logs is
  higher priority than a broad observability subsystem.
- Defer Prometheus-style `/metrics` to a later phase; it is not required to
  start the first conversational slice honestly.

Direction:
Phase 3 should add correlation-aware logging at the seams it introduces, but it
should not block the first vertical slice on a full observability platform.
