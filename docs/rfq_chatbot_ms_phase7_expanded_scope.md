# rfq_chatbot_ms — Phase 7 Expanded Scope & Action Plan

> **Document type:** Scope definition + sequenced action plan  
> **Source of truth:** `rfq_chatbot_ms_architecture_brief_v2_F.html` (§9.7, §9.8, §12.1, §13)  
> **Companion:** `implementation_plan_chatbot.md` Phase 7 section  
> **Predecessor:** Phase 6 post-implementation audit (April 2026)  
> **Status:** Ready for review — no implementation until decisions are validated  
> **Date:** 2026-04-20

---

## 1. Why Phase 7 Is Expanded

The original Phase 7 in the implementation plan was scoped as: golden set, correlation logging, demo verification, polish. That scope remains — but it is no longer sufficient.

Phases 1–6 built a **structurally correct** copilot: the pipeline works, the four pillars are implemented, the tests pass. What Phase 7 must now deliver is a copilot that is **visibly intelligent** — one where the jury sees not just correct architecture but genuine context engineering depth.

Two categories of work are merged into this expanded Phase 7:

- **Track A — Defense Infrastructure** (originally planned): golden set, correlation IDs, structured logging, `/ready` endpoint, demo script verification, Phase 5 shim cleanup. These are non-negotiable.
- **Track B — Intelligence Elevation** (surfaced post-audit): structured system prompt, RFQ context pre-loading, multi-turn awareness, response formatting, domain vocabulary, mode-specific welcome, suggested follow-ups. These are what separate "correctly implemented" from "genuinely impressive."

Both tracks touch the same files (primarily `context_builder.py`, `chat_controller.py`, `config/`). They should be done together, not sequentially.

---

## 2. Scope — What Is In vs. What Is Out

### In Scope (Phase 7)

| ID | Item | Track | Brief Ref |
|----|------|-------|-----------|
| 7.01 | Structured XML system prompt rewrite | B | §9.1 |
| 7.02 | Domain vocabulary section in prompt | B | §9.1 |
| 7.03 | Response formatting directives in prompt | B | §9.1 |
| 7.04 | RFQ context pre-loading on first turn | B | §9.1, §13 |
| 7.05 | Mode-specific welcome behavior | B | §4, §13 |
| 7.06 | Suggested follow-up questions in responses | B | — |
| 7.07 | Multi-turn intent continuity (last-intent carry-forward) | B | §9.5 |
| 7.08 | Structured Azure OpenAI messages (multi-turn array) | B | §9.1, P1-16 |
| 7.09 | Correlation ID middleware + propagation | A | §9.7, P1-15 |
| 7.10 | Structured logging setup (JSON format) | A | §9.7, P1-15 |
| 7.11 | `/ready` endpoint | A | Plan §6 |
| 7.12 | Phase 5 greeting shim removal | A | Audit F5 |
| 7.13 | Golden set — case files + harness + judges | A | §9.8, P1-14 |
| 7.14 | Defense demo script verification (4 beats) | A | §13 |
| 7.15 | OpenAPI/Swagger verification against live routes | A | Audit P7-5 |
| 7.16 | `/metrics` endpoint (Prometheus counters) | B | Manager H5 pattern |
| 7.17 | Capability-status vocabulary enrichment | B | §8.4 |

### Out of Scope (remains deferred)

| Item | Why out | When it activates |
|------|---------|-------------------|
| Token budget enforcement (`utils/tokens.py`) | Requires tiktoken integration, testing; not demo-visible | Post-defense |
| History compression (`history_translator.py`) | 6-turn window sufficient for demo conversations | Post-defense |
| Document RAG (`search_mr_documents`) | No embedding infrastructure; Priority 2 | ≥10 MR packages |
| What-if sandbox (`run_sandbox_scenario`) | HOTL; Priority 2 | Post-Phase 1 |
| LLM-as-judge evaluation | Priority 2; enriches golden set | After golden set proves methodology |
| Third role (`junior_engineer`) | Priority 2; two-role contrast sufficient | If time permits |
| Full IAM/JWT middleware | Infrastructure dependency | When `rfq_iam_ms` delivers tokens |

