# Phase 6.5 — Domain Boundary Enforcement & Response Discipline

## Implementation Plan

Execute the Blueprint (7 steps, in exact order) to repair three live failures: greeting data dump, identity self-narration, and off-domain bread recipe.

---

## Pre-flight: Rename Target Map

Complete `general_knowledge` → `domain_knowledge` rename across **11 src locations** and **25 test locations** (mapped via grep).

### Source files (11 occurrences):
| File | Lines | Count |
|------|-------|-------|
| `src/config/intent_patterns.py` | 13, 69, 80 | 3 |
| `src/controllers/intent_controller.py` | 71, 132, 134 | 3 |
| `src/controllers/chat_controller.py` | 148, 149, 279, 472 | 4 |
| `src/controllers/output_guardrail.py` | 21 | 1 |

### Test files (25 occurrences):
| File | Lines | Count |
|------|-------|-------|
| `tests/unit/config/test_intent_patterns.py` | 7 | 1 |
| `tests/unit/controllers/test_intent_controller.py` | 47, 56, 59, 68, 152, 161, 191, 234, 244 | 9 |
| `tests/unit/controllers/test_output_guardrail.py` | 127, 131 | 2 |
| `tests/integration/test_intent_routing.py` | 193, 214, 373, 394 | 4 |
| `tests/integration/test_phase6_scenarios.py` | 237, 252, 264, 274, 438, 484, 495 | 7 |
| `tests/integration/test_phase6_observability.py` | 168, 189 | 2 |

---

## Step-by-Step Plan

### Step 1 — `src/config/intent_patterns.py`
- Rename `general_knowledge` → `domain_knowledge` (3 locations)
- Add `import re`, `import random` at top
- Add `DOMAIN_VOCAB_TIER1`, `DOMAIN_VOCAB_TIER2`, `DOMAIN_VOCABULARY` sets
- Add `message_contains_domain_term()` function
- Add `CONVERSATIONAL_SUBTYPES` dict and `classify_conversational_subtype()` function
- Add `OUT_OF_SCOPE_REFUSALS` list and `get_out_of_scope_refusal()` function
- Add `OFF_DOMAIN_INDICATORS` list and `response_contains_off_domain_content()` function

### Step 2 — `src/controllers/intent_controller.py`
- Rename `general_knowledge` → `domain_knowledge` (3 locations)
- Add `out_of_scope` as valid intent
- Import `message_contains_domain_term`, `classify_conversational_subtype`
- Add domain gate: after pattern match produces `domain_knowledge`, check `message_contains_domain_term()` → if False, reclassify as `out_of_scope`
- Add `conversational_subtype` field to `IntentClassification` dataclass
- Populate subtype when intent = `conversational`

### Step 3 — `src/config/prompt_templates.py`
- No `general_knowledge` string literals to rename (confirmed — none present)
- Add `DOMAIN_CONSTRAINTS` prescriptive string (replaces descriptive `DOMAIN_CONSTRAINTS_SECTION_LINES`)
- Add `RESPONSE_FORMATTING` with 5 few-shot examples
- Add `CONVERSATIONAL_RULES` section
- Rewrite `GREETING_BEHAVIOR_SECTION_LINES` to be more restrictive
- Add `FORMAT_HINTS` dict
- Remove any "two concrete next actions" patterns (check `RESPONSE_RULES_SECTION_LINES`)

### Step 4 — `src/controllers/context_builder.py`
- Modify `_build_stable_prefix()` to accept `intent` and `conversational_subtype` parameters
- Implement intent-aware section inclusion matrix (FD-7)
- Create `_lite_response_rules_section()` method
- Create `_build_greeting_context()` method for 3-field greeting context
- Add `_domain_constraints_section()`, `_conversational_rules_section()`, `_response_formatting_section()` methods
- Add format hint to turn guidance
- Add history window truncation by intent
- Update `build()` signature to accept `intent` and `conversational_subtype`

### Step 5 — `src/controllers/chat_controller.py`
- Rename `general_knowledge` → `domain_knowledge` (4 locations: 148, 149, 279, 472)
- Rename `_handle_general_knowledge` → `_handle_domain_knowledge`
- Add `_handle_out_of_scope()` handler (deterministic refusal, no LLM)
- Wire `out_of_scope` in routing before existing routes
- Refactor `_handle_conversational()` with sub-type routing
- Pass `intent` and `conversational_subtype` to `context_builder.build()` calls
- Update `_intent_to_route()` for new intents

### Step 6 — `src/controllers/output_guardrail.py`
- Rename `general_knowledge` → `domain_knowledge` (1 location)
- Remove auto-pass for `domain_knowledge` and `conversational`
- Add `out_of_scope` pass-through
- Add domain leak detection for `domain_knowledge` (off-domain content check)
- Add verbose length warnings for `conversational` (soft guardrails)
- Add `conversational_subtype` parameter to `evaluate()`
- Wire domain_leak → refusal replacement in `chat_controller.py`

### Step 7 — Tests
- Global rename `general_knowledge` → `domain_knowledge` in all test files (25 locations)
- Update `ALLOWED_INTENTS` set to include `out_of_scope` and `domain_knowledge`
- Update test function names and assertions
- Update test_output_guardrail.py to test new guardrail behavior
- Add new boundary tests for domain gate
- Add conversational sub-type tests
- Run full test suite

---

## Verification Plan

### Automated Tests
```bash
pytest tests/ -v
```

### Grep Verification
```bash
grep -rn "general_knowledge" src/ tests/
# Must return zero results
```

### Behavioral Verification
- `"hello"` → 2-3 sentence contextual welcome
- `"who are you?"` → brief persona
- `"how to prepare bread at home"` → deterministic refusal (no LLM)
- `"what is PWHT?"` → domain_knowledge answer
- `"what's the grand total?"` → rfq_specific with tools

---

## Risk Mitigations

| Risk | Mitigation |
|------|-----------|
| Intent rename breaks tests | Mechanical find-replace, verified with grep |
| Greeting becomes too terse | FD-4 allows 2-3 warm sentences |
| Off-domain keywords false positives | Requires 2+ indicators |
| Context builder refactor breaks rfq_specific | rfq_specific gets ALL sections (no reduction) |

> [!IMPORTANT]
> The `context_builder.py` refactor is the most complex change. The existing `_build_stable_prefix()` includes ALL sections unconditionally. The refactor makes it intent-aware while ensuring `rfq_specific` still gets every section (no regression).

> [!WARNING]
> Several integration tests assert `"general_knowledge"` in log output values (e.g., `phase6.intent_classified`). These must be updated to `"domain_knowledge"` — but for tests like `test_phase6_scenario_11_disambiguation_abandonment` where `"what is PWHT?"` is used, the intent will now be `"domain_knowledge"` (PWHT passes the domain gate). For `"how does RT work?"` — `"rt"` is in DOMAIN_VOCAB_TIER1, so it also passes. All existing domain knowledge tests should still classify correctly after rename.
