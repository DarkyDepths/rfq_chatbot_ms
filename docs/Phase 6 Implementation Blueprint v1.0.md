# Phase 6 — Implementation Blueprint v1.0

**Pair:** Execution plan for `rfq_chatbot_ms` Phase 6 — Implementation Pack v1.0
**Posture:** File-by-file sequence. Each step is independently reviewable and independently testable.
**Scope discipline:** This Blueprint adds *no* decisions beyond the Pack. Where the Pack is silent, the Blueprint defers (not invents).
**Acceptance:** Blueprint is complete when all ten criteria in Pack §13 hold.

---

## 0. How to read this Blueprint

Each step names:

- **Files** — create vs modify, with path.
- **Responsibilities** — what the file/code must do, sourced from Pack decisions.
- **Dependencies** — which prior steps must be green before starting.
- **Tests to add in this step** — unit-level where possible, integration-level only where unavoidable.
- **Review checkpoint** — the specific invariants a reviewer must confirm before merging.
- **Pack references** — which Pack sections govern this step.

Steps are numbered and must be executed in order. A step may only ship if all prior steps are merged to main and green. No parallel work on later steps.

Every step ends with a working, shippable codebase. If a step cannot end in that state, it's the wrong step and must be split.

---

## Milestone M6.1 — Intent + Boundary Router

---

## Step 1 — Configuration modules

### 1.1 Files

- **Create** `src/config/intent_patterns.py`
- **Create** `src/config/disambiguation_config.py`

### 1.2 Responsibilities

**`src/config/intent_patterns.py`** (Pack §A, §J.1)

Defines the deterministic intent classification configuration:

```python
from typing import TypedDict

class IntentPattern(TypedDict):
    keywords: list[str]
    session_context: str       # "rfq_bound", "portfolio", "any"
    intent: str                # one of: rfq_specific, general_knowledge,
                               # unsupported, disambiguation, conversational

INTENT_PATTERNS: list[IntentPattern]
FALLBACK_INTENT: str = "conversational"
```

The `INTENT_PATTERNS` list must be ordered by precedence (Pack §A.4):

1. `unsupported` patterns first (capability-status keywords always win).
2. `disambiguation` patterns second (ambiguous RFQ reference in non-bound session).
3. `rfq_specific` patterns third (RFQ-referencing language in bound session or explicit RFQ reference).
4. `general_knowledge` patterns fourth (domain vocabulary without RFQ reference).
5. `conversational` is the fallback, not a pattern entry — handled by `FALLBACK_INTENT`.

The `unsupported` patterns must be the **exact same keyword set** as `CAPABILITY_STATUS_ENTRIES` in `src/config/capability_status.py`. The implementer must not maintain two divergent lists. The recommended approach: import `CAPABILITY_STATUS_ENTRIES` and derive the `unsupported` pattern entries from its keys programmatically.

The `rfq_specific` patterns must encode the RFQ-bound session bias rule from Pack §A.3: in an `rfq_bound` session, domain-adjacent vocabulary (deadline, owner, status, stage, cost, client, priority) should trigger `rfq_specific`, not `general_knowledge`.

The `general_knowledge` patterns should include definitional signals: "what is", "how does", "explain", "typical", "in general", "standard".

The `disambiguation` patterns must include RFQ-referencing language (e.g., "this rfq", "the project", "that rfq") with a `session_context` of `"portfolio"` to ensure they fire only in non-RFQ-bound sessions.

No class-based abstraction, no registry, no loader. Plain module-level constants.

**`src/config/disambiguation_config.py`** (Pack §D, §J.2)

Defines:

```python
DISAMBIGUATION_DETECTION_PATTERNS: list[str] = [
    "which rfq",
    "which project",
    "are you referring to",
]

MAX_RESOLUTION_WORD_COUNT: int = 10

RFQ_REFERENCE_PATTERNS: list[str] = [
    r"IF-\d+",
    r"RFQ-\d+",
    # UUID pattern for downstream RFQ ids
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
]
```

The `DISAMBIGUATION_DETECTION_PATTERNS` are lowercased substring patterns matched against the previous assistant message content to detect an active disambiguation prompt.

The `RFQ_REFERENCE_PATTERNS` are regex patterns matched against the user's response to extract an RFQ reference. These should be seeded from real GHI/BACAB RFQ code conventions.

### 1.3 Dependencies

None. This is the foundation step.

### 1.4 Tests to add

- **Create** `tests/unit/config/test_intent_patterns.py`
  - Assert `FALLBACK_INTENT == "conversational"`.
  - Assert the set of intents used across all `INTENT_PATTERNS` entries is a subset of `{"rfq_specific", "general_knowledge", "unsupported", "disambiguation", "conversational"}`.
  - Assert no intent outside the 5-intent taxonomy appears.
  - Assert `unsupported` patterns appear before `rfq_specific` patterns in the list (precedence order).
  - Assert every `unsupported` pattern keyword exists in `CAPABILITY_STATUS_ENTRIES.keys()` (no divergence).
- **Create** `tests/unit/config/test_disambiguation_config.py`
  - Assert `DISAMBIGUATION_DETECTION_PATTERNS` is non-empty.
  - Assert `MAX_RESOLUTION_WORD_COUNT > 0`.
  - Assert `RFQ_REFERENCE_PATTERNS` is non-empty.
  - Assert each entry in `RFQ_REFERENCE_PATTERNS` is a valid regex.

### 1.5 Review checkpoint

- No YAML files, no DB migrations, no admin endpoints.
- Module-level constants only.
- `unsupported` keyword set derived from or validated against `CAPABILITY_STATUS_ENTRIES`.
- Precedence order is correct in the list.
- Tests green.