---

## 3. Implementation Sequence

The order matters. Earlier items create foundations that later items depend on.

```
Step 1 ──▶ Step 2 ──▶ Step 3 ──▶ Step 4 ──▶ Step 5
Prompt     Pipeline    Observ-    Golden     Final
Rewrite    Upgrades    ability    Set        Polish
```

### Step 1 — System Prompt Rewrite (7.01, 7.02, 7.03, 7.17)

**Goal:** Transform the flat-text system prompt into a structured, XML-tagged prompt configuration that encodes persona, domain constraints, response rules, and confidence behavior as parseable sections.

**Why first:** Every subsequent step (welcome behavior, follow-ups, formatting) depends on the prompt being structured enough to support conditional sections. Doing this first means all later enrichments slot in cleanly.

**Files touched:**
- `controllers/context_builder.py` — rewrite `_build_stable_prefix()` to emit XML-structured prompt
- `config/prompt_templates.py` — **new file** — externalized prompt sections (persona, domain vocab, response rules, formatting directives)
- `config/capability_status.py` — add 3–4 new entries (historical comparison, similar RFQ, supplier recommendation, material pricing)

**What the structured prompt looks like:**

```xml
<persona>
You are RFQ Copilot, a workflow-constrained conversational assistant for
GHI / Albassam Group estimation engineers working on industrial pressure
vessel and heat exchanger RFQs for Saudi Aramco.
</persona>

<domain_constraints>
You operate exclusively within the RFQ lifecycle domain. You do not assist
with topics outside industrial estimation, procurement, or project management.
</domain_constraints>

<domain_vocabulary>
Key terms you must understand precisely:
- MR package: Material Requisition package (ZIP of technical documents from Aramco)
- BOQ: Bill of Quantities (the estimation workbook)
- PWHT: Post-Weld Heat Treatment (a fabrication requirement)
- RT: Radiographic Testing (a quality inspection method)
- U-Stamp / NB registration: ASME certification requirements
- SAMSS/SAES/SAEP: Saudi Aramco engineering standards
- Cost-per-ton: primary cost metric for pressure vessel estimation
</domain_vocabulary>

<response_rules>
- Lead with the direct answer, then provide supporting detail
- Use markdown formatting: headers for sections, bold for key values, tables for comparisons
- Keep responses under 250 words unless the user requests detail
- When presenting numerical data, always include the source system and artifact
- End RFQ-specific responses with 1-2 contextual follow-up suggestions
</response_rules>

<role_framing>
{role_tone_directive}
{role_depth_directive}
</role_framing>

<stage_framing>
{stage_prompt_fragment}
{stage_label}
</stage_framing>

<confidence_behavior>
{confidence_directives}
</confidence_behavior>

<grounding_rules>
- Every RFQ-specific factual claim must be traceable to a retrieved tool result
- If no tool evidence is available, state this honestly and suggest alternatives
- Never fabricate RFQ-specific data, cost figures, dates, or status information
- For general domain knowledge (what is PWHT, how does Aramco bidding work), answer from training knowledge
</grounding_rules>
```

**Done when:** Unit tests for `ContextBuilder` pass with the new XML-structured output. The `test_context_builder.py` assertions updated. Manual verification that Azure OpenAI responds correctly to the new format.

---

### Step 2 — Pipeline Upgrades (7.04, 7.05, 7.06, 7.07, 7.08)

**Goal:** Make the copilot feel intelligent across multiple turns, not just structurally correct on each individual turn.

#### 7.04 — RFQ Context Pre-Loading

**What:** When `handle_turn` processes the first turn in an RFQ-bound session, auto-fetch `get_rfq_profile` and `get_rfq_snapshot` regardless of the user's query content. Store the results as "session context" available to all subsequent turns.

**Files touched:**
- `controllers/chat_controller.py` — add `_maybe_preload_rfq_context()` called on first turn detection
- `controllers/context_builder.py` — accept a `preloaded_context` parameter and inject it into the variable suffix

