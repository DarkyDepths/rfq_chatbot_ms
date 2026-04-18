# Phase 6 — Implementation Pack v1.0

**Status:** Frozen — no conceptual decisions remain open
**Scope:** `rfq_chatbot_ms` — Decision Control Layer (Mode A + Mode B)
**Posture:** Pre-generation control, deterministic classification, per-intent grounding, contract-stable
**Pairing:** This Pack defines *what*. The companion Blueprint defines *how* (file-by-file sequence).

---

## 0. Executive summary

Phase 6 changes `rfq_chatbot_ms` from *"I answer differently depending on context"* to *"I decide whether and how I am allowed to answer at all."*

Phase 5 was prompt enrichment. Phase 6 is decision control.

The phase ships one core idea: a deterministic pre-generation control layer that classifies intent, routes by knowledge boundary, enforces grounding policy, handles disambiguation, and validates output — all before and after the LLM generates a response.

Phase 6 delivers four milestones:

1. **M6.1 — Intent + Boundary Router**: classify the user turn into a 5-intent taxonomy and route to the correct knowledge path.
2. **M6.2 — Grounding Guardrail**: enforce per-intent evidence policy so RFQ-specific responses require tool-backed evidence.
3. **M6.3 — Disambiguation**: handle ambiguous RFQ references through conversation-history-based stateless clarification.
4. **M6.4 — Verification + Close-out**: output guardrail enforcement, structured observability, golden-set test scenarios, and Phase 7 readiness gates.

Phase 6 produces **no API contract change**. No new endpoints, no new DTOs, no new response shapes. Disambiguation responses are plain assistant messages inside the existing `TurnResponse.content`. All Phase 6 decisions are observable through structured logs and test outcomes only — the same posture as Phase 5.

---

## 1. Phase 6 scope fences

### 1.1 What Phase 6 is

A deterministic pre-generation control layer over the existing Phase 5 turn pipeline. The intent classifier decides *what kind of question* the user is asking. The boundary router decides *which knowledge path* the question takes. The grounding guardrail decides *whether the answer is permitted*. The output guardrail *validates* the response after generation.

### 1.2 What Phase 6 is not

- Not an LLM-based intent classifier.
- Not a multi-agent or A2A orchestration layer.
- Not a document RAG expansion.
- Not a semantic or procedural memory system.
- Not a portfolio analytics engine.
- Not a proactive subscription or notification system.
- Not a what-if sandbox.
- Not a contract redesign.
- Not an auth platform overhaul.
- Not a chatbot-as-intelligence-engine transformation.

All of the above belong to Phase 7 or later.

### 1.3 Frozen items (do not move in Phase 6)

Everything frozen in Phase 5, plus:

- Session creation/binding rules.
- One-way RFQ binding semantics.
- One conversation per session invariant.
- Non-streaming Azure OpenAI posture; no native function-calling.
- Error status mapping.
- All DTO shapes: `ChatbotSessionRead`, `TurnRequest`, `TurnResponse`, `ConversationReadResponse`, `ConversationMessageRead`, `SourceRef`.
- `PromptEnvelope` public shape: `stable_prefix`, `variable_suffix`, `total_budget`.
- `tool_calls` persisted but not surfaced on read DTOs.
- Phase 5 declarative config structure (`stage_profiles.py`, `role_profiles.py`).
- Phase 5 subtractive tool gating (intersection rule).
- Phase 5 confidence marker format.
- Phase 5 structured log field names (all `phase5.*` fields remain and continue emitting).

---

## 2. Decision Set A — Intent taxonomy

### A.1 Closed set

Exactly five intents. No additions in Phase 6.

| Intent | Meaning |
|---|---|
| `rfq_specific` | User is asking about a specific RFQ, its data, status, stage, or artifacts. |
| `general_knowledge` | User is asking about domain knowledge without referencing a specific RFQ. |
| `unsupported` | User is asking for a capability that is known-absent (Phase 5 capability-status list). |
| `disambiguation` | User's question references an RFQ but the context is insufficient to identify which one. |
| `conversational` | Greetings, small talk, follow-ups, or anything that doesn't need retrieval or domain routing. |

### A.2 Design rules

