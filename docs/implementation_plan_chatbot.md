# rfq_chatbot_ms — Implementation Plan v1

> **Document type:** Execution-ready implementation roadmap + learning guide
> **Source of truth:** `rfq_chatbot_ms_architecture_brief_v2_F.html` (frozen)
> **Pattern reference:** `rfq_manager_ms` BACAB layering, `rfq_intelligence_ms` blueprint style
> **Status:** Planning — no code generation
> **Date:** 2026-04-14

---

## 1. Executive Framing

### 1.1 What this plan is for

This document sequences the implementation of `rfq_chatbot_ms` — the technical microservice that delivers the product surface called **RFQ Copilot** — into phases that can be followed step by step. Each phase produces a coherent, testable increment. You can stop after any phase and still have a working (if incomplete) service.

### 1.2 Why the implementation must be staged

`rfq_chatbot_ms` is architecturally different from `rfq_manager_ms` and `rfq_intelligence_ms`. Manager is CRUD + workflow. Intelligence is parse + assemble. The copilot is **orchestration over orchestration**: it calls manager for operational facts, intelligence for derived insight, Azure OpenAI for generation, and its own session state for conversational continuity. Every layer depends on the layer below it being correct.

Building all layers simultaneously is the fastest route to vibe coding. The brief has ~40 files in the frozen `src/` layout and 16 Priority-1 capabilities. Touching them all at once means nothing is testable in isolation and debugging becomes forensic archaeology.

**Staged implementation means:** contracts first → persistence second → one vertical slice end-to-end third → expand tools and connectors fourth → add intelligence (stage, role, confidence, grounding) fifth → evaluation and polish last.

### 1.3 What "done" means for Phase 1

Phase 1 is **done** when:

- All 16 Priority-1 capabilities from §12.1 of the brief are implemented and verified
- The four-beat defense demo script (§13) runs live against seeded data
- The golden-set evaluation suite runs green in CI
- Every claim in the brief has a corresponding implementation or an honest stub with a documented reason
- The service boots, connects to its own Postgres, calls manager and intelligence over HTTP, calls Azure OpenAI, and returns a grounded, role-aware, stage-aware, confidence-aware response through the BACAB layered stack

### 1.4 What is intentionally deferred

| Item | Why deferred | Brief ref |
|------|-------------|-----------|
| `services/` folder | Orchestration simple enough for controllers in Phase 1 | §10.3, D13 |
| Semantic + procedural memory | Requires ≥50 real sessions, cold-start incompatible | §9.2, D4 |
| Native MCP servers | OAuth 2.1 enterprise auth not ready, C4 (can't touch manager) | §9.4, D3 |
| Document RAG (`search_mr_documents`) | Exception path, Priority 2 | §9.3, §12.1 P2-18 |
| What-if sandbox (`run_sandbox_scenario`) | Priority 2 stretch, not in core demo script | §9.4, D18 |
| Third role (`junior_engineer`) | Priority 2 stretch, mandatory pair sufficient | §7, §12.1 P2-17 |
| Multi-agent / A2A | Explicitly rejected for Phase 1 | §1, D1 |
| Proactive event subscription | Priority 2 | §12.1 P2-21 |
| LLM-as-judge evaluator | Priority 2, enriches golden set methodology | §12.1 P2-20 |

---

## 2. Planning Principles

These are not aspirational. They are decision filters applied at every phase boundary.

| # | Principle | What it prevents |
|---|-----------|-----------------|
| P1 | **Learn before build** | Coding without understanding the brief's reasoning; skipping the "why" |
| P2 | **Vertical slice before broad expansion** | 15 stub files with no working end-to-end path |
| P3 | **No layer skipping** | Controllers calling connectors directly; routes doing business logic |
| P4 | **No premature abstractions** | Generic "base tool" classes before a single tool works |
| P5 | **Deterministic-first where possible** | Using LLM calls where a dict lookup suffices |
| P6 | **Brief-driven implementation, not improvisation** | Inventing features the brief doesn't specify |
| P7 | **Contracts before behavior** | Implementing tool execution before the tool schema exists |
| P8 | **One exit criterion per phase** | Moving to the next phase without verifying the current one |
| P9 | **Honest stubs over fake implementations** | `return {"status": "ok"}` pretending to be a real connector |
| P10 | **Manager-native stage truth** | Inventing lifecycle enums that don't exist in manager's schema |

---

## 3. Phase Map — Overview

```
Phase 0  ──▶  Phase 1  ──▶  Phase 2  ──▶  Phase 3  ──▶  Phase 4  ──▶  Phase 5  ──▶  Phase 6  ──▶  Phase 7
Skeleton     Contracts &    Two-mode      First          Connectors    Stage/Role/   Grounding &   Evaluation
baseline     persistence    session       vertical       & typed       confidence    guardrails    & polish
             foundations    model         slice          retrieval     behavior
```

| Phase | Goal | Key outcome |
|-------|------|------------|
| **0** | Accepted skeleton / bootstrap baseline | App boots, health route up, DB connects, smoke test green |
| **1** | Contracts and persistence foundations | All Pydantic models, DB tables, Alembic migrations, typed contracts |
| **2** | Two-mode session model | Session creation (RFQ-bound / portfolio), session state machine, mode pivot logic |
| **3** | First conversational vertical slice | One turn end-to-end: route → controller → Azure OpenAI → response, with hardcoded context |
| **4** | Manager/intelligence connectors and typed retrieval | Real HTTP connectors, tool envelope, ≥2 working tools with real backend calls |
| **5** | Stage-aware, role-aware, and confidence-aware behavior | Pillar 1 + Pillar 3 + Pillar 4 integrated into the turn pipeline |
| **6** | Grounding, guardrails, and knowledge boundary | Pillar 2 grounding guardrail, input/output guardrails, intent classification with knowledge-boundary routing |
| **7** | Evaluation, golden set, and defense polish | Golden-set harness, CI integration, demo script walkthrough, correlation logging |

---

## 4. Phase Details

---

### Phase 0 — Accepted Skeleton / Bootstrap Baseline

**Phase goal:** Confirm the existing skeleton boots, connects to its Postgres database, and responds on health and smoke routes. This is the foundation everything else builds on.

**Why this phase comes now:** You cannot build anything if the skeleton itself is broken. This is already done per your description, but the plan starts by re-verifying it as a clean baseline.

#### Understand

- How `create_app()` in `app.py` assembles the FastAPI instance
- How `database.py` creates the SQLAlchemy engine, `SessionLocal`, and `Base`
- How `app_context.py` currently exposes `get_smoke_payload()` (minimal DI seed)
- How `conftest.py` sets up an in-memory SQLite for tests
- How the manager's `app_context.py` wires datasources → controllers via `Depends()` (this is the DI pattern you'll replicate)

#### Build

Nothing new. Verify what exists.

#### Verify

- [ ] `uvicorn src.app:app --host 0.0.0.0 --port 8003` starts without errors
- [ ] `GET /health` returns `{"status": "healthy"}`
- [ ] `GET /rfq-chatbot/v1/smoke` returns the phase-0 payload
- [ ] `pytest tests/` all green
- [ ] Postgres connection works with the real `DATABASE_URL`

#### What must remain stubbed

Everything beyond bootstrap. All BACAB folders (`controllers/`, `connectors/`, `datasources/`, `models/`, `translators/`, `tools/`) contain only `__init__.py`.

#### Exit criteria

Clean boot, all tests green, database connection verified.

#### Common mistakes

- Skipping this phase and assuming the skeleton works. Verify explicitly.
- Changing `database.py` or `settings.py` prematurely before understanding the manager pattern.

---

### Phase 1 — Contracts and Persistence Foundations

**Phase goal:** Define every Pydantic model, every SQLAlchemy ORM model, and the Alembic migration that creates the database tables. The result: the entire typed contract surface exists, but nothing reads or writes to the database yet besides the migration.

**Why this phase comes now:** You cannot build tools, controllers, or datasources until the data shapes exist. The ToolResultEnvelope, the Session model, the Conversation/Message models, the PromptEnvelope — all of these are referenced by every layer above. Building them first means every later phase types against real contracts, not ad-hoc dicts.

#### Understand