**Done when:** First turn in an RFQ-bound session can reference the RFQ name, client, and stage even if the user just says "hello."

#### 7.05 — Mode-Specific Welcome Behavior

**What:** When the first turn is a greeting (conversational intent, first turn), inject a mode-appropriate welcome:
- RFQ-bound: "I'm ready to help with {rfq_name} — a {client} project currently in {stage_name}. What would you like to know?"
- Portfolio: "I can help you explore your active RFQ pipeline. Which project would you like to discuss, or would you like a portfolio overview?"

**Files touched:**
- `controllers/chat_controller.py` — detect first-turn + conversational intent → inject welcome context
- `config/prompt_templates.py` — welcome templates per mode

**Done when:** Demo beat 0 (preamble) transitions smoothly into a context-aware welcome that immediately demonstrates the copilot knows which RFQ it's working with.

#### 7.06 — Suggested Follow-Up Questions

**What:** Add a `<follow_up_guidance>` section to the prompt that instructs the LLM to end RFQ-specific responses with 2-3 contextual next-step suggestions. These should be based on what data is available (stage, snapshot, profile) and what the user hasn't asked yet.

**Files touched:**
- `config/prompt_templates.py` — follow-up instruction template
- `controllers/context_builder.py` — inject follow-up guidance into the stable prefix for rfq_specific intent

**Done when:** RFQ-specific responses consistently end with actionable follow-up suggestions.

#### 7.07 — Multi-Turn Intent Continuity

**What:** Carry the last resolved intent forward as context for ambiguous follow-up turns. If the user's previous turn resolved to `rfq_specific` and their current turn is short/ambiguous (e.g., "and the deadline?"), treat it as rfq_specific rather than falling back to conversational.

**Files touched:**
- `controllers/intent_controller.py` — accept `last_resolved_intent` parameter; use it as a tiebreaker when classification is ambiguous
- `controllers/chat_controller.py` — pass last intent to the classifier
- `models/conversation.py` or message-level JSONB — persist intent classification per message (the plan already specified this for Phase 6)

**Done when:** Short follow-up queries within an RFQ-bound conversation maintain context without re-triggering disambiguation or falling to conversational.

#### 7.08 — Structured Azure OpenAI Messages

**What:** Refactor `_build_azure_messages` to send actual multi-turn message arrays instead of embedding conversation history as text inside one user message. The system message contains the stable prefix. Previous turns become actual `{"role": "user/assistant", "content": "..."}` entries. The latest user turn + retrieved facts become the final user message.

**Files touched:**
- `controllers/chat_controller.py` — rewrite `_build_azure_messages()`
- `controllers/context_builder.py` — return structured message list instead of flat text for history

**Why this matters:** Azure OpenAI caches the stable prefix across calls within the same conversation (brief §9.1 explicitly calls this out as P1-16). With the current flat format, there's nothing to cache. With structured messages, the ~2,200 token system prompt is cached after the first turn, reducing cost and latency on subsequent turns.

**Done when:** Azure OpenAI calls use multi-message format. Token usage drops measurably on turn 2+ within a conversation.

---

### Step 3 — Observability (7.09, 7.10, 7.11, 7.16)

**Goal:** Make every request traceable and the service operationally mature.

#### 7.09 + 7.10 — Correlation IDs + Structured Logging

**What:** 
- Generate a `X-Correlation-ID` (UUID) per request via FastAPI middleware
- Propagate it through all connector calls (manager, intelligence, Azure OpenAI) as an HTTP header
- Inject it into every structured log line
- Switch logging output to JSON format

**Files created:**
- `utils/correlation.py` — middleware + context var for correlation ID
- `utils/logging.py` — JSON formatter setup, correlation ID injection

**Files touched:**
- `app.py` — register correlation ID middleware
- `connectors/manager_connector.py` — add correlation header to HTTP calls
- `connectors/intelligence_connector.py` — same
- `connectors/azure_openai_connector.py` — log correlation ID with LLM calls