### 1.6 Pack references

§A.1–A.4, §D.2, §J.1, §J.2.

---

## Step 2 — Intent classifier controller

### 2.1 Files

- **Create** `src/controllers/intent_controller.py`

### 2.2 Responsibilities

Defines `IntentController`. Single public method:

```python
def classify_intent(
    self,
    user_content: str,
    session: ChatbotSession,
    last_assistant_content: str | None,
) -> IntentClassification:
```

**`IntentClassification`** is a small frozen dataclass:

```python
@dataclass(frozen=True)
class IntentClassification:
    intent: str                         # one of the 5 intents
    disambiguation_resolved: bool       # True if this turn resolved a prior disambiguation
    resolved_rfq_reference: str | None  # extracted RFQ ref if disambiguation resolved
    disambiguation_abandoned: bool      # True if user abandoned disambiguation
```

**Classification sequence** (Pack §A.4, §F.3):

1. **Disambiguation resolution check** (runs first, before normal classification):
   - If `last_assistant_content` is not None AND matches any `DISAMBIGUATION_DETECTION_PATTERNS` (lowercased substring match):
     - AND `user_content` word count ≤ `MAX_RESOLUTION_WORD_COUNT`:
       - AND `user_content` matches any `RFQ_REFERENCE_PATTERNS` regex:
         - Return `IntentClassification(intent="rfq_specific", disambiguation_resolved=True, resolved_rfq_reference=<extracted>, disambiguation_abandoned=False)`.
       - ELSE (short response but no RFQ reference):
         - Treat as possible resolution attempt; fall through to normal classification. If normal classification produces `conversational` or `general_knowledge`, set `disambiguation_abandoned=True`.
     - AND `user_content` word count > `MAX_RESOLUTION_WORD_COUNT`:
       - User clearly moved on. Run normal classification with `disambiguation_abandoned=True`.
   - If `last_assistant_content` does not match disambiguation patterns, proceed to normal classification.

2. **Normal classification** (Pack §A.4 precedence):
   - Normalize `user_content` to lowercase, stripped.
   - Check `unsupported` keywords first (from `INTENT_PATTERNS` entries where `intent == "unsupported"`). If any keyword matches → return `unsupported`.
   - Check `disambiguation` patterns (entries where `intent == "disambiguation"` and `session_context` matches session mode). Only fires when session is not `rfq_bound`. If matches → return `disambiguation`.
   - Check `rfq_specific` patterns (entries where `intent == "rfq_specific"`). In `rfq_bound` sessions, domain vocabulary triggers this. If matches → return `rfq_specific`.
   - Check `general_knowledge` patterns (entries where `intent == "general_knowledge"`). If matches → return `general_knowledge`.
   - Default: return `FALLBACK_INTENT` ("conversational").

The controller is stateless — no constructor dependencies, no connectors, no DB access. Pure in-process classification.

### 2.3 Dependencies

- Step 1 complete (`intent_patterns.py`, `disambiguation_config.py` exist).

### 2.4 Tests to add

- **Create** `tests/unit/controllers/test_intent_controller.py`

  **Precedence tests:**
  - `unsupported` keyword wins over `rfq_specific` keyword when both match (e.g., "what's the briefing deadline?" → `unsupported`, not `rfq_specific`).
  - `disambiguation` fires for RFQ-referencing language in portfolio session.
  - `disambiguation` does NOT fire for same language in RFQ-bound session (→ `rfq_specific` instead).

  **Classification tests by intent:**
  - "what is PWHT?" in portfolio session → `general_knowledge`.
  - "what is PWHT?" in RFQ-bound session → `general_knowledge` (domain definition, not RFQ-specific).
  - "what's the deadline?" in RFQ-bound session → `rfq_specific`.
  - "what's the deadline?" in portfolio session → `disambiguation`.
  - "hello copilot" in any session → `conversational`.
  - "what's the briefing?" in any session → `unsupported`.
  - "tell me about this RFQ" in portfolio session → `disambiguation`.
  - "tell me about this RFQ" in RFQ-bound session → `rfq_specific`.
  - Random unrecognized text → `conversational`.

  **Disambiguation resolution tests:**
  - Last assistant was "Which RFQ are you referring to?", user says "IF-25144" → `rfq_specific`, `disambiguation_resolved=True`, `resolved_rfq_reference` contains `"IF-25144"`.
  - Last assistant was "Which RFQ are you referring to?", user says "never mind, what is PWHT?" → re-classified as `general_knowledge`, `disambiguation_abandoned=True`.
  - Last assistant was "Which RFQ are you referring to?", user says "hello" → `conversational`, `disambiguation_abandoned=True`.
  - Last assistant was NOT a disambiguation prompt → normal classification, `disambiguation_resolved=False`, `disambiguation_abandoned=False`.

  **Edge cases:**
  - Empty user content → `conversational`.
  - Whitespace-only user content → `conversational`.

### 2.5 Review checkpoint

- Classifier is deterministic: same inputs always produce same output.
- No LLM calls, no network calls, no DB access.
- Precedence order matches Pack §A.4.
- `disambiguation` only fires for non-RFQ-bound sessions.
- `IntentClassification` exposes all four fields needed by downstream pipeline steps.
- Tests green.

### 2.6 Pack references

§A.1–A.4, §D.2–D.5, §F.3.

---

## Step 3 — Boundary router and ChatController rewiring

### 3.1 Files

- **Modify** `src/controllers/chat_controller.py`
- **Modify** `src/app_context.py`

### 3.2 Responsibilities

This step wires the intent classifier into `ChatController.handle_turn` and implements the boundary routing table from Pack §B.1.