- § 9.2 of the brief: Session state, `chatbot_conversations` table schema
- § 6 (Pillar 2): `ToolResultEnvelope`, `SourceRef`, `ConfidenceLevel`
- § 10.2: the frozen `models/` layout — `turn.py`, `conversation.py`, `envelope.py`, `session.py`, `prompt.py`
- § 4: Session mode enum — `rfq_bound`, `portfolio`, `pending_pivot`
- How `rfq_manager_ms` models are structured (SQLAlchemy ORM + Pydantic DTOs)

#### Build

| File | What to create | Notes |
|------|---------------|-------|
| `models/envelope.py` | `ToolResultEnvelope`, `SourceRef`, `ConfidenceLevel` (Pydantic) | Frozen contract from §6.  `ConfidenceLevel` is a `str` enum: `deterministic`, `pattern_1_sample`, `absent` |
| `models/session.py` | `SessionMode` enum, `Session` ORM model, `SessionCreate`/`SessionRead` Pydantic DTOs, `RoleContext` | Mode ∈ {`rfq_bound`, `portfolio`, `pending_pivot`}. Columns: `id`, `user_id`, `rfq_id` (nullable), `mode`, `role`, `created_at`, `updated_at` |
| `models/conversation.py` | `Conversation` ORM model, `Message` ORM model, `ToolCallRecord` | Schema from §9.2: `{conversation_id, rfq_id, user_id, turn_number, role, content, timestamp, tool_calls, source_refs}` |
| `models/turn.py` | `TurnRequest`, `TurnResponse` (Pydantic) | Input/output DTOs for the turn endpoint |
| `models/prompt.py` | `PromptEnvelope` (Pydantic) | `stable_prefix`, `variable_suffix`, `total_budget` |
| `config/settings.py` | Extend with Azure OpenAI creds, manager/intelligence URLs, IAM config, feature flags | Add `AZURE_OPENAI_*`, `MANAGER_BASE_URL`, `INTELLIGENCE_BASE_URL`, `IAM_SERVICE_URL`, `AUTH_BYPASS_*` |
| `alembic.ini` + `migrations/` | Alembic init + first migration creating `chatbot_sessions` and `chatbot_conversations` tables | Follow manager pattern |

#### Verify

- [ ] `alembic upgrade head` creates both tables with correct columns and constraints
- [ ] All Pydantic models instantiate with valid sample data
- [ ] `ConfidenceLevel` enum rejects invalid values
- [ ] `SessionMode` enum covers exactly three states
- [ ] `ToolResultEnvelope` validates `source_ref` is required when `confidence != "absent"`
- [ ] Unit tests for model validation (pass/fail cases)

#### What must remain stubbed

- No routes beyond health/smoke
- No controllers, connectors, datasources, tools, translators
- No Azure OpenAI calls

#### Exit criteria

All models importable. Migration runs clean. Pydantic validation tests green.

#### Common mistakes

- Making `ToolResultEnvelope.value` too specific too early (keep it as `Any` per the brief)
- Inventing columns the brief doesn't mention
- Skipping `RoleContext` — it's needed by Pillar 3 later
- Not including `rfq_id` as nullable on sessions (required for portfolio mode)

#### Concepts to learn first

- Pydantic v2 model validators, `model_config`, discriminated unions
- SQLAlchemy 2.0 ORM style (mapped_column, relationship)
- Alembic autogenerate workflow
- The difference between ORM models (database persistence) and Pydantic DTOs (API/internal contracts)

---

### Phase 2 — Two-Mode Session Model

**Phase goal:** Implement session creation (both modes), session state persistence, and the mode-pivot state machine. The result: you can create an RFQ-bound session (Mode A) and a portfolio session (Mode B), retrieve session state, and pivot from portfolio to rfq_bound.

**Why this phase comes now:** The two-mode design (§4) is the organizational backbone of every later feature. Stage-aware behavior requires knowing `session.mode == rfq_bound`. Tool surface selection requires knowing the mode. Context building requires knowing the mode. Without the session model, nothing else has a place to live.

#### Understand

- § 4 of the brief: entry context, binding, pivot rules
- § 4.2: pivot is one-way (portfolio → rfq_bound only), immutable once set
- § 4.4: what differs between modes (session binding, default context, tool surface, allowed intents, stage-aware gating)
- Manager's `app_context.py` DI pattern: how `Depends()` wires datasources → controllers

#### Build

| File | What to create | Notes |
|------|---------------|-------|
| `datasources/session_datasource.py` | `SessionDatasource` — CRUD on `chatbot_sessions` table | `create()`, `get_by_id()`, `update_mode()`, `bind_rfq()` |
| `controllers/mode_controller.py` | `ModeController` — resolve mode, validate pivot, enforce one-way rule | Pure logic: check current mode, validate transition, reject invalid |
| `routes/session_routes.py` | `POST /sessions`, `GET /sessions/{id}` | Accept `mode: rfq | global` + optional `rfq_id`. Return session state |
| `translators/chat_translator.py` | Stub — API shape ↔ internal shape (start with passthrough) | Minimal for now, expanded in Phase 3 |
| `app_context.py` | Upgrade from smoke placeholder to real DI wiring | Wire `SessionDatasource` → `ModeController`, expose `Depends()` providers following manager pattern |

#### Verify

- [ ] `POST /rfq-chatbot/v1/sessions` with `{"mode": "rfq", "rfq_id": "IF-25144", "user_id": "u1"}` → creates rfq_bound session
- [ ] `POST /rfq-chatbot/v1/sessions` with `{"mode": "global", "user_id": "u1"}` → creates portfolio session (rfq_id is null)
- [ ] `GET /rfq-chatbot/v1/sessions/{id}` returns correct session state
- [ ] Pivot from `portfolio` → `rfq_bound` works and sets `rfq_id`
- [ ] Pivot from `rfq_bound` → anything is rejected (one-way rule)
- [ ] Integration test: create session → read session → verify persistence
- [ ] Unit test: `ModeController.validate_pivot()` edge cases

#### What must remain stubbed

- No conversation/turn logic yet
- No connectors (no HTTP calls to manager or intelligence)
- No Azure OpenAI
- No tools, no stage/role/confidence behavior

#### Exit criteria

Session CRUD works end-to-end through the BACAB stack. Mode pivot enforced. DI wiring follows the manager pattern.

#### Common mistakes