**Done when:** A single `POST /sessions/{id}/turn` produces log lines that all share the same correlation ID, traceable from route entry through intent classification through tool execution through LLM call through response persistence.

#### 7.11 — `/ready` Endpoint

**What:** Readiness probe that checks DB connectivity + Azure OpenAI reachability.

**Files touched:**
- `routes/health_route.py` — add `GET /ready`

**Done when:** Kubernetes/Docker health checks can distinguish "service is alive" (`/health`) from "service is ready to serve traffic" (`/ready`).

#### 7.16 — `/metrics` Endpoint

**What:** Prometheus-compatible counters: `turns_total`, `tool_calls_total` (by tool_name), `intent_classifications_total` (by intent), `grounding_gaps_total`, `upstream_errors_total` (by service), `response_latency_seconds` (histogram).

**Files created:**
- `utils/metrics.py` — counter/histogram definitions
- `routes/metrics_route.py` — `/metrics` endpoint

**Done when:** Prometheus can scrape the endpoint and display basic copilot health dashboards.

---

### Step 4 — Golden Set & Demo Verification (7.13, 7.14)

**Goal:** Prove that every claim in the brief has a corresponding behavior in the running system.

**Why after Steps 1-3:** The golden set should test the *enriched* copilot, not the pre-enrichment version. Running golden set cases against the structured prompt + pre-loaded context + follow-up suggestions validates the final product.

#### 7.13 — Golden Set

**Structure:**

```
golden_set/
├── cases/
│   ├── beat1_deterministic_grounding.json
│   ├── beat2_pattern_based_confidence.json
│   ├── beat3_honest_absence.json
│   ├── beat4_role_contrast_estimation.json
│   ├── beat4_role_contrast_executive.json
│   ├── stage_aware_go_nogo.json
│   ├── stage_aware_default.json
│   ├── grounding_gap_no_evidence.json
│   ├── grounding_gap_upstream_failure.json
│   ├── intent_rfq_specific.json
│   ├── intent_general_knowledge.json
│   ├── intent_unsupported.json
│   ├── intent_conversational.json
│   ├── intent_disambiguation.json
│   ├── disambiguation_resolution.json
│   ├── disambiguation_abandonment.json
│   ├── capability_status_analytics.json
│   ├── capability_status_briefing.json
│   ├── welcome_rfq_bound.json
│   ├── welcome_portfolio.json
│   ├── follow_up_continuity.json
│   └── knowledge_boundary.json
├── harness.py          # pytest runner — loads cases, creates sessions, sends turns
├── judges.py           # assertion helpers — regex matchers, forbidden patterns, structural checks
└── conftest.py         # fixtures — live backends required
```

**Case schema:**
```json
{
  "case_id": "beat1_deterministic_grounding",
  "description": "Demo beat 1 — deterministic answer with source_ref",
  "session": {
    "mode": "rfq",
    "rfq_id": "<seeded-rfq-uuid>",
    "role": "estimation_dept_lead"
  },
  "turns": [
    {
      "user_content": "What's the current stage for this RFQ?",
      "expect": {
        "intent": "rfq_specific",
        "tool_selected": "get_rfq_stage",
        "source_refs_present": true,
        "forbidden_patterns": ["I don't have", "unavailable", "I cannot"],
        "required_patterns": ["stage", "Go"]
      }
    }
  ]
}
```

**Assertions are structural, never textual:** Check intent, tool selection, source_ref presence, forbidden/required patterns. Never assert exact LLM wording.

**Done when:** `pytest golden_set/ -v` passes with ≥20 cases covering all four pillars + the enrichment behaviors (welcome, follow-ups, intent continuity).

#### 7.14 — Defense Demo Script Verification

**What:** Walk through the four beats from §13 as golden-set cases. Verify that:
- Beat 1: deterministic answer, source_ref present, no hedging
- Beat 2: pattern-based answer, confidence marker emitted
- Beat 3: honest absence, named future condition present
- Beat 4: same question, two sessions (estimation_dept_lead vs executive), visibly different framing

