# rfq_chatbot_ms Working Notes (Phase 6)

## Canonical References

- `docs/Phase 6 Implementation Pack v1.0.md` (behavior source of truth)
- `docs/Phase 6 Implementation Blueprint v1.0.md` (execution/source-of-change plan)

For any behavioral or scope dispute, the Phase 6 Pack and Blueprint above are canonical.

## Phase 6 Behaviors

Milestone M6.1 - Intent + Boundary Router:
1. Deterministic five-intent classification and precedence.
2. Route-by-intent turn dispatch in ChatController.
3. Unsupported intent dispatch to capability-status path.

Milestone M6.2 - Grounding Guardrail:
1. Grounding required for rfq_specific turns.
2. Grounding-gap absence injection when evidence is missing.
3. Grounding mismatch handling when no retrieval tool matches.

Milestone M6.3 - Disambiguation:
1. Portfolio ambiguity triggers clarification prompts.
2. Request-scoped RFQ resolution for follow-up selector turns.
3. Clean abandonment back to conversational or general-knowledge routes.

Milestone M6.4 - Verification + Close-out:
1. Full pytest integration scenario coverage (14 beats).
2. Full Postman demo beat coverage (14 beats).
3. Contract stability checks and observability field checks.

## What Not To Do In rfq_chatbot_ms

- Do not change public API contracts/DTO shapes.
- Do not add new endpoints, response shapes, or Phase 6-specific error codes.
- Do not implement LLM-based intent classification.
- Do not add semantic hallucination detection (LLM-as-judge).
- Do not enforce hard output guardrail rejection/replacement behavior.
- Do not add portfolio analytics tools, RFQ listing, or cross-RFQ aggregation.
- Do not introduce implicit session binding from disambiguation resolution.
- Do not introduce LLM-native function-calling or streaming behavior.
- Do not bypass stage/role gating with ad-hoc runtime logic.
- Do not add silent capability failure messaging; use explicit capability-status phrasing.

## Scope Reminder

Phase 6 is behavior enrichment of the existing turn pipeline, not a contract rewrite or platform-wide architecture expansion.
Phase 7+ remains out of scope for this branch.