- Putting business logic in the route (mode validation belongs in `ModeController`)
- Making `rfq_id` required on all sessions (it's nullable for portfolio mode)
- Forgetting `pending_pivot` state (used during disambiguation flows later)
- Not following the manager DI pattern → leads to untestable code

---

### Phase 3 — First Conversational Vertical Slice

**Phase goal:** Send one user message and get one response back, end-to-end through the full BACAB stack. This is the first time Azure OpenAI is called. The context is hardcoded (no connector calls yet), but the entire turn pipeline exists: route → chat_controller → context_builder → Azure OpenAI → response → persist to conversation table.

**Why this phase comes now:** This is the **proof-of-life** for the copilot. Before you add connectors, tools, stage-awareness, or guardrails, you need the bare-bones turn pipeline working. Every later phase enriches this pipeline; none replaces it.

#### Understand

- § 10.4: the full flow of a single conversational turn (the long code flow diagram)
- § 9.1: ContextBuilder — stable prefix first, variable suffix last
- § 9.4: MCP-shaped function calling (the tool interface pattern)
- Azure OpenAI chat completions API with function calling and structured outputs
- The three Azure OpenAI calls per turn: intent classification → main generation with tools → final narration

#### Build

| File | What to create | Notes |
|------|---------------|-------|
| `connectors/azure_openai_connector.py` | `AzureOpenAIConnector` — chat completions, structured outputs | Thin wrapper around `openai` SDK. Accepts messages list + tool definitions. Returns completion |
| `controllers/chat_controller.py` | `ChatController.handle_turn()` — orchestrates one full turn | The central orchestrator. Phase 3 version: skip stage/role/confidence/grounding, just do: build context → call LLM → persist → return |
| `controllers/context_builder.py` | `ContextBuilder.build()` — assemble PromptEnvelope | Phase 3 version: hardcoded system prompt, no stage/role framing yet, hardcoded tool list (empty), last N messages from history |
| `controllers/conversation_controller.py` | `ConversationController` — read/write turns to episodic memory | Load last N turns, persist new turn (user + assistant) |
| `datasources/conversation_datasource.py` | `ConversationDatasource` — CRUD on `chatbot_conversations` | `create_message()`, `get_messages_by_conversation()`, `get_last_n_turns()` |
| `routes/chat_routes.py` | `POST /conversations/{id}/turn`, `GET /conversations/{id}` | Accept `TurnRequest`, return `TurnResponse` |
| `app_context.py` | Extend wiring for conversation + chat controllers | Add `AzureOpenAIConnector`, `ConversationDatasource`, `ConversationController`, `ChatController` |

#### Verify

- [ ] Create a session → send a turn → receive a coherent LLM response
- [ ] The response is persisted in `chatbot_conversations`
- [ ] `GET /conversations/{id}` returns the conversation history
- [ ] A second turn in the same conversation receives context from the first turn
- [ ] The system prompt is in the stable-prefix position (first in the messages list)
- [ ] Azure OpenAI connector handles errors gracefully (timeout, 429, 500)
- [ ] Integration test: full turn round-trip
- [ ] Unit test: `ContextBuilder.build()` returns correct PromptEnvelope shape

#### What must remain stubbed

- No real connectors to manager or intelligence (no tool calls resolve to real APIs)
- No intent classification (every turn goes straight to generation)
- No stage/role/confidence/grounding guardrails
- No tool execution (tools list is empty — the LLM just generates text)
- Context is a hardcoded system prompt, not the full ContextBuilder with stage/role framing

#### Exit criteria

A human can chat with the copilot. The conversation is persisted. The LLM response arrives through the BACAB stack. The PromptEnvelope structure is visible in logs.

#### Common mistakes

- Calling Azure OpenAI from the route (it must go through `ChatController`)
- Building a complex prompt before the pipeline is proven
- Skipping conversation persistence ("I'll add it later")
- Not handling Azure OpenAI rate limits / errors (the first thing that will break in practice)
- Over-engineering `ContextBuilder` with all framing slots before a single turn works

---

### Phase 4 — Connectors, Tools, and Typed Retrieval

**Phase goal:** Connect to `rfq_manager_ms` and `rfq_intelligence_ms` over HTTP. Build the first working tools (`get_rfq_snapshot`, `get_rfq_profile`, `get_rfq_stage`). The LLM can now call tools that return real data wrapped in `ToolResultEnvelope`.

**Why this phase comes now:** Tools are the copilot's hands. Without them, the LLM generates from training data only — no grounding, no source refs, no factual accuracy. But tools require connectors to external services, and connectors require typed contracts to validate responses. Phase 1 and 2 established the contracts; Phase 3 proved the turn pipeline; now we connect the pipeline to real data.

#### Understand

- § 9.4: Tool interface — MCP-shaped, not MCP-native. Tool naming, schema structure
- § 9.3: Retrieval paths — intelligence snapshot first, manager portfolio second, documents are exception
- § 6 (Pillar 2): ToolResultEnvelope — every tool returns this shape
- Manager's `connectors/iam_service.py` and `connectors/event_bus.py` for the HTTP connector pattern
- Intelligence's consumer-facing endpoints: `/snapshot`, `/briefing`, `/workbook-review`, `/workbook-profile`
- Manager's endpoints: `/rfqs/{id}`, `/rfqs/{id}/stages`, `/rfqs/stats`, `/rfqs/analytics`, `/rfqs`

#### Build

| File | What to create | Notes |
|------|---------------|-------|
| `connectors/manager_connector.py` | `ManagerConnector` — HTTP client for manager | Methods: `get_rfq(rfq_id)`, `get_rfq_stages(rfq_id)`, `list_rfqs(filters)`, `get_stats()`, `get_analytics(params)` |
| `connectors/intelligence_connector.py` | `IntelligenceConnector` — HTTP client for intelligence | Methods: `get_snapshot(rfq_id)`, `get_briefing(rfq_id)`, `get_workbook_review(rfq_id)`, `get_workbook_profile(rfq_id)` |
| `connectors/iam_connector.py` | `IAMConnector` — IAM seam stub | Phase 4: auth-bypass mode returning hardcoded role from settings. Same pattern as manager |
| `tools/common/envelope.py` | Shared `ToolResultEnvelope` Pydantic base | Re-exports from `models/envelope.py` + helper constructors |
| `tools/common/decorators.py` | `@tool` decorator for Azure OpenAI function registration | Generates JSON schema from Pydantic model, registers tool definition |
| `tools/get_rfq_snapshot.py` | First RFQ-scoped tool | Calls `intelligence_connector.get_snapshot()`, wraps in `ToolResultEnvelope` |
| `tools/get_rfq_profile.py` | Manager-backed tool | Calls `manager_connector.get_rfq()`, wraps in envelope |
| `tools/get_rfq_stage.py` | Stage truth tool (Pillar 1 foundation) | Calls `manager_connector.get_rfq_stages()`, wraps in envelope |
| `controllers/tool_controller.py` | `ToolController` — tool selection, invocation, result handling | Registers tools, matches Azure OpenAI function_call to tool, executes, returns envelope |
| `translators/envelope_translator.py` | Translate `ToolResultEnvelope` → LLM-consumable dict | Formats envelope for inclusion in the LLM's tool return message |
| `controllers/chat_controller.py` | **Extend:** integrate `ToolController` into turn pipeline | After intent (stub for now), pass tools to Azure OpenAI, handle function_call, execute tool, send result back |
| `controllers/context_builder.py` | **Extend:** inject tool definitions into the stable prefix | Read registered tools from `ToolController`, format as function definitions for Azure OpenAI |

#### Verify

- [ ] `get_rfq_snapshot` returns real data from intelligence (requires intelligence service running)
- [ ] `get_rfq_stage` returns real stage data from manager (requires manager service running)
- [ ] The LLM calls a tool when a factual question is asked (e.g., "what's the grand total?")
- [ ] Tool result is wrapped in `ToolResultEnvelope` with valid `source_ref` and `confidence`
- [ ] The LLM renders the tool result in its response
- [ ] Mocked connector tests (unit): tools work with fixture data
- [ ] Integration test: turn with tool call → tool execution → tool result → LLM narration

#### What must remain stubbed

- Intent classification (all turns treated as `rfq_factual`)
- Stage-aware tool filtering (all tools exposed regardless of stage)
- Role-aware framing (no role injection into prompt)
- Grounding/confidence guardrails (output is not post-processed)
- Portfolio tools (`list_rfqs`, `get_rfq_stats`, `get_rfq_analytics`, `resolve_rfq_by_name`)
- `get_capability_status` tool
- Disambiguation controller

#### Exit criteria

Ask "what's the grand total for IF-25144?" → the LLM calls `get_rfq_snapshot` or `get_workbook_review` → receives real data → renders the answer with the raw source_ref data. The tool envelope is visible in logs.

#### Common mistakes

- Building all 12 tools at once. Start with 3 (snapshot, profile, stage). Add the rest incrementally.
- Hardcoding connector URLs instead of reading from `settings.py`
- Not mocking connectors in unit tests (tests should not require live manager/intelligence)
- Putting tool execution logic in the route
- Inventing tool return shapes that don't match the `ToolResultEnvelope` contract

---

### Phase 5 — Stage-Aware, Role-Aware, and Confidence-Aware Behavior

**Phase goal:** Integrate the three behavioral pillars into the turn pipeline. The copilot now adapts its tools, prompt framing, and output rendering based on (a) the RFQ's current stage, (b) the user's role, and (c) the confidence level of tool results. This is where the copilot becomes the copilot described in the brief.

**Why this phase comes now:** The vertical slice from Phase 3–4 proved the pipeline works and tools return real data. Now we add the intelligence that makes the copilot's behavior contextual. These three pillars are what differentiate the copilot from "a chat window with tools stapled on." They require working tools (Phase 4) and session state (Phase 2) to function.

#### Understand

- § 5 (Pillar 1): Stage-aware — how `stage_controller.py` reads `rfq_stage` from manager, looks up `stage_config.py`, filters tools and allowed intents, injects stage framing
- § 7 (Pillar 3): Role-aware — how `role_controller.py` resolves role from IAM seam, looks up `role_config.py`, injects role framing, filters tool results by role
- § 8 (Pillar 4): Confidence-aware — how `confidence_controller.py` reads `confidence` from tool envelopes, conditions LLM rendering, ensures qualifiers are present
- § 10.4: Where each controller sits in the turn flow (stage → intent → context → tools → confidence → role)

#### Build

| File | What to create | Notes |
|------|---------------|-------|
| `config/stage_config.py` | Static dict: `stage_template_id` → `{allowed_intents, relevant_tools, stage_framing}` | Cover 3–5 stage templates from the demo RFQ's workflow. Keyed on real manager `stage_template` identifiers |
| `config/role_config.py` | Static dict: role → `{allowed_topics, forbidden_topics, framing_style, redaction_rules, system_prompt_text}` | Two mandatory roles: `estimation_dept_lead`, `executive` |
| `config/mode_config.py` | Mode → tool surface mapping | RFQ-bound → RFQ-scoped tools. Portfolio → portfolio tools. Post-pivot → both |
| `controllers/stage_controller.py` | `StageController` — fetch stage from manager, look up config, return stage context | Calls `get_rfq_stage` tool/connector, matches `stage_template_id` to `stage_config` entry |
| `controllers/role_controller.py` | `RoleController` — resolve role, inject framing, output filter | Resolve via `iam_connector`, look up `role_config`, generate role framing text, apply output redaction |
| `controllers/confidence_controller.py` | `ConfidenceController` — check confidence qualifiers in LLM output | Read confidence from tool envelopes, verify LLM used appropriate qualifiers in response text |
| `controllers/context_builder.py` | **Extend:** inject `role_framing` and `stage_framing` into stable prefix | `_role_framing(role)` and `_stage_framing(stage)` methods. Conditional `_rfq_profile` vs `_portfolio_context` |
| `controllers/tool_controller.py` | **Extend:** filter exposed tools by stage config | Only pass stage-relevant tools to Azure OpenAI |
| `controllers/chat_controller.py` | **Extend:** wire stage → role → confidence into the turn pipeline | Add `StageController`, `RoleController`, `ConfidenceController` calls at the right points in the flow |
| `tools/get_capability_status.py` | The "speakable absence" tool | Local tool — returns structured explanation of why a capability is absent + what would be needed |

#### Verify

- [ ] Same question at different stages → different tool surfaces exposed to the LLM
- [ ] Stage framing appears in the system prompt for RFQ-bound sessions
- [ ] Same question, two roles → different response content (estimation_dept_lead gets raw margin, executive gets bid-strategy framing)
- [ ] Role framing appears in the system prompt
- [ ] Deterministic tool result → LLM states value plainly without hedging
- [ ] Pattern-based tool result → LLM includes "(validated against 1 sample)" qualifier
- [ ] Absent capability → LLM names the gap + future condition (via `get_capability_status`)
- [ ] Unit tests: `StageController` with mocked manager response
- [ ] Unit tests: `RoleController` with fixture role configs
- [ ] Unit tests: `ConfidenceController` with each confidence state
- [ ] Integration tests: the three-case demo narrative from §8 (beats 1, 2, 3)

#### What must remain stubbed

- Grounding guardrail (source_ref enforcement with retry) — Phase 6
- Input guardrails (PII, injection, intent classification routing) — Phase 6
- Output guardrails (grounding check, role check as enforcement, not just injection) — Phase 6
- Disambiguation controller — Phase 6
- Portfolio tools (`list_rfqs`, `get_rfq_stats`, `get_rfq_analytics`, `resolve_rfq_by_name`) — Phase 6
- History compression in ContextBuilder — Phase 6

#### Exit criteria

The four-beat demo narrative partially works: beats 1–3 (grounding + confidence states A/B/C) are demonstrable. Beat 4 (role contrast) is demonstrable with two different session configurations. The copilot is no longer just a chat window.

#### Common mistakes

- Inventing stage template IDs instead of reading them from the actual manager seed data
- Hardcoding role in the session instead of resolving from IAM seam (even if IAM is in bypass mode)
- Making confidence enforcement client-side (it belongs in `ConfidenceController`)
- Skipping `get_capability_status` — it's the mechanism that makes Pillar 4 state C work

---

### Phase 6 — Grounding, Guardrails, Knowledge Boundary, and Portfolio Tools

**Phase goal:** Complete the guardrail stack (input, output, action), implement intent classification with knowledge-boundary routing, build the remaining portfolio tools for Mode B, and implement the disambiguation controller. This is the phase where the copilot becomes safe and honest, not just capable.

**Why this phase comes now:** Phases 3–5 built the capability path (tools, stage-awareness, role-awareness, confidence). Phase 6 builds the **safety path** — making sure the copilot doesn't hallucinate numbers without sources, doesn't leak forbidden content past role filters, doesn't run state-changing tools, and routes questions correctly between general-knowledge and tool-required paths. The guardrails sit on top of a working pipeline; they can't exist without it.

#### Understand

- § 6 (Pillar 2): Grounding guardrail — extract numerics, verify source_ref proximity, retry on failure, safe fallback
- § 9.6: Three guardrail layers — input, output, action
- § 9.7: Intent classification — first step of every turn, structured outputs, knowledge-boundary routing
- § 6: Knowledge boundary rule — general concept → LLM may explain; specific project decision → tools required
- § 9.5: Disambiguation — three-tier resolution pattern
- § 4.2: Global → RFQ-bound pivot

#### Build

| File | What to create | Notes |
|------|---------------|-------|
| `controllers/intent_controller.py` | `IntentController` — classify intent via Azure OpenAI structured output call | Returns `{intent: enum, confidence: float, rfq_id: str?, topic: str?}`. Intent categories: `rfq_factual`, `rfq_analytical`, `rfq_what_if`, `general_knowledge`, `portfolio`, `rfq_resolution`, `out_of_scope` |
| `controllers/grounding_controller.py` | `GroundingController` — post-process LLM output for source_ref enforcement | Extract numeric values (regex), check proximity to `[source_ref]` pattern, retry budget: 2 attempts, safe fallback |
| `controllers/guardrail_controller.py` | `GuardrailController` — input guardrails + action guardrails | Input: scope check, PII filter stub, injection heuristics. Action: reject all write-tool calls (Phase 1 = read-only) |
| `controllers/disambiguation_controller.py` | `DisambiguationController` — three-tier RFQ resolution | Low ambiguity → auto-pick. Medium → suggest + confirm. High → offer choices. Uses `resolve_rfq_by_name` tool |
| `tools/list_rfqs.py` | Portfolio tool | Calls `manager_connector.list_rfqs()`, wraps in envelope |
| `tools/get_rfq_stats.py` | Portfolio tool | Calls `manager_connector.get_stats()`, wraps in envelope |
| `tools/get_rfq_analytics.py` | Portfolio tool | Calls `manager_connector.get_analytics()`, wraps in envelope |
| `tools/resolve_rfq_by_name.py` | Disambiguation tool | Search + heuristics against manager's RFQ list |
| `tools/get_intelligence_briefing.py` | RFQ-scoped tool | `/briefing` endpoint |
| `tools/get_workbook_review.py` | RFQ-scoped tool | `/workbook-review` endpoint |
| `tools/get_workbook_profile.py` | RFQ-scoped tool | `/workbook-profile` endpoint |
| `translators/history_translator.py` | DB rows → compressed history block | Compress past-N turns into summary, keep last N verbatim |
| `utils/tokens.py` | Token counting + budget enforcement | `tiktoken` for token counting, budget checks in ContextBuilder |
| `utils/source_ref.py` | Source_ref rendering helpers | Pattern matching, proximity checking |
| `controllers/context_builder.py` | **Extend:** add `_compressed_history()`, `_portfolio_context()` | Full portfolio mode context assembly |
| `controllers/chat_controller.py` | **Extend:** wire intent → guardrails → grounding into turn pipeline | Intent classification as first step; grounding + role check as last steps before return |

#### Verify

- [ ] Intent classification: "what's the grand total?" → `rfq_factual` (tools required)
- [ ] Intent classification: "what is ASME Section VIII?" → `general_knowledge` (no tool call needed)
- [ ] Knowledge boundary: `general_knowledge` intent → LLM answers without tools, response labeled as general
- [ ] Knowledge boundary: `rfq_factual` intent → tools must be called before generation
- [ ] Grounding: response with numeric claim missing source_ref → guardrail rejects → retry → source added
- [ ] Grounding: after 2 failed retries → safe fallback message
- [ ] Role output filter: executive session → no raw cost breakdown in response
- [ ] Action guardrail: any attempt to invoke a write-tool → blocked + logged
- [ ] Disambiguation (low ambiguity): "show me IF-25144" → auto-pick + stated assumption
- [ ] Portfolio mode: "which RFQs are near deadline?" → `list_rfqs` or `get_rfq_analytics` called
- [ ] Global → RFQ-bound pivot: start in portfolio → ask about specific RFQ → session pivots
- [ ] History compression: conversation past N turns is summarized, not truncated
- [ ] Token budget: `ContextBuilder` enforces `total_budget` and logs when approaching limit
- [ ] Unit tests for each guardrail layer
- [ ] Integration tests for the full guardrailed turn pipeline

#### What must remain stubbed

- Document RAG (`search_mr_documents`) — Priority 2
- What-if sandbox (`run_sandbox_scenario`) — Priority 2
- LLM-as-judge evaluation — Priority 2
- Proactive event subscription — Priority 2
- Third role (`junior_engineer`) — Priority 2

#### Exit criteria

The entire Priority-1 guardrail stack is operational. The copilot classifies intents, enforces grounding, respects role boundaries, handles the knowledge-boundary rule, and disambiguates RFQs. All four demo beats from §13 are fully functional.

#### Common mistakes

- Building the grounding guardrail before tools return real source_refs (Phase 4 must be solid first)
- Over-engineering intent classification — start with a simple schema and a clear prompt, not a fine-tuned classifier
- Treating intent classification as optional ("the LLM will figure it out") — It won't reliably. The brief says it's "non-negotiable"
- Making disambiguation HITL instead of search-and-disambiguate (D17: HITL is for mutations, not understanding)

---

### Phase 7 — Evaluation, Golden Set, and Defense Polish

**Phase goal:** Build the golden-set evaluation suite, integrate it into CI, add correlation logging, verify the defense demo script end-to-end, and polish rough edges. The result: the service is defense-ready.

**Why this phase comes now:** You can't evaluate behavior that doesn't exist. The golden set verifies the claims made by Phases 1–6. Building it last (but not skipping it) means every case tests real behavior against real expectations. Building it first would mean writing expectations against unbuilt code.

#### Understand

- § 9.8: Golden-set structure — case schema, harness, coverage targets
- § 13: Defense demo script — the four beats
- § 9.7: Structured logging with correlation IDs
- Manager's logging/correlation patterns for reuse

#### Build

| File | What to create | Notes |
|------|---------------|-------|
| `golden_set/cases/*.json` | 20–30 hand-curated test cases | Cover: stage-appropriate (3–4 stages × 2), grounding (5), role-aware (2 roles × 2 topics), confidence (3 states × 2), intent boundary (4–5), disambiguation (2–3) |
| `golden_set/harness.py` | pytest runner | Load cases, create sessions, send turns, check intent, tool selection, source_refs, answer patterns |
| `golden_set/judges.py` | Assertion helpers | Regex matchers for source_refs, forbidden pattern checkers, confidence qualifier detectors |
| `utils/correlation.py` | Correlation ID propagation | Generate per-request correlation ID, attach to all LLM calls and tool calls, log with structured format |
| `utils/logging.py` | Structured logging setup | JSON structured logging, correlation ID in every log line |
| Various files | **Polish:** error handling, edge cases, timeout handling, retry logic | Clean up rough edges discovered during golden set runs |

#### Verify

- [ ] `pytest golden_set/ -v` runs all cases and reports pass/fail per case
- [ ] Coverage: at least 3 stage-appropriate cases, 5 grounding cases, 4 role-aware cases (2 roles × 2 topics), 6 confidence cases, 4 intent-boundary cases
- [ ] Correlation ID visible in every log line for a single turn
- [ ] Defense demo beats 1–4 all pass as golden-set cases
- [ ] CI pipeline runs golden-set on every commit (or every push to main)
- [ ] No golden-set case relies on LLM producing exact text — all checks are structural (intent, tool selection, source_ref presence, forbidden patterns)

#### What must remain stubbed

Nothing. This phase completes Priority 1.

#### Exit criteria

Golden set green. Demo script walkable. Correlation logging visible. CI integration working.

#### Common mistakes

- Making golden-set cases too brittle (checking exact LLM wording instead of structural properties)
- Skipping cases for uncomfortable failures (a case that reveals a real bug is more valuable than one that passes trivially)
- Not running the full demo script end-to-end before declaring done
- Forgetting correlation IDs (makes debugging in the defense impossible)

---

## 5. File-by-File Implementation Map

Based on the brief's frozen `src/` layout (§10.2). For each important file: what it does, which phase introduces it, minimal initial version, and what later phases extend.

### 5.1 Config Layer

| File | Responsibility | Introduced | Initial version | Later extensions |
|------|---------------|-----------|-----------------|-----------------|
| `config/settings.py` | Env vars, Azure creds, feature flags | Phase 0 (exists) | DB URL, CORS, basic app config | Phase 1: Azure OpenAI creds, service URLs, IAM config |
| `config/stage_config.py` | Stage template → copilot config dict | Phase 5 | 3–5 entries for demo RFQ stages | Expand as workflows grow |
| `config/role_config.py` | Role → copilot config dict | Phase 5 | 2 entries: `estimation_dept_lead`, `executive` | Phase 2+: `junior_engineer`, more roles |
| `config/mode_config.py` | Mode → tool surface mapping | Phase 5 | RFQ-scoped tools vs portfolio tools | Stable after initial definition |

### 5.2 Models Layer

| File | Responsibility | Introduced | Initial version | Later extensions |
|------|---------------|-----------|-----------------|-----------------|
| `models/envelope.py` | `ToolResultEnvelope`, `SourceRef`, `ConfidenceLevel` | Phase 1 | Pydantic models per brief §6 | Stable — frozen contract |
| `models/session.py` | `Session` ORM + `SessionMode` enum + DTOs | Phase 1 | ORM model + create/read DTOs | Stable after Phase 2 |
| `models/conversation.py` | `Conversation` + `Message` ORM models | Phase 1 | Schema from §9.2 | Stable after Phase 3 |
| `models/turn.py` | `TurnRequest`, `TurnResponse` DTOs | Phase 1 | Input/output shapes | Phase 6: add intent, tool_calls in response |
| `models/prompt.py` | `PromptEnvelope` DTO | Phase 1 | `stable_prefix`, `variable_suffix`, `total_budget` | Phase 6: add token tracking |

### 5.3 Routes Layer

| File | Responsibility | Introduced | Initial version | Later extensions |
|------|---------------|-----------|-----------------|-----------------|
| `routes/health_route.py` | Health + readiness | Phase 0 (exists) | `/health` | Phase 7: add `/ready`, `/metrics` |
| `routes/session_routes.py` | Session CRUD | Phase 2 | `POST /sessions`, `GET /sessions/{id}` | Stable |
| `routes/chat_routes.py` | Turn submission + conversation readback | Phase 3 | `POST /conversations/{id}/turn`, `GET /conversations/{id}` | Stable |

### 5.4 Controllers Layer

| File | Responsibility | Introduced | Initial version | Later extensions |
|------|---------------|-----------|-----------------|-----------------|
| `controllers/chat_controller.py` | Main turn orchestrator | Phase 3 | Minimal: context → LLM → persist | Phase 4–6: add tools, stage, role, confidence, guardrails |
| `controllers/context_builder.py` | Prompt assembly (§9.1) | Phase 3 | Hardcoded system prompt | Phase 5: stage/role framing. Phase 6: history compression, portfolio context, token budgets |
| `controllers/mode_controller.py` | Mode resolution + pivot | Phase 2 | Validate mode, enforce one-way pivot | Stable after Phase 2 |
| `controllers/stage_controller.py` | Pillar 1 — stage resolution | Phase 5 | Read stage from manager, look up config | Stable |
| `controllers/role_controller.py` | Pillar 3 — role resolution + output filter | Phase 5 | Resolve role, inject framing | Phase 6: output redaction enforcement |
| `controllers/confidence_controller.py` | Pillar 4 — confidence rendering | Phase 5 | Check qualifiers in output | Stable |
| `controllers/intent_controller.py` | Intent classification | Phase 6 | Structured output LLM call | Stable |
| `controllers/grounding_controller.py` | Pillar 2 — source_ref enforcement | Phase 6 | Regex extraction, proximity check, retry | Stable |
| `controllers/guardrail_controller.py` | Input + action guardrails | Phase 6 | Scope check, PII stub, injection heuristics, write-block | Stable |
| `controllers/disambiguation_controller.py` | Three-tier RFQ resolution | Phase 6 | Search + confidence scoring + tier determination | Stable |
| `controllers/conversation_controller.py` | Episodic memory read/write | Phase 3 | Load/persist turns | Phase 6: history compression |
| `controllers/tool_controller.py` | Tool registry + execution | Phase 4 | Register tools, execute by name | Phase 5: stage-aware filtering |

### 5.5 Connectors Layer

| File | Responsibility | Introduced | Initial version | Later extensions |
|------|---------------|-----------|-----------------|-----------------|
| `connectors/azure_openai_connector.py` | Azure OpenAI SDK wrapper | Phase 3 | Chat completions | Phase 6: structured outputs for intent classification |
| `connectors/manager_connector.py` | HTTP client for manager | Phase 4 | `get_rfq()`, `get_rfq_stages()` | Phase 6: `list_rfqs()`, `get_stats()`, `get_analytics()` |
| `connectors/intelligence_connector.py` | HTTP client for intelligence | Phase 4 | `get_snapshot()` | Phase 4–6: `get_briefing()`, `get_workbook_review()`, `get_workbook_profile()` |
| `connectors/iam_connector.py` | IAM seam | Phase 4 | Auth-bypass mode | Phase 2+: swap to `rfq_iam_ms` |

### 5.6 Datasources Layer

| File | Responsibility | Introduced | Initial version | Later extensions |
|------|---------------|-----------|-----------------|-----------------|
| `datasources/session_datasource.py` | Session table CRUD | Phase 2 | Create, read, update mode | Stable |
| `datasources/conversation_datasource.py` | Conversation/message CRUD | Phase 3 | Create message, read by conversation | Phase 6: history window queries |
| `datasources/document_index_datasource.py` | pgvector index | **Deferred** (P2) | Not built in Phase 1 | Priority 2: `search_mr_documents` |

### 5.7 Tools Layer

| File | Responsibility | Introduced |
|------|---------------|-----------|
| `tools/common/envelope.py` | Shared envelope constructors | Phase 4 |
| `tools/common/decorators.py` | `@tool` decorator | Phase 4 |
| `tools/get_rfq_snapshot.py` | Intelligence → snapshot | Phase 4 |
| `tools/get_rfq_profile.py` | Manager → RFQ record | Phase 4 |
| `tools/get_rfq_stage.py` | Manager → stages (Pillar 1) | Phase 4 |
| `tools/get_intelligence_briefing.py` | Intelligence → briefing | Phase 6 |
| `tools/get_workbook_review.py` | Intelligence → workbook review | Phase 6 |
| `tools/get_workbook_profile.py` | Intelligence → workbook profile | Phase 6 |
| `tools/list_rfqs.py` | Manager → RFQ list (portfolio) | Phase 6 |
| `tools/get_rfq_stats.py` | Manager → stats (portfolio) | Phase 6 |
| `tools/get_rfq_analytics.py` | Manager → analytics (portfolio) | Phase 6 |
| `tools/resolve_rfq_by_name.py` | Disambiguation | Phase 6 |
| `tools/get_capability_status.py` | Speakable absence (Pillar 4) | Phase 5 |
| `tools/search_mr_documents.py` | Document RAG (exception path) | **Deferred** (P2) |
| `tools/run_sandbox_scenario.py` | What-if sandbox | **Deferred** (P2) |

### 5.8 Translators Layer

| File | Responsibility | Introduced |
|------|---------------|-----------|
| `translators/chat_translator.py` | API shape ↔ internal shape | Phase 2 (stub), Phase 3 (functional) |
| `translators/envelope_translator.py` | Envelope → LLM-consumable dict | Phase 4 |
| `translators/history_translator.py` | DB rows → compressed history | Phase 6 |

### 5.9 Utils Layer

| File | Responsibility | Introduced |
|------|---------------|-----------|
| `utils/tokens.py` | Token counting, budget enforcement | Phase 6 |
| `utils/source_ref.py` | Source_ref rendering helpers | Phase 6 |
| `utils/correlation.py` | Correlation ID propagation | Phase 7 |
| `utils/logging.py` | Structured logging setup | Phase 7 |

---

## 6. API Contract Progression

The public API should be introduced incrementally, not all at once.

| Order | Endpoint | Phase | Why this order |
|-------|---------|-------|---------------|
| 1 | `GET /health` | 0 | Already exists. Proves the service is alive |
| 2 | `POST /rfq-chatbot/v1/sessions` | 2 | Creates a session (mode + optional rfq_id). Required before any conversation |
| 3 | `GET /rfq-chatbot/v1/sessions/{id}` | 2 | Read session state. Useful for debugging and UI integration |
| 4 | `POST /rfq-chatbot/v1/conversations/{id}/turn` | 3 | The core endpoint. Sends a user message, receives a copilot response |
| 5 | `GET /rfq-chatbot/v1/conversations/{id}` | 3 | Read back conversation history. Needed for UI pagination and debugging |
| 6 | `GET /ready` | 7 | Readiness probe: checks DB + Azure OpenAI connectivity. Added during polish |

> [!IMPORTANT]
> The session creation endpoint **must** precede the turn endpoint. A turn requires a session (for mode, rfq_id binding, role context). Without sessions, turns have nowhere to live.

---

## 7. Persistence Progression

### 7.1 Table introduction order

| Order | Table | Phase | Columns (initial) | Notes |
|-------|-------|-------|-------------------|-------|
| 1 | `chatbot_sessions` | 1 (schema), 2 (CRUD) | `id`, `user_id`, `rfq_id` (nullable), `mode`, `role`, `created_at`, `updated_at` | Mode is the backbone; rfq_id nullable for portfolio |
| 2 | `chatbot_conversations` | 1 (schema), 3 (CRUD) | `id`, `session_id`, `created_at` | Thin — just groups messages |
| 3 | `chatbot_messages` | 1 (schema), 3 (CRUD) | `id`, `conversation_id`, `turn_number`, `role` (user/assistant/tool), `content`, `tool_calls` (JSONB), `source_refs` (JSONB), `timestamp` | Core episodic memory |

### 7.2 What to persist early vs. defer

| Persist from Phase 3 | Defer until needed |
|----------------------|-------------------|
| Every user message | History compression summaries (Phase 6) |
| Every assistant response | Token usage stats (Phase 7) |
| Tool calls per turn (as JSONB) | Document embeddings (Priority 2) |
| Source refs per turn (as JSONB) | Semantic memory (Phase 2+) |
| Session mode + rfq_id binding | Intent classification results (Phase 6 — store as JSONB on the message) |

### 7.3 What should remain in-memory/stubbed

- **Stage config:** static Python dict, not a database table. Changes only when workflows are reconfigured — treat as code, not data
- **Role config:** static Python dict. Roles are stable within a deployment
- **Tool registry:** in-memory dict populated at app startup
- **Prompt templates:** hardcoded strings or files, not DB records

---

## 8. Connector Progression

### 8.1 Azure OpenAI Connector

| When | What | Why |
|------|------|-----|
| **Phase 3** | Chat completions (basic) | First LLM call. Proves the pipeline works |
| **Phase 4** | Function calling (tools) | LLM needs to select and call tools |
| **Phase 6** | Structured outputs (intent classification) | Intent classifier returns a typed enum, not free-form text |

**First thin version:** Accept a messages list + optional tools list. Return the completion. Handle 429 (rate limit) with exponential backoff. Handle timeouts with a configurable deadline.

**Mocked before real:** In unit tests, mock the completion response to test the pipeline without Azure OpenAI. In integration tests, call the real API.

### 8.2 Manager Connector

| When | What | Backing endpoint | Why at this moment |
|------|------|-----------------|-------------------|
| **Phase 4** | `get_rfq(rfq_id)` | `GET /rfqs/{id}` | First RFQ profile read for Mode A default context |
| **Phase 4** | `get_rfq_stages(rfq_id)` | `GET /rfqs/{id}/stages` | Pillar 1 stage truth — must exist before `StageController` |
| **Phase 6** | `list_rfqs(filters)` | `GET /rfqs` | Portfolio Mode B — listing and filtering RFQs |
| **Phase 6** | `get_stats()` | `GET /rfqs/stats` | Portfolio Mode B — aggregate counts |
| **Phase 6** | `get_analytics(params)` | `GET /rfqs/analytics` | Portfolio Mode B — trends, deadlines |

**First thin version:** `httpx.AsyncClient` with configurable base URL from settings. Timeout handling. Return raw JSON, let the tool layer wrap it in `ToolResultEnvelope`.

**Mocked before real:** Fixture data matching manager's actual response shapes (copy from manager's test fixtures or API docs).