Plus the enrichment beats:
- Beat 0 (welcome): RFQ-bound session gets context-aware greeting
- Beat 5 (optional): portfolio disambiguation auto-resolves to IF-25144

**Done when:** All defense demo beats pass as golden-set cases. The demo can be walked through live in under 5 minutes.

---

### Step 5 — Final Polish (7.12, 7.15)

#### 7.12 — Phase 5 Greeting Shim Removal

**What:** Remove `_is_phase5_legacy_rfq_greeting()` from `IntentController`. The Phase 6 intent classifier + the new welcome behavior (7.05) handle this case correctly.

**Files touched:**
- `controllers/intent_controller.py` — remove method and its call
- `tests/` — remove/update tests that depended on the shim

**Done when:** "hello copilot" in an RFQ-bound session triggers the welcome behavior through the normal intent pipeline, not a hardcoded shim.

#### 7.15 — OpenAPI Verification

**What:** Run the app, export the auto-generated OpenAPI spec, compare against `rfq_chatbot_ms_openapi_current.yaml`. Fix any drift. Confirm turn endpoint path (`/sessions/{id}/turn` vs `/conversations/{id}/turn`) is documented correctly.

**Done when:** OpenAPI spec matches the running implementation. Swagger UI renders correctly for all endpoints.

---

## 4. Exit Criteria — Phase 7 Complete

- [ ] System prompt uses XML-structured format with persona, domain vocabulary, response rules, confidence behavior, and grounding rules
- [ ] First turn in RFQ-bound session auto-loads RFQ context and delivers a mode-aware welcome
- [ ] RFQ-specific responses include 1-2 suggested follow-up questions
- [ ] Multi-turn conversations maintain intent continuity for short follow-ups
- [ ] Azure OpenAI calls use structured multi-message format (prompt caching enabled)
- [ ] Correlation ID visible in every log line for a single request trace
- [ ] `/ready` endpoint checks DB + Azure OpenAI connectivity
- [ ] `/metrics` endpoint exposes Prometheus-compatible counters
- [ ] Golden set: ≥20 cases, all passing, covering all four pillars + enrichment behaviors
- [ ] Defense demo beats 0–4 all pass as golden-set cases
- [ ] Phase 5 greeting shim removed
- [ ] OpenAPI spec matches running implementation
- [ ] Capability-status vocabulary expanded with 3+ new entries

---

## 5. What This Phase Does NOT Change

- **No new database tables or migrations.** All changes are in controllers, config, and utils.
- **No new BACAB layers.** The architecture remains routes → controllers → datasources/connectors.
- **No new external dependencies.** Everything uses existing libraries (httpx, openai, pydantic, sqlalchemy).
- **No changes to the turn pipeline flow.** The sequence remains: intent → stage → role → tools → context → LLM → guardrail → persist. We're enriching what happens inside each step, not rearranging them.
- **No changes to the data model.** Session, conversation, and message schemas are unchanged.

---

## 6. Risk Register

| Risk | Consequence | Mitigation |
|------|------------|-----------|
| XML-structured prompt causes LLM to treat tags as content | Responses contain XML artifacts | Test with Azure OpenAI model before committing; GPT-4.1/4o handle XML well |
| Pre-loading context on first turn adds latency | First response noticeably slower | Accept the tradeoff — first-turn latency is less important than context-aware welcome |
| Follow-up suggestions feel generic | Reduces wow factor | Condition suggestions on available data (stage, snapshot fields) rather than static templates |
| Golden set cases are too brittle | False failures on every LLM response variation | Structural checks only — intent, tool, source_ref, forbidden patterns. Never exact text matching |
| Correlation ID propagation breaks existing tests | Test failures block progress | Add correlation middleware after unit tests pass, update integration tests |

---

*Phase 7 expanded scope — rfq_chatbot_ms · April 2026*  
*Prepared for Guidara — BACAB Consulting · GHI × Albassam Group*