- Intent describes **user intention**, not system routing. There is no `rfq_operational` or `rfq_intelligence` intent. Which backend serves the answer is a tool-planner decision that lives downstream of intent classification.
- The intent taxonomy is a classification of *what the user wants*, not *where the system gets it*.
- Intent classification is **deterministic only** in Phase 6. No LLM classifier, no scoring model, no probability thresholds. LLM-assisted classification is Phase 7+.
- When the classifier cannot match a known pattern, the intent defaults to `conversational`. This is safe: the user gets a helpful conversational response without RFQ-specific claims.

### A.3 Classification signals

The classifier uses keyword and pattern-based matching on the user's turn content plus session context. Canonical signal patterns per intent:

**`rfq_specific`** — Matches when the turn references a specific RFQ:

- Pronouns or demonstratives tied to RFQ context: "this RFQ", "the project", "our RFQ", "it" (when session is RFQ-bound).
- RFQ data vocabulary: "deadline", "owner", "status", "stage", "cost", "client", "priority".
- Session context: if the session is `rfq_bound`, domain questions are presumed RFQ-specific unless clearly general.
- Critical rule: an RFQ-bound session creates a **bias toward `rfq_specific`** for domain-adjacent questions. A question like "what's the timeline?" in an RFQ-bound session is `rfq_specific`, not `general_knowledge`.

**`general_knowledge`** — Matches when the turn asks about domain concepts without RFQ reference:

- Definitional patterns: "what is PWHT?", "how does RT work?", "explain ASME U-stamp".
- General industry vocabulary without specific RFQ context: "typical cost-per-ton for pressure vessels", "standard lead time for X".
- No RFQ-referencing pronouns, no session-bound RFQ identifiers in the turn.
- Critical rule: in a portfolio (global) session without RFQ binding, domain questions that don't reference a specific RFQ are `general_knowledge`.

**`unsupported`** — Matches the Phase 5 `CAPABILITY_STATUS_ENTRIES` keyword list:

- "briefing", "workbook review", "analytics", "portfolio", "grand total", "final price", etc.
- Classification precedence: `unsupported` takes priority over all other intents when a capability-status keyword matches. This preserves Phase 5 behavior.

**`disambiguation`** — Matches when the turn references an RFQ but context is insufficient:

- RFQ-referencing language in a **non-RFQ-bound** session: "what's the status of this RFQ?" in a portfolio session.
- Ambiguous pronouns without a bound context: "the last one", "that project".
- Critical rule: `disambiguation` only fires when the session is **not** RFQ-bound. In an RFQ-bound session, the RFQ is known and the intent resolves to `rfq_specific`.

**`conversational`** — Matches when nothing else does:

- Greetings: "hello", "hi", "good morning".
- Small talk: "how are you?", "thanks", "ok".
- Follow-ups that don't trigger domain vocabulary.
- The catch-all default when no other intent pattern matches.

### A.4 Classification precedence

When multiple intents could match, the following precedence applies:

```
1. unsupported        (capability-status keywords always win)
2. disambiguation     (ambiguous RFQ reference in non-bound session)
3. rfq_specific       (RFQ-referencing language in bound session or explicit RFQ reference)
4. general_knowledge  (domain vocabulary without RFQ reference)
5. conversational     (default fallback)
```

This precedence is deterministic and requires no scoring.

---

## 3. Decision Set B — Intent + Boundary Router (M6.1)

### B.1 Routing table

The intent classifier and the boundary router are a single component. The output of classification is directly consumed as a routing decision.

| Intent | Route | Phase 5 pipeline components used |
|---|---|---|
| `rfq_specific` | → Stage/Role resolution → ToolController → ContextBuilder → LLM → Output guardrail | Full Phase 5 pipeline |
| `general_knowledge` | → Role resolution (no stage) → ContextBuilder → LLM → Output guardrail | Role framing applies; stage framing skipped |
| `unsupported` | → Phase 5 `get_capability_status` path (dispatch, not replacement) | Existing Phase 5 capability-status mechanism |
| `disambiguation` | → Disambiguation controller → ContextBuilder → LLM → Output guardrail | New disambiguation controller |
| `conversational` | → ContextBuilder → LLM | Minimal framing, no retrieval, no guardrail enforcement |

### B.2 Role framing outside `rfq_specific`