### 8.3 Intelligence Connector

| When | What | Backing endpoint | Why at this moment |
|------|------|-----------------|-------------------|
| **Phase 4** | `get_snapshot(rfq_id)` | `GET /intelligence/v1/rfqs/{id}/snapshot` | Default context for RFQ-bound conversations |
| **Phase 6** | `get_briefing(rfq_id)` | `GET /intelligence/v1/rfqs/{id}/briefing` | Intelligence dossier for deeper questions |
| **Phase 6** | `get_workbook_review(rfq_id)` | `GET /intelligence/v1/rfqs/{id}/workbook-review` | Completeness/discrepancy queries |
| **Phase 6** | `get_workbook_profile(rfq_id)` | `GET /intelligence/v1/rfqs/{id}/workbook-profile` | Drill-down past snapshot |

**First thin version:** Same `httpx.AsyncClient` pattern as manager connector. Same mock strategy.

**Mocked before real:** Fixture data matching intelligence's actual response shapes. Importantly: the fixture must include `confidence` and `validated_against` fields (since intelligence owns confidence classification — D8).

### 8.4 IAM Connector

| When | What | Why at this moment |
|------|------|-------------------|
| **Phase 4** | Auth-bypass stub | Local development. Returns role from settings (`AUTH_BYPASS_ROLE`, `AUTH_BYPASS_USER_ID`) |
| **Phase 5** | Used by `RoleController` to resolve role | Pillar 3 needs identity resolution |
| **Phase 2+** | Swap target to `rfq_iam_ms` | Future canonical IAM service — connector target changes, copilot code doesn't |