**3.2.a — Update `ChatController.__init__`**

Add `IntentController` as a new constructor dependency. Inject it via `app_context.py` following the existing `Depends` pattern.

**3.2.b — Update `handle_turn` to the Pack §F.1 pipeline**

The new pipeline sequence:

```python
def handle_turn(self, session_id, command):
    # 1. Load session (existing)
    session = ...

    # 2. Get-or-create conversation (existing)
    conversation = ...

    # 3. Classify intent (NEW)
    last_assistant_content = self._get_last_assistant_content(conversation.id)
    intent_result = self.intent_controller.classify_intent(
        user_content=command.content,
        session=session,
        last_assistant_content=last_assistant_content,
    )
    # Log Phase 6 fields
    log("phase6.intent_classified", intent_result.intent)
    log("phase6.route_selected", self._intent_to_route(intent_result.intent))
    if intent_result.disambiguation_resolved:
        log("phase6.disambiguation_resolved", intent_result.resolved_rfq_reference)
    if intent_result.disambiguation_abandoned:
        log("phase6.disambiguation_abandoned", True)

    # 4. Route by intent
    if intent_result.intent == "rfq_specific":
        return self._handle_rfq_specific(session, conversation, command, intent_result)
    elif intent_result.intent == "general_knowledge":
        return self._handle_general_knowledge(session, conversation, command)
    elif intent_result.intent == "unsupported":
        return self._handle_unsupported(session, conversation, command)
    elif intent_result.intent == "disambiguation":
        return self._handle_disambiguation(session, conversation, command)
    else:  # conversational
        return self._handle_conversational(session, conversation, command)
```

**3.2.c — Implement route handler methods**

Each route handler encapsulates the pipeline path from Pack §F.1:

**`_handle_rfq_specific`**: Full Phase 5 pipeline — stage resolution → role resolution → tool planner → grounding check (Step 5) → context builder → LLM → output guardrail (Step 10) → persist. This is the existing Phase 5 `handle_turn` body, extracted into a method. If `intent_result.disambiguation_resolved` is True, use `intent_result.resolved_rfq_reference` as request-scoped RFQ context (not modifying the session's persisted `rfq_id`).

**`_handle_general_knowledge`**: Role resolution (no stage) → context builder (role framing only, no stage framing, no retrieval) → LLM → persist. No tool planner call. No output guardrail enforcement.

**`_handle_unsupported`**: Dispatch to Phase 5 capability-status path. Call `ToolController.maybe_execute_retrieval` which already handles capability-status internally. Then → context builder → LLM → output guardrail (unsupported check, Step 10) → persist. This path is almost identical to the existing Phase 5 behavior for unsupported keywords.

**`_handle_disambiguation`**: Role resolution (for clarification style) → context builder (disambiguation prompt directive) → LLM → output guardrail (disambiguation shape check, Step 10) → persist. Log `phase6.disambiguation_triggered=true`.

**`_handle_conversational`**: Context builder (minimal framing) → LLM → persist. No retrieval, no guardrails. Fastest path.

**3.2.d — Add `_get_last_assistant_content` helper**

Fetch the most recent assistant message content from the conversation for disambiguation-resolution detection. Uses the existing `ConversationController.get_recent_history` with `limit=1`, filtered to role=assistant. Returns `None` if no assistant message exists.

**3.2.e — Update `app_context.py`**

```python
def get_intent_controller() -> IntentController:
    return IntentController()

def get_chat_controller(..., intent_controller=Depends(get_intent_controller)):
    return ChatController(..., intent_controller=intent_controller)
```

### 3.3 Dependencies

- Step 2 complete (`IntentController` exists).

### 3.4 Tests to add

- **Modify** `tests/unit/test_chat_controller.py`
  - Existing Phase 5 tests must continue passing. `ChatController` constructor now takes `intent_controller` as an additional argument; update test factories accordingly.

- **Create** `tests/integration/test_intent_routing.py`
  - `rfq_specific` route: RFQ-bound session, question about deadline → `phase6.intent_classified=rfq_specific`, `phase6.route_selected=tools_pipeline`, tool planner fires.
  - `general_knowledge` route: RFQ-bound session, "what is PWHT?" → `phase6.intent_classified=general_knowledge`, `phase6.route_selected=direct_llm`, no tool planner call, role framing present, no stage framing.
  - `unsupported` route: any session, "what's the briefing?" → `phase6.intent_classified=unsupported`, `phase6.route_selected=capability_status`, Phase 5 capability-status path fires.
  - `disambiguation` route: portfolio session, "what's the status of this RFQ?" → `phase6.intent_classified=disambiguation`, `phase6.route_selected=disambiguation`.
  - `conversational` route: any session, "hello" → `phase6.intent_classified=conversational`, `phase6.route_selected=conversational`, no retrieval.
  - `general_knowledge` on portfolio session: "how does RT work?" → `phase6.intent_classified=general_knowledge`, no tool planner.

### 3.5 Review checkpoint

- `handle_turn` executes intent classification **before** any Phase 5 logic.
- Each route handler calls only the pipeline components it needs (per Pack §F.1 diagram).
- `_handle_rfq_specific` contains the full Phase 5 pipeline (extracted, not rewritten).
- `_handle_general_knowledge` applies role framing but skips stage resolution and tool planner.
- `_handle_unsupported` dispatches to existing Phase 5 capability-status mechanism.
- `_handle_conversational` has no guardrail checks.
- Phase 5 log fields (`phase5.*`) still emit for `rfq_specific` turns.
- Phase 6 log fields (`phase6.intent_classified`, `phase6.route_selected`) emit for all turns.
- Existing Phase 5 tests pass with the new constructor signature.
- Intent classification and boundary routing add negligible latency (< 10 ms) since they are in-process and deterministic with no additional network calls. For `general_knowledge` and `conversational` routes, total turn latency may decrease relative to Phase 5 because stage resolution and tool planner calls are skipped entirely.
- Tests green.

### 3.6 Pack references

§B.1–B.5, §F.1–F.3, §G.2, §H.1.

---

## Milestone M6.2 — Grounding Guardrail

---

## Step 4 — ContextBuilder extensions for grounding-gap absence

### 4.1 Files

- **Modify** `src/controllers/context_builder.py`

### 4.2 Responsibilities

Extend `ContextBuilder.build` to accept a new signal: `grounding_gap: bool`.

When `grounding_gap=True`, the stable prefix includes a grounding-gap absence directive:

```
Grounding behavior: grounding gap mode.
The user asked an RFQ-specific question but no grounded tool evidence is available.
Do not generate any RFQ-specific factual claims. Instead, respond honestly:
state that you cannot retrieve the requested information right now,
and suggest what you can help with or ask the user to rephrase.
Do not append any confidence marker line for this response mode.
```

This directive sits alongside the existing Phase 5 confidence and capability-status directives. The logic in `_build_confidence_directives` (or a new parallel method) gains a third mode:

- `capability_status_hit is not None` → capability-status absence (existing Phase 5).
- `grounding_gap=True` → grounding-gap absence (new Phase 6).
- `any_pattern_based_tool_fired=True` → pattern-based marker (existing Phase 5).
- Default → deterministic mode, no marker (existing Phase 5).

Precedence: `capability_status_hit` > `grounding_gap` > `any_pattern_based_tool_fired` > default. Only one directive mode is active per turn.

### 4.3 Dependencies

- Step 3 complete (routing is wired, `_handle_rfq_specific` exists as a callable path).

### 4.4 Tests to add

- **Modify** `tests/unit/controllers/test_context_builder.py`
  - `grounding_gap=True` → stable prefix contains "grounding gap mode" directive and "cannot retrieve" instruction.
  - `grounding_gap=True` → stable prefix does NOT contain the confidence pattern marker.
  - `grounding_gap=False` with pattern-based tool → existing Phase 5 marker behavior unchanged.
  - `capability_status_hit` takes precedence over `grounding_gap=True`.

### 4.5 Review checkpoint

- `PromptEnvelope` public shape unchanged (no new fields).
- Grounding-gap directive appears only when `grounding_gap=True`.
- Precedence among the four directive modes is correct and tested.
- Tests green.

### 4.6 Pack references

§C.2, §C.3 (Scenario 2 and 3), §C.4.

---

## Step 5 — Grounding check logic in the `rfq_specific` route

### 5.1 Files

- **Modify** `src/controllers/chat_controller.py`

### 5.2 Responsibilities

In `_handle_rfq_specific`, after the tool planner runs and before `ContextBuilder.build`, add the grounding check:

```python
# After tool planner
tool_call_records = self.tool_controller.maybe_execute_retrieval(...)

# Grounding check
has_evidence = any(
    record.result is not None
    and record.result.confidence != ConfidenceLevel.ABSENT
    and record.result.source_ref is not None
    for record in tool_call_records
)
grounding_gap = not has_evidence
tool_planner_fired = len(tool_call_records) > 0

log("phase6.grounding_required", True)
log("phase6.grounding_satisfied", has_evidence)
if grounding_gap:
    if not tool_planner_fired:
        log("phase6.grounding_mismatch", True)   # intent said rfq_specific but planner found no tool
    log("phase6.grounding_gap_absence_injected", True)

# Pass grounding_gap to ContextBuilder
prompt_envelope = self.context_builder.build(
    ...,
    grounding_gap=grounding_gap,
)
```

**Three scenarios handled** (Pack §C.3):

1. **Tool retrieval succeeded** (`has_evidence=True`): `grounding_gap=False`. Normal Phase 5 behavior with confidence rendering.

2. **Tool retrieval attempted but failed** (`tool_call_records` has an entry with a failed/absent result): `has_evidence=False`, `tool_planner_fired=True`. The tool planner did fire; it just didn't produce usable evidence. `grounding_gap=True`. Log `phase6.grounding_gap_absence_injected=true` (but NOT `phase6.grounding_mismatch`, since the planner and classifier agreed — the tool just failed).

3. **Intent was `rfq_specific` but tool planner matched no keyword** (`tool_call_records` is empty): `has_evidence=False`, `tool_planner_fired=False`. `grounding_gap=True`. Log both `phase6.grounding_mismatch=true` (classifier/planner disagreement) and `phase6.grounding_gap_absence_injected=true`.

This differentiation matters for debugging: `grounding_mismatch` means the classifier recognized RFQ intent but the planner had no keyword match (classifier gap). Grounding gap without mismatch means the planner tried but the upstream failed (infrastructure issue). Both produce honest absence, but the log signal is different.

In all grounding-gap cases, the ContextBuilder receives `grounding_gap=True` and injects the absence directive from Step 4.

### 5.3 Dependencies

- Step 4 complete (ContextBuilder accepts `grounding_gap`).

### 5.4 Tests to add

- **Modify** `tests/integration/test_intent_routing.py` (or create `tests/integration/test_grounding.py`)
  - Tool retrieval succeeds → `phase6.grounding_satisfied=true`, no grounding gap, normal response.
  - Manager returns 503 on tool call → `phase6.grounding_satisfied=false`, `phase6.grounding_gap_absence_injected=true`, response contains absence framing.
  - `rfq_specific` intent but no tool keyword match → `phase6.grounding_mismatch=true`, `phase6.grounding_gap_absence_injected=true`.

### 5.5 Review checkpoint

- Grounding check runs **only** in `_handle_rfq_specific`, not in other route handlers.
- `phase6.grounding_required=true` is logged for every `rfq_specific` turn.
- The three scenarios produce distinct and correct log field combinations.
- When `grounding_gap=True`, the LLM receives the absence directive and the response does not contain fabricated RFQ facts.
- Tests green.

### 5.6 Pack references

§C.1–C.4, §F.1 (step 5d), §G.2.

---

## Milestone M6.3 — Disambiguation

---

## Step 6 — Disambiguation controller

### 6.1 Files

- **Create** `src/controllers/disambiguation_controller.py`

### 6.2 Responsibilities

Defines `DisambiguationController`. This controller does not own the classification decision (that's `IntentController`) — it owns the **response assembly** for disambiguation turns.

Single public method:

```python
def build_disambiguation_context(
    self,
    user_content: str,
    role_resolution: RoleResolution,
) -> dict:
```

Returns a context dict consumed by `ContextBuilder` to produce the disambiguation prompt. The dict contains:

- `disambiguation_mode: True`
- `user_question: str` — the original user question that triggered disambiguation.
- `role_profile: RoleProfile` — for tone/depth styling of the clarification prompt.

The controller itself is thin — the real work is in `ContextBuilder` applying the disambiguation prompt directive. The controller exists as a clean separation of concern and as the place where future disambiguation enrichment (e.g., listing recent RFQs) would land.

### 6.3 Dependencies

- Step 3 complete (routing dispatches to `_handle_disambiguation`).

### 6.4 Tests to add

- **Create** `tests/unit/controllers/test_disambiguation_controller.py`
  - `build_disambiguation_context` returns expected fields.
  - Role resolution is passed through correctly.

### 6.5 Review checkpoint

- Controller is stateless. No DB access, no network calls.
- No implicit session binding logic.
- Tests green.

### 6.6 Pack references

§D.1–D.6.

---

## Step 7 — ContextBuilder extensions for disambiguation

### 7.1 Files

- **Modify** `src/controllers/context_builder.py`

### 7.2 Responsibilities

Extend `ContextBuilder.build` to accept a new signal: `disambiguation_context: dict | None`.

When `disambiguation_context` is not None, the stable prefix includes a disambiguation prompt directive:

```
Disambiguation behavior: RFQ resolution mode.
The user asked a question that references an RFQ, but no RFQ is bound to this session.
Generate a clarification response asking the user to identify which RFQ they mean.
You may ask for an RFQ code (e.g., IF-25144, RFQ-01) or suggest the user bind their session.
Do not answer the user's question directly. Ask for clarification only.
```

Role framing is applied from the disambiguation context (for tone/style consistency).

When disambiguation is active, the `variable_suffix` contains the conversation history and the latest user turn but no retrieval blocks (there is no retrieval in the disambiguation path).

### 7.3 Dependencies

- Step 6 complete (disambiguation controller exists).
- Step 4 complete (ContextBuilder extension pattern established).

### 7.4 Tests to add

- **Modify** `tests/unit/controllers/test_context_builder.py`
  - `disambiguation_context` set → stable prefix contains "RFQ resolution mode" directive.
  - `disambiguation_context` set → no retrieval blocks in variable suffix.
  - `disambiguation_context` not set → existing behavior unchanged.

### 7.5 Review checkpoint

- `PromptEnvelope` public shape unchanged.
- Disambiguation directive only appears when `disambiguation_context` is provided.
- Tests green.

### 7.6 Pack references

§D.3, §E.2 (Check 2).

---

## Step 8 — Wire disambiguation into ChatController

### 8.1 Files

- **Modify** `src/controllers/chat_controller.py`
- **Modify** `src/app_context.py`

### 8.2 Responsibilities

**8.2.a — Inject `DisambiguationController` into `ChatController`.**

Add to constructor and `app_context.py` wiring.

**8.2.b — Implement `_handle_disambiguation` fully.**

```python
def _handle_disambiguation(self, session, conversation, command):
    role_resolution = self.role_controller.resolve_role(session)
    # Log Phase 5 role fields
    ...

    disambiguation_context = self.disambiguation_controller.build_disambiguation_context(
        user_content=command.content,
        role_resolution=role_resolution,
    )

    self.conversation_controller.create_user_message(conversation.id, command.content)

    prompt_envelope = self.context_builder.build(
        recent_messages=self.conversation_controller.get_recent_history(...),
        latest_user_turn=command.content,
        role_resolution=role_resolution,
        disambiguation_context=disambiguation_context,
    )

    completion = self.azure_openai_connector.create_chat_completion(
        self._build_azure_messages(prompt_envelope)
    )

    log("phase6.disambiguation_triggered", True)

    # Output guardrail check (Step 10) will be added later
    assistant_message = self.conversation_controller.create_assistant_message(
        conversation.id, completion.assistant_text,
    )
    return to_turn_response(conversation.id, assistant_message)
```

**8.2.c — Handle disambiguation resolution in `_handle_rfq_specific`.**

When `intent_result.disambiguation_resolved` is True, the turn uses `intent_result.resolved_rfq_reference` as request-scoped context. This means:

- Stage resolution receives the resolved RFQ reference (not the session's `rfq_id`, which remains null for portfolio sessions).
- Tool planner uses the resolved reference.
- The session's persisted `rfq_id` does **not** change. No implicit binding.

Implementation: create a request-scoped wrapper or override that provides the resolved RFQ reference to `StageController.resolve_stage` and `ToolController.maybe_execute_retrieval` without modifying the session object.

### 8.3 Dependencies

- Step 6 and 7 complete.
- Step 5 complete (grounding logic exists in `_handle_rfq_specific`).

### 8.4 Tests to add

- **Add to** `tests/integration/test_phase6_scenarios.py` (or create it):
  - **Scenario 9**: Portfolio session → "what's the status of this RFQ?" → `phase6.disambiguation_triggered=true`, response contains clarification prompt.
  - **Scenario 10**: Following Scenario 9, user says "IF-25144" → `phase6.disambiguation_resolved=true`, turn proceeds as `rfq_specific`.
  - **Scenario 11**: Following Scenario 9, user says "never mind, what is PWHT?" → `phase6.disambiguation_abandoned=true`, re-classified as `general_knowledge`.

### 8.5 Review checkpoint

- Disambiguation response is a plain assistant message (no new DTO).
- `resolved_rfq_reference` is request-scoped only; `session.rfq_id` never changes.
- Disambiguation abandonment re-classifies cleanly.
- `phase6.disambiguation_triggered` appears in logs for disambiguation turns.
- Tests green.

### 8.6 Pack references

§D.1–D.6, §F.1 (step 8a–8d), §G.2.

---

## Milestone M6.4 — Verification + Close-out

---

## Step 9 — `_handle_general_knowledge` and `_handle_conversational` finalization

### 9.1 Files

- **Modify** `src/controllers/chat_controller.py`

### 9.2 Responsibilities

Ensure `_handle_general_knowledge` and `_handle_conversational` are fully implemented and tested. These were stubbed or partially implemented in Step 3.

**`_handle_general_knowledge`:**

```python
def _handle_general_knowledge(self, session, conversation, command):
    role_resolution = self.role_controller.resolve_role(session)
    # Log role fields

    recent_messages = self.conversation_controller.get_recent_history(...)
    self.conversation_controller.create_user_message(conversation.id, command.content)

    prompt_envelope = self.context_builder.build(
        recent_messages,
        latest_user_turn=command.content,
        role_resolution=role_resolution,
        # No stage_resolution, no retrieval, no grounding_gap
    )

    completion = self.azure_openai_connector.create_chat_completion(
        self._build_azure_messages(prompt_envelope)
    )

    assistant_message = self.conversation_controller.create_assistant_message(
        conversation.id, completion.assistant_text,
    )
    return to_turn_response(conversation.id, assistant_message)
```

Key property: role framing applies, stage framing does not. No tool planner. No output guardrail.

**`_handle_conversational`:**

Same as `_handle_general_knowledge` but may use even more minimal framing (no role depth directives, just the base system prompt). The ContextBuilder already handles this case when no role/stage signals are provided.

Key property: no guardrail checks. Conversational responses are not subject to grounding or output guardrail checks (Pack §F.2).

### 9.3 Dependencies

- Step 3 complete (route handlers exist).

### 9.4 Tests to add

- **Add to** `tests/integration/test_phase6_scenarios.py`:
  - **Scenario 2**: RFQ-bound session, "what is PWHT?" → `general_knowledge`, role framing present, no stage framing, no retrieval.
  - **Scenario 3**: Portfolio session, "how does RT work?" → `general_knowledge`, no retrieval.
  - **Scenario 5**: "hello copilot" → `conversational`, no retrieval, no guardrail.
  - **Scenario 14**: Portfolio session, domain question → helpful answer, no grounding violation.

### 9.5 Review checkpoint

- `general_knowledge` turns include role framing but no stage framing.
- `conversational` turns have no guardrail enforcement.
- No tool planner calls for either route.
- Tests green.

### 9.6 Pack references

§B.2, §F.1, §F.2.

---

## Step 10 — Output guardrail

### 10.1 Files

- **Create** `src/controllers/output_guardrail.py`
- **Modify** `src/controllers/chat_controller.py`

### 10.2 Responsibilities

**`src/controllers/output_guardrail.py`**

Defines `OutputGuardrail`. Single public method:

```python
def evaluate(
    self,
    intent: str,
    assistant_text: str,
    source_refs: list,
    grounding_gap_injected: bool,
    capability_status_hit: CapabilityStatusHit | None,
) -> str:
    """Return 'pass' or a violation type string."""
```

**Early return for non-guardrailed intents:**

```python
if intent in ["general_knowledge", "conversational"]:
    return "pass"
```

Conversational and general-knowledge responses are not evaluated by the output guardrail — they carry no RFQ-specific claims and no evidence policy applies. This early return ensures no future check is accidentally applied to these intents.

**Three structural checks** (Pack §E.2):

1. **Grounding check** (intent = `rfq_specific`):
   - If `source_refs` is empty AND `grounding_gap_injected` is False → return `"grounding_violation"`.
   - If `grounding_gap_injected` is True → return `"pass"` (absence was handled correctly).
   - Otherwise → return `"pass"`.

2. **Disambiguation shape check** (intent = `disambiguation`):
   - If `assistant_text` does not contain "?" and does not contain (case-insensitive) "which" and does not contain "RFQ" → return `"disambiguation_shape_violation"`.
   - Otherwise → return `"pass"`.

3. **Unsupported routing check** (intent = `unsupported`):
   - If `capability_status_hit` is not None and `capability_status_hit.capability_name` not in `assistant_text` → return `"unsupported_routing_violation"`.
   - Otherwise → return `"pass"`.

For all other intents (`general_knowledge`, `conversational`) → return `"pass"` without checks.

**Enforcement posture:** soft. The guardrail returns the result; the caller logs it. No response rejection.

**Wire into `ChatController`:**

Call `output_guardrail.evaluate(...)` after the LLM call in `_handle_rfq_specific`, `_handle_disambiguation`, and `_handle_unsupported`. Log the result:

```python
guardrail_result = self.output_guardrail.evaluate(...)
log("phase6.output_guardrail_result", guardrail_result)
```

Do NOT call the guardrail in `_handle_general_knowledge` or `_handle_conversational`.

### 10.3 Dependencies

- Steps 3–9 complete (all route handlers finalized).

### 10.4 Tests to add

- **Create** `tests/unit/controllers/test_output_guardrail.py`
  - `rfq_specific` + non-empty source_refs → `"pass"`.
  - `rfq_specific` + empty source_refs + `grounding_gap_injected=False` → `"grounding_violation"`.
  - `rfq_specific` + empty source_refs + `grounding_gap_injected=True` → `"pass"`.
  - `disambiguation` + response contains "?" → `"pass"`.
  - `disambiguation` + response contains "which" → `"pass"`.
  - `disambiguation` + response lacks all signals → `"disambiguation_shape_violation"`.
  - `unsupported` + capability name in response → `"pass"`.
  - `unsupported` + capability name missing → `"unsupported_routing_violation"`.
  - `general_knowledge` → `"pass"` (no check).
  - `conversational` → `"pass"` (no check).

### 10.5 Review checkpoint

- Guardrail is soft: returns a string, never rejects or modifies the response.
- Only three checks exist; no additional checks were invented.
- `general_knowledge` and `conversational` always return `"pass"`.
- `phase6.output_guardrail_result` is logged for every turn that passes through a guardrailed route.
- Tests green.

### 10.6 Pack references

§E.1–E.4, §F.1 (steps 5g, 7d, 8d), §G.2.

---

## Step 11 — Observability instrumentation

### 11.1 Files

- **Modify** `src/controllers/chat_controller.py`
- **Modify** `src/controllers/intent_controller.py` (if any fields not yet emitted)

### 11.2 Responsibilities

Verify that all ten Phase 6 log fields from Pack §G.2 are emitted at the correct pipeline positions. Most should already be wired from Steps 3, 5, 8, and 10. This step is a verification pass and gap-fill.

Complete list of required Phase 6 log fields:

| Field | Emitted by | Step where wired |
|---|---|---|
| `phase6.intent_classified` | ChatController (Step 3) | 3 |
| `phase6.route_selected` | ChatController (Step 3) | 3 |
| `phase6.disambiguation_triggered` | ChatController (Step 8) | 8 |
| `phase6.disambiguation_resolved` | ChatController (Step 3) | 3 |
| `phase6.disambiguation_abandoned` | ChatController (Step 3) | 3 |
| `phase6.grounding_required` | ChatController (Step 5) | 5 |
| `phase6.grounding_satisfied` | ChatController (Step 5) | 5 |
| `phase6.grounding_mismatch` | ChatController (Step 5) | 5 |
| `phase6.grounding_gap_absence_injected` | ChatController (Step 5) | 5 |
| `phase6.output_guardrail_result` | ChatController (Step 10) | 10 |

If any field is missing from its expected step, add it here.

Also verify: all Phase 5 `phase5.*` fields continue to emit for `rfq_specific` turns (since the `rfq_specific` route runs the full Phase 5 pipeline internally).

### 11.3 Dependencies

- Steps 3, 5, 8, 10 complete.

### 11.4 Tests to add

- **Create** `tests/integration/test_phase6_observability.py`
  - One `rfq_specific` turn → all applicable Phase 5 and Phase 6 fields present.
  - One `general_knowledge` turn → `phase6.intent_classified` and `phase6.route_selected` present; no Phase 5 stage/tool fields; no `phase6.grounding_*` fields.
  - One `disambiguation` turn → `phase6.disambiguation_triggered` present.
  - One disambiguation resolution turn → `phase6.disambiguation_resolved` present.
  - One `conversational` turn → only `phase6.intent_classified` and `phase6.route_selected`; no guardrail result.

### 11.5 Review checkpoint

- All ten Pack §G.2 fields appear in the correct tests.
- Phase 5 fields still emit unchanged for `rfq_specific` turns.
- No new DTO or HTTP response fields.
- Tests green.

### 11.6 Pack references

§G.1–G.3.

---

## Step 12 — Pytest integration scenarios

### 12.1 Files

- **Create** `tests/integration/test_phase6_scenarios.py` (if not already created in earlier steps; consolidate here)

### 12.2 Responsibilities

Implement all fourteen scenarios from Pack §K.2 as pytest integration tests using the full FastAPI `TestClient` with mocked connectors.

Some scenarios may already exist from Steps 3–9. This step consolidates them into the canonical scenario file and ensures all fourteen are present, passing, and self-contained.

Each test follows the existing Phase 5 pattern: dependency overrides for Azure OpenAI, manager, and intelligence connectors; session creation via the API; turn submission; assertion on response status, content, source_refs, and log fields.

**Scenarios 1–5:** Intent classification (rfq_specific, general_knowledge on bound, general_knowledge on portfolio, unsupported, conversational).

**Scenarios 6–8:** Grounding enforcement (tool success, tool failure, grounding mismatch).

**Scenarios 9–11:** Disambiguation (trigger, resolution, abandonment).

**Scenario 12:** Output guardrail soft enforcement on grounding gap (`phase6.grounding_gap_absence_injected=true`, `phase6.output_guardrail_result=pass`, HTTP 200 passes through).

**Scenario 13:** Phase 5 regression guard (all six Phase 5 scenarios still pass).

**Scenario 14:** Mode B general knowledge works.

### 12.3 Dependencies

- Steps 1–11 all complete.

### 12.4 Review checkpoint

- All fourteen scenarios pass in CI.
- Tests use mocks, not live services.
- Tests are deterministic.
- Phase 5 scenarios pass unchanged (Scenario 13).

### 12.5 Pack references

§K.1–K.3, §13.

---

## Step 13 — Postman demo beats

### 13.1 Files

- **Create** `docs/postman/rfq_chatbot_ms_postman_phase6_demo_v1.json`
- **Create** `docs/postman/rfq_chatbot_ms_postman_phase6_demo_env_v1.json`

### 13.2 Responsibilities

Create Postman collection and environment for the fourteen Phase 6 demo scenarios. Follow the existing Phase 5 Postman collection pattern (folders per scenario, test assertions per request, environment variables for base URLs and RFQ IDs).

Each scenario folder should contain:

- Pre-request setup (session creation, RFQ binding where needed).
- The turn request(s).
- Postman test assertions on HTTP status, response body patterns, and where applicable, the confidence marker or absence template.

For Scenario 13 (Phase 5 regression), point to the existing Phase 5 Postman collection rather than duplicating its beats.

### 13.3 Dependencies

- Step 12 complete.

### 13.4 Review checkpoint

- All fourteen beats runnable in a single collection run.
- Environment variables cover both Mode A and Mode B sessions.
- Each beat has at least one Postman test assertion.

### 13.5 Pack references

§K.1, §13 (acceptance #2, #9).

---

## Step 14 — Documentation

### 14.1 Files

- **Modify** `CLAUDE.md`
- **Modify** `README.md`
- **Verify** `docs/rfq_chatbot_ms_openapi_current.yaml` — must require **no changes** (hard acceptance gate).
- **Verify** `docs/rfq_chatbot_ms_api_contract_current.html` — must require **no changes** (hard acceptance gate).

### 14.2 Responsibilities

**CLAUDE.md additions:**

- A "Phase 6 behaviors" section listing the four milestones.
- Updated "What not to do" section adding: no LLM classifier, no semantic hallucination detection, no hard output guardrail enforcement, no portfolio tools, no contract changes, no implicit session binding from disambiguation.
- Pointer to the Phase 6 Pack and Blueprint for canonical decisions.

**README.md additions:**

- Update the service description to reflect Phase 6: intent-aware, grounding-enforced, disambiguation-capable.
- Add `src/config/intent_patterns.py` and `src/config/disambiguation_config.py` to the configuration note.
- Update the "does not yet include" section to say Phase 7+ (not Phase 6+).

**Contract verification:**

Open the OpenAPI YAML and HTML contract. Confirm they do not need changes. If they do, this is a Phase 6 scope violation — raise it as a finding, do not edit.

### 14.3 Dependencies

- Step 13 complete.

### 14.4 Review checkpoint

- OpenAPI YAML and HTML contract unchanged (hard check).
- `CLAUDE.md` explicitly names Phase 7 fences.
- Tests green.

### 14.5 Pack references

§H.1–H.2, §13 (acceptance #6, #7).

---

## 10. Cross-cutting review checkpoints (applied after every step)

These invariants are checked on every PR regardless of step:

1. **No contract change.** `git diff` on all model files, OpenAPI YAML, and HTML contract shows no functional changes.
2. **No new endpoint.** `git grep -E '@router\.(get|post|patch|put|delete)'` shows the same decorator set as Phase 5.
3. **Five intents only.** `git grep` on `intent_patterns.py` shows exactly five intent values.
4. **No LLM classifier.** No Azure OpenAI calls in `IntentController`.
5. **Phase 5 fields still emit.** `git grep 'phase5\.'` shows all Phase 5 log fields still present and unchanged.
6. **Output guardrail is soft.** No code path in `OutputGuardrail` rejects, replaces, or modifies the response.
7. **No implicit session binding.** `git grep 'rfq_id'` in disambiguation-related code shows no writes to `session.rfq_id`.
8. **Conversational has no guardrail.** `_handle_conversational` does not call `output_guardrail.evaluate`.

---

## 11. Sequencing and parallelism

Steps 1 and 2 can be developed quickly in sequence. Step 3 is the highest-risk step (ChatController rewiring) and gets two reviewers minimum.

Steps 4–5 (grounding) and Steps 6–8 (disambiguation) have no mutual dependencies after Step 3, so they *could* be parallelized by two implementers. However, for review simplicity, running them sequentially is recommended.

Steps 9–14 are strictly sequential.

The critical path is: **1 → 2 → 3 → (4 → 5) → (6 → 7 → 8) → 9 → 10 → 11 → 12 → 13 → 14**.

---

## 12. When Phase 6 is done

Phase 6 is done when Pack §13's ten acceptance criteria all hold:

- [ ] All fourteen scenarios pass as pytest integration tests in CI.
- [ ] All fourteen scenarios exist as executable Postman demo beats.
- [ ] All ten Phase 6 log fields appear correctly for applicable turns.
- [ ] All Phase 5 log fields continue to emit unchanged.
- [ ] `src/config/intent_patterns.py` and `src/config/disambiguation_config.py` exist and are typed.
- [ ] `PromptEnvelope` Pydantic class byte-identical to Phase 4/5.
- [ ] OpenAPI YAML requires no changes.
- [ ] All Phase 5 demo beats still pass unchanged.
- [ ] Full fourteen-beat demo runnable end-to-end in Postman.
- [ ] Output guardrail emits structured violation logs for grounding-gap scenarios.

When all ten hold, Phase 6 ships. The next phase starts from a known-good baseline.

---

**End of Implementation Blueprint v1.0.**