Role framing from Phase 5 **remains active** for `general_knowledge` turns. An executive asking "what is PWHT?" should get a summary-level answer; an estimation lead should get a technical answer. Stage framing is skipped for `general_knowledge` because stage context is irrelevant to domain knowledge.

For `conversational` turns, role framing may apply (the session still has a role). Stage framing is always skipped.

For `disambiguation` turns, role framing may apply to the clarification prompt style.

### B.3 Phase 5 capability-status dispatch

The Phase 6 intent classifier dispatches `unsupported` turns to the existing Phase 5 `get_capability_status` path. Phase 5's `ToolController._match_capability_status` and `_build_capability_status_record` remain unchanged. The classifier routes to them; it does not replace them.

This preserves working Phase 5 code and minimizes regression risk.

### B.4 Interaction with the Phase 5 tool planner

After the intent router classifies a turn as `rfq_specific`, the turn proceeds to the Phase 5 tool planner (keyword matching → stage/role gating → intersection rule). The tool planner may produce "no match" (no retrieval) even when intent is `rfq_specific`.

**This is handled by the output guardrail (M6.2), not by the classifier.** The intent router's classification is advisory to the grounding policy: it says "this turn is about an RFQ and therefore needs grounding." If the tool planner can't find a tool to call, the turn proceeds without retrieval, and the output guardrail detects the grounding gap and triggers graceful degradation.

The intent classifier does not force tool selection, does not override the planner, and does not downgrade its own classification based on planner results. Intent and tool selection are separate concerns.

### B.5 What the router does *not* do