**First thin version:** Read `AUTH_BYPASS_*` from settings. Return a hardcoded `RoleContext`. This is exactly what manager does today.

---

## 9. Tool Progression

> [!WARNING]
> Do NOT build the tool layer before the connector layer is stable. A tool is a thin wrapper around a connector call + envelope construction. Building the tool without a working connector means you're writing untestable code.

### 9.1 Introduction order

| Order | Tool | Phase | Why this order | Backing |
|-------|------|-------|---------------|---------|
| 1 | `get_rfq_snapshot` | 4 | Default read for every RFQ-bound conversation. Must work first | Intelligence `/snapshot` |
| 2 | `get_rfq_profile` | 4 | RFQ metadata from manager. Complements snapshot | Manager `/rfqs/{id}` |
| 3 | `get_rfq_stage` | 4 | Foundation for Pillar 1. Must exist before `StageController` | Manager `/rfqs/{id}/stages` |
| 4 | `get_capability_status` | 5 | Pillar 4 "speakable absence". Local — no external dependency | Local dict |
| 5 | `get_intelligence_briefing` | 6 | Expands RFQ-scoped tool surface | Intelligence `/briefing` |
| 6 | `get_workbook_review` | 6 | Completeness queries | Intelligence `/workbook-review` |
| 7 | `get_workbook_profile` | 6 | Drill-down queries | Intelligence `/workbook-profile` |
| 8 | `list_rfqs` | 6 | Portfolio Mode B primary tool | Manager `/rfqs` |
| 9 | `get_rfq_stats` | 6 | Portfolio aggregate stats | Manager `/rfqs/stats` |
| 10 | `get_rfq_analytics` | 6 | Portfolio analytics | Manager `/rfqs/analytics` |
| 11 | `resolve_rfq_by_name` | 6 | Disambiguation for Mode B | Manager `/rfqs` + heuristics |
| — | `search_mr_documents` | **P2** | Document RAG exception path | pgvector |
| — | `run_sandbox_scenario` | **P2** | What-if sandbox | Local computation |

