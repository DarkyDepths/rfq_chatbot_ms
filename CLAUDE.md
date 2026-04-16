# rfq_chatbot_ms Working Notes (Phase 5 Mode A)

## Canonical References

- `docs/Phase 5 Mode A Implementation Pack v1.0.md` (behavior source of truth)
- `docs/Phase 5 Mode A — Implementation Blueprint v1.0.md` (execution/source-of-change plan)

## Phase 5 Behaviors (Frozen)

1. Proactive stage resolution at turn start for RFQ-bound sessions.
2. Two-persona declarative role framing.
3. Deterministic subtractive tool gating via stage x role allow-list intersection.
4. Closed-list speakable absence via `get_capability_status`.
5. Structured confidence marker for pattern-based answers.
6. Single-fetch intra-turn reuse of `ManagerRfqDetail`.
7. `PromptEnvelope` public shape frozen; internal composition can be restructured.
8. Mode B is hard-frozen in Phase 5 (no code change).
9. Observability via structured logs only (no DTO expansion).

## What Not To Do In rfq_chatbot_ms

- Do not change public API contracts/DTO shapes in Phase 5.
- Do not implement or expand Mode B behavior in Phase 5.
- Do not add new portfolio/disambiguation/intent-classifier scope (Phase 6+).
- Do not introduce LLM-native function-calling or streaming behavior.
- Do not bypass stage/role gating with ad-hoc runtime logic.
- Do not add silent capability failure messaging; use explicit capability-status phrasing.

## Scope Reminder

Phase 5 is behavior enrichment of the existing turn pipeline, not a contract rewrite or platform-wide architecture expansion.