- No LLM classification.
- No multi-intent classification (exactly one intent per turn).
- No confidence scoring on classification.
- No tool selection (that remains the Phase 5 planner's job).
- No schema change to any existing route or DTO.

---

## 4. Decision Set C — Grounding guardrail (M6.2)

### C.1 Per-intent grounding policy

Grounding is not a global setting. It is enforced per intent:

| Intent | Grounding rule | What happens when evidence is missing |
|---|---|---|
| `rfq_specific` | **REQUIRED** — response must be backed by tool evidence (`source_refs` non-empty) | Degrade to honest absence; do not let LLM answer freely about RFQ data |
| `general_knowledge` | **NOT REQUIRED** — LLM may answer directly from training knowledge | N/A |
| `conversational` | **NOT REQUIRED** — LLM may answer directly | N/A |
| `unsupported` | **NOT APPLICABLE** — routed to capability-status, no generation | N/A |
| `disambiguation` | **BLOCK ANSWER** — do not generate a factual response; generate a clarification prompt | N/A |

### C.2 Critical grounding rule

If intent is `rfq_specific` AND no valid tool evidence exists after the tool planner runs, the system **must not let the LLM generate a free-form RFQ-specific response**. Instead:

- The grounding guardrail injects an absence framing directive into the prompt, similar to Phase 5 capability-status absence behavior.
- The LLM is instructed to say it does not have grounded facts for the specific question and to suggest what it *can* answer.
- No RFQ-specific factual claims may appear in the response without backing evidence.

This is the architectural answer to "how do you prevent hallucination about real RFQ data?" and it is enforced by pipeline control, not by prompt engineering alone.

### C.3 Grounding enforcement scenarios

Three scenarios the guardrail must handle:

**Scenario 1: Tool retrieval succeeded, `source_refs` present.**
→ Pass through. The response is grounded. Phase 5 confidence rendering applies normally.

**Scenario 2: Tool retrieval was attempted but failed (503/504/timeout).**
→ The turn has no tool evidence. The grounding guardrail injects absence framing. The LLM produces an honest degradation response ("I couldn't retrieve the data right now; please try again"). This replaces whatever the LLM would have hallucinated.

**Scenario 3: Intent classified as `rfq_specific` but tool planner found no matching tool.**
→ The intent layer says "this is about an RFQ" but the planner says "I don't know which tool to call." The grounding guardrail injects absence framing. This is logged as a grounding mismatch (`phase6.grounding_mismatch=true`) for debugging and future classifier improvement.

### C.4 What the grounding guardrail does *not* do

- No semantic hallucination detection (checking whether the LLM invented a specific dollar amount). That requires an LLM-as-judge step and is Phase 7+.
- No response rewriting or post-processing. The guardrail works by shaping the prompt *before* generation, not by editing the response *after* generation.
- No tool selection override. The guardrail does not force the planner to call a specific tool.

---

## 5. Decision Set D — Disambiguation (M6.3)

### D.1 Scope

Phase 6 disambiguation handles **RFQ-resolution ambiguity only**: the user's question references an RFQ but the system cannot identify which one.

Examples of what Phase 6 disambiguation handles:

- "What's the status?" in a portfolio session (no bound RFQ).
- "Tell me about that project" without context.
- "The last one I was working on" without session history to resolve it.

Examples of what Phase 6 disambiguation does **not** handle:

- "How many RFQs are overdue?" → `unsupported` (requires portfolio tools that don't exist).
- "Compare RFQ-01 and RFQ-02" → `unsupported` (requires multi-RFQ tools).
- "Show me all open RFQs" → `unsupported` (requires listing tools).

### D.2 Disambiguation trigger

`disambiguation` intent fires when:

- The session is **not** RFQ-bound (mode is `portfolio`).
- AND the user's turn contains RFQ-referencing language (same patterns that would trigger `rfq_specific` in a bound session).

If the session **is** RFQ-bound, the same language resolves to `rfq_specific` because the target RFQ is known.

### D.3 Disambiguation response

When intent is `disambiguation`, the chatbot generates a clarification prompt asking the user to identify which RFQ they mean. The response is a plain assistant message inside the existing `TurnResponse.content`:

```
Which RFQ are you referring to? You can provide the RFQ code (e.g., IF-25144)
or bind this session to a specific RFQ.
```

The response follows the brief's three-tier pattern:

- **Low ambiguity** (session has recent RFQ context in history): auto-pick with stated assumption.
- **Medium ambiguity** (user said "this RFQ" without context): suggest and confirm.
- **High ambiguity** (no context at all): ask for identification.

For Phase 6, all three tiers are handled through prompt instructions, not through separate code paths. The `ContextBuilder` receives the disambiguation signal and instructs the LLM to produce the appropriate clarification level.

### D.4 Cross-turn disambiguation resolution

Disambiguation resolution is **stateless** — no new DB columns, no pending-disambiguation state machine.

The protocol: if the last assistant message in the conversation was a disambiguation prompt (detectable by the presence of a pattern like "which RFQ" in the content), and the current user turn is short and looks like a selector (e.g., "RFQ-01", "the first one", "IF-25144"), the classifier treats the current turn as a disambiguation resolution rather than re-classifying from scratch.

On resolution: the chatbot extracts the identified RFQ reference from the user's response and proceeds as if the session were contextually bound to that RFQ for this turn. The session's persisted `rfq_id` does **not** change (no implicit binding). The RFQ reference is request-scoped only.

### D.5 Disambiguation abandonment

If the user's response to a disambiguation prompt does **not** match any offered option and is not a short selector (e.g., "actually, never mind — what is PWHT?"), the classifier re-classifies the turn from scratch using the normal intent classification path. The disambiguation context is abandoned. The system does not get stuck in a disambiguation loop.

### D.6 What disambiguation does *not* do

- No implicit session binding. Disambiguation resolution is request-scoped. The session's `rfq_id` does not change.
- No portfolio search. The chatbot cannot list available RFQs to offer choices (that requires tools that don't exist).
- No multi-RFQ resolution. One RFQ per disambiguation prompt.
- No new response DTO. Disambiguation stays inside `TurnResponse.content`.

---

## 6. Decision Set E — Output guardrail (M6.4)

### E.1 Mechanism

The output guardrail is **structural, not semantic**. It checks structural properties of the response after generation, not whether the LLM's claims are factually correct.

### E.2 Structural checks

Three checks, each tied to an intent:

**Check 1: Grounding check (intent = `rfq_specific`).**
If the intent was `rfq_specific` and the persisted assistant message has empty `source_refs` and no grounding-gap absence framing was injected → log `phase6.output_guardrail_result=grounding_violation`.

**Check 2: Disambiguation shape check (intent = `disambiguation`).**
If the intent was `disambiguation` and the response does not contain a clarification pattern (heuristic: contains "?" or "which" or "RFQ") → log `phase6.output_guardrail_result=disambiguation_shape_violation`.

**Check 3: Unsupported routing check (intent = `unsupported`).**
If the intent was `unsupported` and the response does not follow the Phase 5 absence template (heuristic: contains the capability name from the capability-status entry) → log `phase6.output_guardrail_result=unsupported_routing_violation`.

### E.3 Enforcement posture

Phase 6 output guardrails are **soft enforcement**: log and pass through. The guardrail logs the violation type but does not reject or replace the response.

Rationale: hard enforcement (reject and replace with a canned response) risks rejecting valid responses that happen to not match the structural pattern. Soft enforcement collects data for Phase 7 to tighten enforcement rules based on observed violation patterns.

### E.4 What the output guardrail does *not* do

- No semantic hallucination detection (did the LLM invent a dollar amount?). Phase 7+.
- No response rewriting or injection. The guardrail observes and logs; it does not modify.
- No retry-on-failure loop. If the guardrail detects a violation, it logs and passes through. No second LLM call.

---

## 7. Decision Set F — Pipeline integration

### F.1 Updated pipeline

The Phase 6 pipeline extends the Phase 5 pipeline with a new control entry point:

```
1. Load session (existing)
2. Get-or-create conversation (existing)
3. Classify intent (NEW — Phase 6)
4. Route by intent:
   ├─ rfq_specific:
   │   5a. Resolve stage (Phase 5)
   │   5b. Resolve role (Phase 5)
   │   5c. ToolController.maybe_execute_retrieval (Phase 5)
   │   5d. Grounding check — if no evidence, inject absence framing (NEW — Phase 6)
   │   5e. ContextBuilder.build (Phase 5, with grounding signal)
   │   5f. Azure OpenAI call
   │   5g. Output guardrail — grounding check (NEW — Phase 6)
   │
   ├─ general_knowledge:
   │   6a. Resolve role (Phase 5, no stage)
   │   6b. ContextBuilder.build (role framing only)
   │   6c. Azure OpenAI call
   │
   ├─ unsupported:
   │   7a. Dispatch to Phase 5 capability-status path (existing)
   │   7b. ContextBuilder.build (absence template)
   │   7c. Azure OpenAI call
   │   7d. Output guardrail — unsupported routing check (NEW)
   │
   ├─ disambiguation:
   │   8a. Resolve role (for clarification style)
   │   8b. ContextBuilder.build (disambiguation prompt directive)
   │   8c. Azure OpenAI call
   │   8d. Output guardrail — disambiguation shape check (NEW)
   │
   └─ conversational:
       9a. ContextBuilder.build (minimal framing)
       9b. Azure OpenAI call

10. Persist assistant message (existing)
11. Return TurnResponse (existing)
```

### F.2 Pipeline invariants

- Intent classification runs **once per turn, before everything else**. The result is immutable for the rest of the turn.
- Stage and role resolution run **only when their route requires them**. Not every turn pays the stage-resolution latency cost.
- The tool planner runs **only for `rfq_specific` turns**. `general_knowledge`, `conversational`, and `disambiguation` turns never invoke the planner.
- The output guardrail runs **after the LLM call, before persistence** (except for `conversational`, which has no guardrail). Conversational responses are not subject to grounding or output guardrail checks because they carry no RFQ-specific claims and no evidence policy applies.
- All Phase 5 log fields continue to emit alongside Phase 6 fields.

### F.2.1 Latency impact

Phase 6 adds negligible latency (< 5–10 ms per turn) because the intent classifier, boundary router, and output guardrail are all deterministic in-process operations with no additional network calls. The only network calls in the pipeline remain the existing Phase 5 upstream calls (manager, intelligence, Azure OpenAI), which Phase 6 does not increase — and in fact reduces for non-`rfq_specific` turns by skipping stage resolution and tool planner calls entirely.

### F.3 Disambiguation-resolution detection

Before running the normal intent classifier, the pipeline checks whether the current turn is a **disambiguation resolution**:

1. Load the last assistant message from the conversation.
2. If the last assistant message contains a disambiguation pattern (e.g., "which RFQ") AND the current user turn is short (heuristic: fewer than a threshold word count, e.g., ≤ 10 words) AND contains an RFQ-like reference (e.g., matches an RFQ-code pattern or contains "RFQ"):
   - Treat the turn as a disambiguation resolution.
   - Extract the RFQ reference from the user's turn.
   - Re-classify as `rfq_specific` with the extracted RFQ reference as request-scoped context.
   - Proceed through the `rfq_specific` pipeline path.
3. If the conditions are not met, run the normal intent classifier.

This check runs **before** the intent classifier and short-circuits it when disambiguation resolution is detected.

---

## 8. Decision Set G — Observability

### G.1 Mechanism

Structured logs only. No new HTTP response fields. No new DTO properties. Same posture as Phase 5.

### G.2 Required log fields

Phase 6 extends the Phase 5 log fields. All Phase 5 `phase5.*` fields remain and continue emitting. Phase 6 adds the following fields, in pipeline execution order:

| Field | When emitted | Value |
|---|---|---|
| `phase6.intent_classified` | After intent classification | The classified intent: `rfq_specific`, `general_knowledge`, `unsupported`, `disambiguation`, `conversational` |
| `phase6.route_selected` | After boundary routing | The route taken: `tools_pipeline`, `direct_llm`, `capability_status`, `disambiguation`, `conversational` |
| `phase6.disambiguation_triggered` | When disambiguation intent fires | `true`; otherwise field absent |
| `phase6.disambiguation_resolved` | When a prior disambiguation is resolved | `true` + the extracted RFQ reference; otherwise field absent |
| `phase6.disambiguation_abandoned` | When disambiguation is abandoned | `true`; otherwise field absent |
| `phase6.grounding_required` | After intent classification for `rfq_specific` | `true` for `rfq_specific`, `false` otherwise |
| `phase6.grounding_satisfied` | After tool planner + evidence check | `true` if `source_refs` will be non-empty, `false` otherwise |
| `phase6.grounding_mismatch` | When intent is `rfq_specific` but tool planner found no tool | `true`; otherwise field absent |
| `phase6.grounding_gap_absence_injected` | When grounding gap triggers absence framing | `true`; otherwise field absent |
| `phase6.output_guardrail_result` | After output guardrail | `pass`, `grounding_violation`, `disambiguation_shape_violation`, or `unsupported_routing_violation` |

### G.3 Log format

Same as Phase 5: key-value pairs in the existing logging framework via `extra` dict. No dedicated log stream. Phase 6 fields coexist with Phase 5 fields on every turn log.

---

## 9. Decision Set H — Contract posture

### H.1 No contract change

Phase 6 is contract-stable:

- No new endpoints.
- No new DTOs.
- No new response shapes.
- No new error codes for Phase 6-specific failures.
- Disambiguation responses are plain assistant messages inside `TurnResponse.content`.

### H.2 Verification

`PromptEnvelope` Pydantic class remains byte-identical to Phase 4/5. OpenAPI YAML requires no changes. All existing Phase 4 and Phase 5 demo beats must continue to pass unchanged.

---

## 10. Decision Set I — Mode B behavior

### I.1 What Phase 6 adds to Mode B

Phase 6 makes Mode B (portfolio/global sessions) genuinely useful:

- `general_knowledge` intent → LLM answers domain questions directly (no tools needed).
- `disambiguation` intent → chatbot asks which RFQ the user means.
- `unsupported` intent → honest absence via existing capability-status path.
- `conversational` intent → normal conversational responses.

### I.2 What Mode B still cannot do

- No portfolio analytics ("how many RFQs are overdue?").
- No cross-RFQ aggregation.
- No RFQ listing or browsing.
- No LLM-improvised portfolio answers.

These require portfolio tools that do not exist. They are Phase 7+.

### I.3 Mode B is no longer hard-frozen

Unlike Phase 5 (where Mode B was "no code change permitted"), Phase 6 **intentionally changes Mode B behavior**. The intent router and disambiguation controller both operate on portfolio sessions. This is where the Phase 6 product impact is most visible.

However, Mode B changes must stay within the routes defined in the routing table (§B.1). No new portfolio-specific tools, no new portfolio endpoints, no portfolio-specific DTOs.

---

## 11. Decision Set J — Configuration

### J.1 Intent classifier configuration

Python module: `src/config/intent_patterns.py`.

Declarative mapping from patterns to intents, typed as:

```python
from typing import TypedDict

class IntentPattern(TypedDict):
    keywords: list[str]       # substring-match triggers
    session_context: str      # "rfq_bound", "portfolio", "any"
    intent: str               # one of the 5 intents

INTENT_PATTERNS: list[IntentPattern]
FALLBACK_INTENT: str = "conversational"
```

The pattern list is ordered by precedence (§A.4). The first match wins.

### J.2 Disambiguation configuration

Python module: `src/config/disambiguation_config.py`.

```python
DISAMBIGUATION_DETECTION_PATTERNS: list[str]  # patterns that indicate prior disambiguation prompt
MAX_RESOLUTION_WORD_COUNT: int                # max words to treat as a selector response
RFQ_REFERENCE_PATTERNS: list[str]             # patterns that look like RFQ identifiers
```

Example `RFQ_REFERENCE_PATTERNS` entries: `r"IF-\d+"` (matches `IF-25144`), `r"RFQ-\d+"` (matches `RFQ-01`), UUID format patterns. The implementer should seed these from real GHI/BACAB RFQ code conventions.

### J.3 Grounding gap configuration

Not a separate config module. The grounding gap behavior is hardcoded in the grounding guardrail logic: if `intent == rfq_specific` and `source_refs` is empty after tool planner, inject absence framing. No configuration needed because the rule is fixed.

---

## 12. Decision Set K — Tests and demo acceptance

### K.1 Dual acceptance posture

Same as Phase 5: every named Phase 6 behavior must exist as both a pytest integration test and a scripted demo beat.

### K.2 Required scenarios

**Scenario 1: Intent classification — `rfq_specific` on bound session.**
RFQ-bound session, question about deadline/status. Assert: `phase6.intent_classified=rfq_specific`, `phase6.route_selected=tools_pipeline`, tool planner fires, `source_refs` non-empty, `phase6.output_guardrail_result=pass`.

**Scenario 2: Intent classification — `general_knowledge` on bound session.**
RFQ-bound session, question "what is PWHT?". Assert: `phase6.intent_classified=general_knowledge`, `phase6.route_selected=direct_llm`, no tool planner call, role framing present in prompt, no stage framing.

**Scenario 3: Intent classification — `general_knowledge` on portfolio session.**
Portfolio session, question "how does RT work?". Assert: `phase6.intent_classified=general_knowledge`, `phase6.route_selected=direct_llm`, no tool planner call.

**Scenario 4: Intent classification — `unsupported` via capability-status.**
Any session, question "what's the briefing?". Assert: `phase6.intent_classified=unsupported`, `phase6.route_selected=capability_status`, existing Phase 5 capability-status path fires, HTTP 200 (not 422).

**Scenario 5: Intent classification — `conversational` fallback.**
Any session, greeting "hello copilot". Assert: `phase6.intent_classified=conversational`, `phase6.route_selected=conversational`, no retrieval, no guardrail enforcement.

**Scenario 6: Grounding enforcement — `rfq_specific` with tool success.**
RFQ-bound session, question with matching tool keyword. Assert: `phase6.grounding_required=true`, `phase6.grounding_satisfied=true`, `phase6.output_guardrail_result=pass`.

**Scenario 7: Grounding enforcement — `rfq_specific` with tool failure.**
RFQ-bound session, question with matching tool keyword, manager returns 503. Assert: `phase6.grounding_required=true`, `phase6.grounding_satisfied=false`, `phase6.grounding_gap_absence_injected=true`, response contains honest absence framing.

**Scenario 8: Grounding mismatch — `rfq_specific` but no tool keyword match.**
RFQ-bound session, question that the classifier recognizes as RFQ-specific but the tool planner cannot match to a keyword (e.g., "tell me about the fabrication schedule for this RFQ"). Assert: `phase6.grounding_required=true`, `phase6.grounding_satisfied=false`, `phase6.grounding_mismatch=true`, `phase6.grounding_gap_absence_injected=true`.

**Scenario 9: Disambiguation — trigger.**
Portfolio session, question "what's the status of this RFQ?". Assert: `phase6.intent_classified=disambiguation`, `phase6.disambiguation_triggered=true`, response contains a clarification prompt ("which RFQ").

**Scenario 10: Disambiguation — resolution.**
Following Scenario 9, user responds "IF-25144" or similar. Assert: `phase6.disambiguation_resolved=true`, turn proceeds as `rfq_specific` for the identified RFQ.

**Scenario 11: Disambiguation — abandonment.**
Following Scenario 9, user responds "never mind, what is PWHT?". Assert: `phase6.disambiguation_abandoned=true`, turn re-classified as `general_knowledge`.

**Scenario 12: Output guardrail — soft enforcement logging.**
Trigger the grounding-gap scenario (Scenario 8). Assert: `phase6.grounding_gap_absence_injected=true` and `phase6.output_guardrail_result=pass` appear in logs. Assert: HTTP 200 (response passes through).

**Scenario 13: Phase 5 regression guard.**
All six Phase 5 scenarios from Pack §J.2 still pass unchanged. Phase 5 stage/role/confidence behavior is unaffected by the new control layer.

**Scenario 14: Mode B — general knowledge works.**
Portfolio session, domain question. Assert: receives a helpful answer without tool retrieval, no grounding violation.

### K.3 Out of scope for Phase 6 tests

- No semantic hallucination detection tests (Phase 7+).
- No portfolio analytics tests (tools don't exist).
- No LLM classifier accuracy tests (classifier is deterministic).
- No load or performance tests.

---

## 13. Acceptance criteria — Phase 6 is done when

All of the following are true simultaneously:

1. All fourteen scenarios in §K.2 pass as pytest integration tests in CI.
2. All fourteen scenarios exist as executable Postman demo beats.
3. All ten Phase 6 log fields in §G.2 appear correctly for every applicable turn.
4. All Phase 5 log fields continue to emit alongside Phase 6 fields.
5. `src/config/intent_patterns.py` and `src/config/disambiguation_config.py` exist and are typed.
6. `PromptEnvelope` Pydantic class is byte-identical to Phase 4/5. (Hard contract check.)
7. OpenAPI YAML requires no changes. (Hard contract check.)
8. All six Phase 5 demo beats still pass unchanged. (Regression check.)
9. The implementer can demonstrate all fourteen scenarios live in Postman in a single session.
10. The output guardrail emits structured violation logs for grounding-gap scenarios.

When all ten hold, Phase 6 is done.

---

## 14. Out-of-scope / Phase 7+ fence (restated)

The following remain explicitly out of Phase 6:

- LLM-based intent classification.
- Semantic hallucination detection (LLM-as-judge).
- Hard output guardrail enforcement (reject and replace).
- Multi-agent / A2A patterns.
- Native MCP servers.
- Document RAG expansion.
- Semantic or procedural memory.
- Portfolio analytics tools (listing, filtering, aggregation).
- Proactive subscriptions and notifications.
- What-if sandbox.
- JWT / IAM middleware and request-path authentication.
- Streaming chat and native function-calling.
- Contract redesign (new endpoints, DTOs, response shapes).
- Action guardrails (chatbot remains read-only).
- Multi-RFQ disambiguation.
- Implicit session binding from disambiguation.

This list is exhaustive for Phase 6 scope fencing. Anything in this list appearing in a Phase 6 PR is grounds for rejection.

---

## 15. Handoff to the Blueprint

The Pack locks *what*. The Blueprint will lock *how*, in this expected order:

**M6.1 — Intent + Boundary Router:**
1. Config module (`intent_patterns.py`).
2. Intent classifier controller.
3. Boundary router integration into `ChatController`.
4. Phase 5 capability-status dispatch wiring.

**M6.2 — Grounding Guardrail:**
5. Grounding check logic (pre-LLM absence injection).
6. Grounding gap handling for the mismatch case.
7. `ContextBuilder` extensions for grounding-gap absence directives.

**M6.3 — Disambiguation:**
8. Config module (`disambiguation_config.py`).
9. Disambiguation controller.
10. Cross-turn resolution detection logic.
11. Abandonment detection logic.
12. `ContextBuilder` extensions for disambiguation prompt directives.

**M6.4 — Verification + Close-out:**
13. Output guardrail logic (three structural checks).
14. Observability instrumentation (ten Phase 6 log fields).
15. Pytest integration tests (fourteen scenarios).
16. Postman demo beat extensions.
17. Documentation updates (CLAUDE.md, README).

This order ensures each milestone builds on the prior one. M6.1 must be green before M6.2 begins. The correctness-critical intent classifier lands first because everything downstream depends on it.

---

**End of Implementation Pack v1.0.**

**Ready for Blueprint on request.**