### 9.2 Tool structure pattern

Every tool follows the same shape:
1. Pydantic input schema (tool parameters)
2. Pydantic output schema (the `value` field inside `ToolResultEnvelope`)
3. A function that calls the appropriate connector method
4. Wraps the result in `ToolResultEnvelope` with `source_ref`, `confidence`, `validated_against`, `retrieved_at`
5. Registered via `@tool` decorator

---

## 10. Evaluation Progression

### 10.1 Introduction order

| Order | What | Phase | Why this order |
|-------|------|-------|---------------|
| 1 | Smoke/integration tests | 0–3 | Basic HTTP endpoint tests, DB CRUD, round-trip turn pipeline |
| 2 | Unit tests per controller | 4–5 | Mocked dependencies, isolated logic verification |
| 3 | Behavior checks | 5 | Stage-appropriate behavior, role-aware output differences, confidence rendering |
| 4 | Golden-set cases | 7 | Hand-curated cases exercising all four pillars |
| 5 | CI integration | 7 | Golden-set runs on every commit |
| 6 | Grounding-specific cases | 7 | Verify source_ref enforcement, retry behavior, safe fallback |
| 7 | Role-boundary cases | 7 | Verify forbidden content is redacted/refused per role |
| 8 | Confidence-rendering cases | 7 | Verify qualifiers for pattern-based, honest absence for cold-start |

### 10.2 What NOT to build

- A giant eval harness before Phase 5 (you'd be evaluating a copilot that can't do anything interesting yet)
- LLM-as-judge scoring (Priority 2 — only if golden set methodology is proven)
- Synthetic test generation (cold-start incompatible — cannot honestly curate from 1 sample)
- Cross-RFQ regression testing (cold-start: only one golden sample exists)

---

## 11. Learning Guidance

### Phase 0 — Bootstrap

| What to learn | What to observe | Question to answer afterward |
|--------------|----------------|------------------------------|
| FastAPI application factory pattern | `create_app()` in `app.py` | Why does `create_app()` exist instead of creating `app` at module level? |
| SQLAlchemy engine lifecycle | `database.py` engine + SessionLocal | What is the difference between `engine`, `SessionLocal`, and a specific `session`? |
| BACAB dependency injection pattern | Manager's `app_context.py` | How does `Depends()` compose layers without circular imports? |

### Phase 1 — Contracts

| What to learn | What to observe | Question to answer afterward |
|--------------|----------------|------------------------------|
| Pydantic v2 validators and model_config | Your new `envelope.py`, `session.py` | How does Pydantic enforce `ConfidenceLevel` as a closed enum? |
| SQLAlchemy ORM 2.0 `mapped_column` style | Your new ORM models | How does `mapped_column(nullable=True)` differ from `Optional` in Pydantic? |
| Alembic autogenerate | Your first migration | What happens if you add a column to the ORM model but don't create a migration? |

### Phase 2 — Sessions

| What to learn | What to observe | Question to answer afterward |
|--------------|----------------|------------------------------|
| State machine patterns in plain Python | `ModeController` | Why is the portfolio → rfq_bound transition one-way? |
| FastAPI Depends() dependency chain | `app_context.py` wiring | Can you trace the full dependency chain from a route parameter to a database query? |

### Phase 3 — Vertical Slice

| What to learn | What to observe | Question to answer afterward |
|--------------|----------------|------------------------------|
| Azure OpenAI chat completions API | `azure_openai_connector.py` | What is the difference between `messages`, `tools`, and `tool_choice` in a completion call? |
| Context window as a managed resource | `ContextBuilder.build()` | Why does the stable prefix come first in the messages array? |
| Function calling flow | The tool_call → tool_result → narration three-step pattern | Why does the copilot make 2–3 LLM calls per turn, not 1? |

### Phase 4 — Connectors & Tools

| What to learn | What to observe | Question to answer afterward |
|--------------|----------------|------------------------------|
| HTTP client patterns with error handling | `manager_connector.py` | What happens when manager returns a 404 for an unknown rfq_id? |
| The ToolResultEnvelope contract | Every tool's return value | Can you explain what `source_ref.locator` means for a workbook-derived value? |
| MCP-shaped tool design | Tool schemas and naming | What would need to change if these tools became native MCP servers? |

### Phase 5 — Pillars 1, 3, 4

| What to learn | What to observe | Question to answer afterward |
|--------------|----------------|------------------------------|
| Manager-native stage truth | `stage_controller.py` reading real `rfq_stage` data | What is the difference between a `stage_template` and an `rfq_stage`? Why does the copilot key on templates? |
| Role-aware generation | Two sessions, same question, different answers | Where exactly in the pipeline does the role framing get injected? Where does the output filter run? |
| Confidence-aware rendering | Three confidence states in one conversation | What prevents the LLM from stating a pattern-based result without the qualifier? |

### Phase 6 — Guardrails & Safety

| What to learn | What to observe | Question to answer afterward |
|--------------|----------------|------------------------------|
| Intent classification with structured outputs | `intent_controller.py` | What happens when the intent classifier returns `out_of_scope`? |
| Grounding enforcement with retry | `grounding_controller.py` | After 2 failed retry attempts, what does the user see? Why is this trade (silence > hallucination) correct? |
| Knowledge boundary rule | `general_knowledge` vs `rfq_factual` routing | Why can the copilot answer "what is PWHT?" without tools but NOT "does this RFQ require PWHT?" without tools? |

### Phase 7 — Evaluation

| What to learn | What to observe | Question to answer afterward |
|--------------|----------------|------------------------------|
| Golden-set evaluation methodology | `golden_set/harness.py` | Why are golden-set checks structural (intent, tool, source_ref presence) rather than checking exact LLM wording? |
| Correlation ID propagation | Request → LLM call → tool call → response, all sharing one ID | Can you trace a single user turn through every log line it generates? |

---

## 12. Risk Register

| # | Risk | Consequence | Mitigation |
|---|------|------------|-----------|
| R1 | **Building too many files too early** | 40 files with 10 lines each, nothing tested, nothing integrated | Follow the phase order. No file created before its phase |
| R2 | **Drifting from BACAB layering** | Controllers calling connectors through shortcuts, routes doing business logic | Verify after every phase: route → controller → datasource/connector. No skips |
| R3 | **Overusing the LLM before typed contracts exist** | LLM returns free-form JSON that doesn't match Pydantic models → silent failures | Contracts (Phase 1) before LLM calls (Phase 3). Pydantic validation at every boundary |
| R4 | **Inventing fake manager stage truth** | Abstract lifecycle enum that drifts from manager's `workflow` / `stage_template` / `rfq_stage` schema | `StageController` reads manager-native data. `stage_config` is keyed on real `stage_template` identifiers from manager's seed data |
| R5 | **Overcommitting to document RAG too early** | Building pgvector, embeddings, reranker before the primary retrieval path (structured APIs) is proven | Document RAG is Priority 2. Build intelligence snapshot retrieval first. Add documents only after P1 is complete |
| R6 | **Role-awareness pretending a finished IAM service exists** | Building complex IAM integration that blocks the role pillar | Use auth-bypass mode (same as manager). Role comes from settings in Phase 1. The connector seam allows swapping to `rfq_iam_ms` later without code changes |
| R7 | **Letting the agent overbuild Phase 2 features during Phase 1** | Semantic memory, what-if sandbox, proactive events, third role — all appearing before P1 is complete | Strict deferred list (§1.4). Every feature must be checked against P1/P2/P3 priority before implementation |
| R8 | **Intent classification becoming a bottleneck** | Overly complex taxonomy, slow LLM calls, incorrect routing | Start with 7 intents (the brief's list). Use a simple structured-output prompt. Iterate based on golden-set failures |
| R9 | **Grounding guardrail being too aggressive** | Rejecting valid responses that have source_refs in a slightly different format | Tune the regex/proximity check on real responses before tightening. Log rejections vs passes for calibration |
| R10 | **Testing against live Azure OpenAI in CI without budgets** | Token costs, flaky tests, rate limits | Mock Azure OpenAI in unit tests. Reserve real API calls for golden-set integration runs with a token budget cap |
| R11 | **Prompt growing beyond token budget** | Context rot, lost-in-the-middle, accuracy degradation (the exact problems §9.1 warns about) | `ContextBuilder` must enforce `total_budget`. History compression must exist before prompts get large. Monitor token usage in logs |
| R12 | **Not verifying against the frozen brief** | Implementation drifts from the brief's decisions without noticing | After each phase, check: does this match §10.2 layout? Does this respect the decision log (D1–D18)? |

---

## 13. Final Recommended Build Order

```
Phase 0 ─────▶ Phase 1 ─────▶ Phase 2 ─────▶ Phase 3 ─────▶ Phase 4 ─────▶ Phase 5 ─────▶ Phase 6 ─────▶ Phase 7
```

| Transition | Reason |
|-----------|--------|
| 0 → 1 | You cannot build layers without contracts. Models come first |
| 1 → 2 | Sessions are the organizational backbone. Everything lives on a session |
| 2 → 3 | The vertical slice proves the pipeline exists before you enrich it |
| 3 → 4 | Tools connect the pipeline to real data. Without them, the LLM hallucinates everything |
| 4 → 5 | The three behavioral pillars (stage/role/confidence) require working tools to be meaningful |
| 5 → 6 | Guardrails enforce the pillars. They sit on top of working behavior, not before it |
| 6 → 7 | Evaluation verifies the complete system. It must run against real, guardrailed behavior |

---

## 14. Recommended First Implementation Slice

### The first slice: Phase 1 — Contracts and Persistence Foundations

**What to build:** All Pydantic models (`envelope.py`, `session.py`, `conversation.py`, `turn.py`, `prompt.py`), ORM models for `chatbot_sessions` and `chatbot_messages`, Alembic migration, extended `settings.py` with Azure OpenAI / service URL configuration.

### Why this slice comes first

1. Every later phase imports from `models/`. If models don't exist, nothing compiles
2. The `ToolResultEnvelope` is the frozen contract across all tools — defining it first prevents drift
3. The session model with `SessionMode` enum is the backbone of the two-mode design — every controller reads session state
4. The Alembic migration proves the database schema is real, not aspirational
5. This slice has **zero external dependencies** — no Azure OpenAI, no manager, no intelligence. It can be built and fully tested in isolation

### Checklist before asking an agent to code this slice

- [ ] I have read and understood § 6 (Pillar 2) — `ToolResultEnvelope`, `SourceRef`, `ConfidenceLevel` contracts
- [ ] I have read and understood § 4 — session modes (`rfq_bound`, `portfolio`, `pending_pivot`)
- [ ] I have read and understood § 9.2 — `chatbot_conversations` table schema
- [ ] I have read and understood § 10.2 — the frozen `models/` file layout
- [ ] I know what `mapped_column(nullable=True)` means in SQLAlchemy 2.0
- [ ] I know what Pydantic `model_config` controls
- [ ] I have the manager's model files (`rfq.py`, `rfq_stage.py`, `workflow.py`) open as pattern reference
- [ ] I can explain why `ConfidenceLevel` has exactly three values and where they come from (§8, D8)
- [ ] I can explain why `Session.rfq_id` is nullable (portfolio mode)
- [ ] I have updated `.env.example` with the new configuration variables I expect
- [ ] I have Alembic initialized and working against the chatbot's Postgres database
- [ ] I can run `pytest tests/` and see the existing tests still pass
