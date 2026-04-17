Phase 5 Mode A — Implementation Pack v1.0
=========================================

**Status:** Frozen — no conceptual decisions remain open

**Scope:** rfq\_chatbot\_ms — Mode A (RFQ Copilot) behavioral enrichment

**Posture:** Behavior-first, contract-stable, declarative configuration, subtractive gating

**Pairing:** This Pack defines _what_. The companion Blueprint defines _how_ (file-by-file sequence).

0\. Executive summary
---------------------

Phase 5 changes rfq\_chatbot\_ms from _"I can chat and retrieve RFQ facts"_ to _"I behave differently depending on the real stage, the user role, and how strong the evidence is."_

The phase ships nine locked behaviors:

1.  Proactive stage resolution at turn start.
    
2.  Two-persona declarative role framing.
    
3.  Deterministic subtractive tool gating via intersection of stage and role allow-lists.
    
4.  Closed-list speakable absence via get\_capability\_status.
    
5.  Structured confidence marker for pattern-based answers.
    
6.  Single-fetch intra-turn reuse of ManagerRfqDetail.
    
7.  PromptEnvelope public shape frozen; internal composition restructured.
    
8.  Mode B hard-frozen: no code change permitted in Phase 5.
    
9.  Observability via structured logs only; no DTO expansion.
    

Phase 5 produces **no API contract change**. All observable effects live in answer text, test outcomes, and logs. This is by design and is the Phase 5 story.

1\. Phase 5 scope fences
------------------------

### 1.1 What Phase 5 is

Behavior enrichment of the existing Phase 4 turn pipeline. Same endpoints, same DTOs, same error mapping, same Azure OpenAI posture. The turn now resolves stage and role at start, gates the keyword planner subtractively by both, renders confidence distinctions, and honestly speaks absence for known unsupported capabilities.

### 1.2 What Phase 5 is not

*   Not an intent classifier.
    
*   Not a knowledge-boundary router.
    
*   Not a guardrail enforcement layer.
    
*   Not a disambiguation engine.
    
*   Not a portfolio/Mode B maturation.
    
*   Not a document-RAG expansion.
    
*   Not a contract change.
    
*   Not a config-management infrastructure project.
    

All of the above belong to Phase 6 or later.

### 1.3 Frozen items (do not move in Phase 5)

*   Session creation/binding rules.
    
*   One-way RFQ binding semantics (no unbind, no rebind).
    
*   One conversation per session invariant.
    
*   Non-streaming Azure OpenAI posture; no native function-calling.
    
*   Error status mapping (NotFoundError→404, ConflictError→409, etc.).
    
*   All DTO shapes: ChatbotSessionRead, TurnRequest, TurnResponse, ConversationReadResponse, ConversationMessageRead, SourceRef.
    
*   PromptEnvelope public shape: stable\_prefix, variable\_suffix, total\_budget. Internal composition may restructure; public fields may not rename, extend, or drop.
    
*   tool\_calls persisted but not surfaced on read DTOs.
    
*   pending\_pivot session mode remains defined in the enum but unused.
    

2\. Decision Set A — Stage awareness
------------------------------------

### A.1 Activation

Stage resolution fires at turn start for RFQ-bound sessions only. For portfolio sessions and global requests, stage resolution is skipped entirely.

### A.2 Routing key

ManagerRfqDetail.current\_stage\_id (UUID) is the routing key for all stage-conditioned logic. current\_stage\_name is used only for prompt-visible framing text shown to the LLM and ultimately the user. No fuzzy name-matching anywhere in routing logic.

### A.3 Fetch mechanism

Stage resolution invokes ManagerConnector.get\_rfq(rfq\_id) exactly once per turn. The returned ManagerRfqDetail is stashed in request-scoped state and reused by any later component in the same turn that needs it (see §F).

### A.4 Configuration surface

Python module: src/config/stage\_profiles.py.

Declarative mapping typed as:

python

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   class StageProfile(TypedDict):      prompt_frame_fragment: str      # text injected into stable_prefix      tool_allow_list: frozenset[str] # names of tools allowed at this stage  STAGE_PROFILES: dict[UUID, StageProfile] = { ... }  DEFAULT_STAGE_PROFILE: StageProfile = { ... }   `

Keys are current\_stage\_id UUIDs from manager. Unknown stage ids resolve to DEFAULT\_STAGE\_PROFILE, which grants the full tool allow-list and emits a neutral framing fragment.

### A.5 Failure mode

If get\_rfq(rfq\_id) raises UpstreamTimeoutError, UpstreamServiceError, or NotFoundError, stage resolution **degrades gracefully**:

*   The turn proceeds as if the session were not stage-aware.
    
*   DEFAULT\_STAGE\_PROFILE is applied.
    
*   phase5.stage\_resolved is logged with the failure reason.
    
*   The turn does not fail-close on a retrieval-independent question.
    

If the user's turn content _also_ requires retrieval that needs the same data (e.g., asking about the deadline), and that retrieval also fails, the failure surfaces normally through the existing error-mapping path.

### A.6 What stage awareness does _not_ do

*   It does not invent a chatbot-side lifecycle enum.
    
*   It does not add an endpoint for listing stages.
    
*   It does not make stage-list (get\_rfq\_stages) a proactive call. Stage-list is fetched only when the keyword planner selects get\_rfq\_stage.
    

3\. Decision Set B — Role awareness
-----------------------------------

### B.1 Persona set

Exactly two personas are first-class in Phase 5:

*   estimation\_dept\_lead — working-level detail, retrieval-heavy, technical framing.
    
*   executive — summarized framing, higher-level framing, decision-oriented.
    

No third persona is introduced in Phase 5.

### B.2 Unknown-role fallback

If session.role is not exactly estimation\_dept\_lead or executive (including None, empty string, historical values like estimator, typos, or any unrecognized string), Phase 5 applies the estimation\_dept\_lead profile.

Rationale: estimation\_dept\_lead is the current AUTH\_BYPASS\_ROLE default and is the more conservative working-level persona — showing working-level detail to an unknown principal is safer than showing executive summaries of data that may need working-level qualifiers.

Fallback events emit phase5.role\_fallback\_used=true with the original role value logged alongside for debuggability.

### B.3 Configuration surface

Python module: src/config/role\_profiles.py.

Declarative mapping typed as:

python

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   class RoleProfile(TypedDict):      tone_directive: str              # text injected into stable_prefix      depth_directive: str             # text injected into stable_prefix      tool_allow_list: frozenset[str]  # names of tools allowed for this role  ROLE_PROFILES: dict[str, RoleProfile] = {      "estimation_dept_lead": { ... },      "executive": { ... },  }  FALLBACK_ROLE = "estimation_dept_lead"   `

### B.4 Resolution timing

Role resolution happens once per turn at turn start, immediately after stage resolution, before the tool planner runs. The resolved role is also stashed in request-scoped state.

### B.5 What role awareness does _not_ do

*   It does not authenticate or authorize. It reads session.role as stored.
    
*   It does not add IAM service calls.
    
*   It does not introduce role-based endpoint gating.
    

4\. Decision Set C — Tool planner gating
----------------------------------------

### C.1 Planner mechanism

The existing keyword planner in ToolController.\_plan\_tool\_use is retained as-is in terms of keyword matching. Phase 5 adds gating _after_ keyword match, not replacement.

### C.2 Intersection rule

The selected tool for a turn must satisfy all three conditions:

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   available_tools = keyword_matches                   ∩ stage_profile.tool_allow_list                   ∩ role_profile.tool_allow_list   `

*   keyword\_matches is the set produced by the existing keyword router.
    
*   stage\_profile.tool\_allow\_list comes from §A.4.
    
*   role\_profile.tool\_allow\_list comes from §B.3.
    

If available\_tools is empty after intersection (i.e., the keyword matched but stage or role subtracted it), the turn proceeds with no retrieval and produces a Confidence State C response per §D. The prior 422 "ambiguous" path remains for the case where multiple _different tool families_ match keywords before gating.

### C.3 Subtractive only

Stage and role configs may _remove_ tools from consideration. They may not _add_ tools, change tool priority, or rewrite planner logic. There is no mechanism by which a role or stage causes a different tool to be selected than the keyword router would have selected.

### C.4 Migration of unsupported\_keywords

The current Phase 4 ToolController.unsupported\_keywords tuple is deleted in full in Phase 5. Its contents are migrated verbatim into the capability-status closed list (§D.2). The Phase 4 UnprocessableEntityError("This retrieval request is not supported in Phase 4 yet") branch is removed.

The ambiguous 422 path (multiple tool families in one turn) is retained unchanged — that path handles request-shape problems, not capability-absence problems, and the two concerns stay separated.

5\. Decision Set D — Confidence-aware rendering
-----------------------------------------------

### D.1 Three states (per the brief)

*   **Deterministic** — tool result with confidence == deterministic. Answer contains no confidence marker.
    
*   **Pattern-based** — at least one contributing tool result has confidence == pattern\_1\_sample. Answer contains the structured marker from §D.3.
    
*   **Absent** — the capability-status path fires (§D.2). Answer is a speakable honest-absence response following the template in §D.4.
    

### D.2 get\_capability\_status — closed-list speakable absence

A new in-process capability named get\_capability\_status is introduced. It is **not** a new endpoint, not a new HTTP-surface tool, and not a discovery API.

Mechanism: before the keyword planner runs, ToolController consults a closed list of known absent capabilities. If the user content matches any entry in the list, the planner short-circuits and emits an absent ToolResultEnvelope carrying a capability-status payload. Retrieval does not fire. The chat controller then builds a Confidence State C prompt (§D.4).

The closed list is the full migration of the prior Phase 4 unsupported\_keywords:

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   briefing, workbook review, workbook profile, analytics, stats,  list rfqs, portfolio, grand total, final price, estimation amount   `

Each entry maps to a short named future condition (e.g., "Briefing capabilities activate once the briefing panel reaches parity with intelligence snapshots"). The named conditions are part of the closed list and live in the same Python config module that defines the list.

The capability-status path is deterministic: keyword → entry → fixed envelope. No classification, no scoring, no LLM involvement.

### D.3 Hedge marker format

When any contributing tool result has confidence == pattern\_1\_sample, the assistant response ends with exactly this trailing line:

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   Confidence: pattern-based (validated against 1 sample)   `

*   The marker is literal and fixed. The prompt instructs the LLM to emit it verbatim as the final line of its response when pattern-based evidence is present.
    
*   When all contributing tool results are deterministic, no marker is emitted. Absence of marker is itself the signal.
    
*   When the capability-status path fires (§D.2), no marker is emitted; the absence template (§D.4) is its own honest signal.
    

Tests assert marker presence/absence via exact substring match. This is testable deterministically and does not require LLM-output regex.

### D.4 Absence response template

When the capability-status path fires, the prompt instructs the LLM to produce a response following this template:

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   I don't have grounded facts for [capability name] yet because [named future condition].  [optional: one sentence redirect to what the chatbot can answer]   `

The named future condition comes from the capability-status entry. The LLM is instructed never to invent a capability status not present in the envelope.

### D.5 Rendering location

All confidence rendering is implemented via prompt instructions in ContextBuilder. No post-processing, no response rewriting, no marker-injection after generation. The prompt carries the directive; the LLM emits the marker; the test verifies the emission.

6\. Decision Set E — Prompt assembly
------------------------------------

### E.1 Public contract

PromptEnvelope(stable\_prefix: str, variable\_suffix: str, total\_budget: int) is publicly frozen. No field additions, no renames, no drops. Phase 6+ may revisit.

### E.2 Internal composition

stable\_prefix is assembled from:

1.  The existing base system prompt (RFQ Copilot role statement).
    
2.  Role framing from the resolved role profile (tone\_directive + depth\_directive).
    
3.  Stage framing from the resolved stage profile (prompt\_frame\_fragment).
    
4.  Confidence-rendering directives (instructions for emitting the §D.3 marker and §D.4 template).
    

variable\_suffix is assembled from:

1.  Recent conversation history (existing behavior).
    
2.  Retrieved facts blocks from tool\_call\_records\_to\_prompt\_blocks (existing behavior).
    
3.  The latest user turn (existing behavior).
    

### E.3 Rationale

This preserves stable\_prefix's original semantics: the portion that does not change across turns within a given session-plus-RFQ context. Role framing is session-stable. Stage framing is session-stable given the RFQ's current stage, which changes slowly relative to chat turns. History, retrieval, and the current turn are inherently per-turn and belong in variable\_suffix.

Side effect: this composition is prompt-caching-friendly for any future Azure OpenAI prompt-cache integration. That integration is not a Phase 5 deliverable, but Phase 5 does not close the door on it.

### E.4 What prompt assembly does _not_ do

*   No history compression or summarization.
    
*   No dynamic token-budget reallocation.
    
*   No retrieval-result ranking or truncation beyond existing behavior.
    

7\. Decision Set F — Intra-turn reuse
-------------------------------------

### F.1 Scope

Intra-turn reuse applies _only_ to the ManagerRfqDetail artifact fetched by the proactive stage resolver.

### F.2 Mechanism

Stage resolution fetches ManagerRfqDetail via ManagerConnector.get\_rfq(rfq\_id) and stores it in request-scoped state. If the keyword planner subsequently selects get\_rfq\_profile in the same turn, the tool reuses the stashed artifact rather than invoking get\_rfq(rfq\_id) a second time. The tool's ToolResultEnvelope is constructed from the stashed data with identical confidence, source\_ref, and provenance semantics as a fresh fetch.

### F.3 Out of scope for intra-turn reuse

*   ManagerConnector.get\_rfq\_stages(rfq\_id) fetches from get\_rfq\_stage are **not** subject to intra-turn reuse. They fire independently when the planner selects them.
    
*   IntelligenceConnector.get\_snapshot(rfq\_id) fetches from get\_rfq\_snapshot are **not** subject to intra-turn reuse.
    
*   No cross-artifact reuse, no cache manager abstraction, no request-scoped TTL.
    

### F.4 Cross-turn caching

Cross-turn caching of stage resolution (same session, same RFQ, subsequent turns reusing the same ManagerRfqDetail) is **optional** in Phase 5. It is a performance optimization, not a correctness requirement. If implemented, it lives in request- or session-scoped state managed by StageController and is documented as such. The Blueprint may defer it to a post-Phase-5 polish item.

### F.5 Two distinct mechanisms

*   **Intra-turn reuse** (§F.2) is a _correctness_ mechanism. Mandatory. Prevents duplicate identical fetches within a single turn.
    
*   **Cross-turn caching** (§F.4) is a _performance_ optimization. Optional. Reduces per-turn latency when stage rarely changes.
    

These are not the same thing and should not share implementation.

8\. Decision Set G — Chat pipeline order
----------------------------------------

### G.1 Locked execution sequence

The correct order inside ChatController.handle\_turn is:

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   1. Load session (existing)  2. Get-or-create conversation (existing)  3. Resolve stage      ← new, proactive  4. Resolve role       ← new, proactive  5. ToolController.maybe_execute_retrieval  ← now uses stage + role gating  6. Fetch recent history (existing)  7. Persist user message (existing)  8. ContextBuilder.build  ← now uses role + stage + confidence directives  9. Azure OpenAI chat-completions call (existing)  10. Persist assistant message (existing)  11. Return TurnResponse (existing)   `

The key correctness properties:

*   Stage and role resolve _before_ the tool planner, so gating can use their outputs.
    
*   The tool planner runs _before_ ContextBuilder.build, so retrieval results are available when the prompt is assembled.
    
*   ContextBuilder is the _only_ component that consumes stage, role, and retrieval context together.
    

### G.2 Request-scoped state

Stage and role resolution outputs are passed as explicit function arguments through the pipeline, not stored on controller instances. FastAPI's request lifecycle defines the scope. No global state, no thread-local, no singleton.

### G.3 What the pipeline does _not_ do

*   No multi-tool turns. Exactly one tool selection per turn, as today.
    
*   No streaming. Single non-streaming Azure OpenAI call, as today.
    
*   No retry on post-LLM failures. Existing connector-level retry policy applies.
    

9\. Decision Set H — Observability
----------------------------------

### H.1 Mechanism

Structured logs only. No new HTTP response fields. No new DTO properties.

### H.2 Required log fields

Each Phase 5 decision point emits a stable, named log field. Field names are frozen in this Pack and must not be renamed during implementation without a Pack revision.

In pipeline execution order:

FieldWhen emittedValuephase5.stage\_resolvedAfter stage resolution step on success, "default\_profile\_applied" on fallback, or failure reason stringphase5.role\_appliedAfter role resolution stepResolved role value (estimation\_dept\_lead or executive)phase5.role\_fallback\_usedAfter role resolution steptrue if original session role was not in the valid persona set, otherwise falsephase5.tools\_keyword\_matchedAfter keyword router runsList of tool names the keyword router matchedphase5.tools\_allowed\_after\_stageAfter stage gatingList of tool names remaining after stage allow-list intersectionphase5.tools\_allowed\_after\_roleAfter role gatingList of tool names remaining after role allow-list intersectionphase5.capability\_status\_hitWhen capability-status path firesThe matched capability name; otherwise field is absentphase5.confidence\_marker\_emittedAfter LLM calltrue if any contributing tool had confidence == pattern\_1\_sample, otherwise false

When role fallback occurs, the original stored role value is logged alongside phase5.role\_fallback\_used (e.g., phase5.role\_original="estimator").

### H.3 Log format

Fields are emitted as key-value pairs in the existing logging framework. No dedicated log stream, no structured event bus. The Phase 5 fields coexist with the current turn-level log lines.

### H.4 Why this matters

Phase 5 is intentionally behavior-first and contract-stable. Without structured decision-point logs, debugging the very behaviors Phase 5 introduces becomes black-box. The log fields also provide the signal data that a future Phase 6 intent router can learn from — collecting it now is free and pays forward.

10\. Decision Set I — Mode B boundary
-------------------------------------

### I.1 Hard freeze

No code change permitted to Mode B in Phase 5. This includes:

*   No changes to SessionEntryMode.GLOBAL handling in ModeController.
    
*   No changes to the portfolio session path in session\_routes.py.
    
*   No changes to tool\_controller.py behavior when session.mode == portfolio.
    
*   No new portfolio-specific tools, keywords, or capability-status entries.
    
*   No new portfolio prompt framing.
    

### I.2 Scope of the freeze

The freeze applies to code, not to ambient behavior. If a Phase 5 change in shared code (e.g., ContextBuilder restructure) produces an incidental behavior change for portfolio sessions, that is acceptable _only if_ existing Mode B tests still pass and no new Mode B code is written. Otherwise the change is out of scope.

### I.3 Rationale

Portfolio/disambiguation behavior belongs to Phase 6 by design. Strengthening Mode A is where stage, role, and confidence signals have coherent meaning. Stretching Phase 5 into Mode B dilutes both phases.

11\. Decision Set J — Tests and demo acceptance
-----------------------------------------------

### J.1 Dual acceptance posture

Every named Phase 5 behavior must exist as both:

*   a **pytest integration test** that gates the CI build, and
    
*   a **scripted demo beat** in the existing Postman collection for jury demonstration.
    

Neither alone is acceptance. Pytest without Postman leaves the jury watching the implementer type curl commands. Postman without pytest leaves Phase 5 vulnerable to silent regression.

### J.2 Required scenarios

**Scenario 1: Role contrast on the same RFQ.**Same RFQ, same user question (e.g., "what's the status?"), two sessions with different roles. Assert:

*   Responses differ in framing (length, depth, tone indicators).
    
*   Both responses carry the same source\_refs\[\] (same underlying facts).
    
*   phase5.role\_applied differs across the two sessions in logs.
    

**Scenario 2: Stage contrast on the same question.**Two RFQs at different current\_stage\_id values (e.g., intake vs. bidding). Same user question. Assert:

*   Prompt framing differs (visible in response content and in prompt-inspection test hooks).
    
*   phase5.stage\_resolved differs in logs.
    
*   Tool emphasis may differ if stage allow-lists differ.
    

**Scenario 3: Confidence marker presence and absence.**Two questions on one RFQ: one that resolves via a deterministic tool (get\_rfq\_profile → ManagerRfqDetail), one that resolves via the pattern-based tool (get\_rfq\_snapshot → IntelligenceSnapshotArtifact). Assert:

*   The deterministic response does not contain "Confidence: pattern-based".
    
*   The pattern-based response ends with exactly "Confidence: pattern-based (validated against 1 sample)".
    
*   phase5.confidence\_marker\_emitted differs correctly across the two turns.
    

**Scenario 4: Capability-status honest absence.**A user question matching a capability-status keyword (e.g., "what's the briefing?"). Assert:

*   Response follows the absence template, names the future condition, and does not hallucinate content.
    
*   No retrieval call fires (neither manager nor intelligence is invoked).
    
*   phase5.capability\_status\_hit appears in logs with the matched capability name.
    
*   Response HTTP status is 200, _not_ 422. (This validates the migration from the Phase 4 unsupported\_keywords 422 path.)
    

**Scenario 5: Trivial no-retrieval turn regression guard.**A user turn that does not trigger any keyword match and does not hit capability-status (e.g., a greeting, a general conversational exchange). Assert:

*   Turn produces an assistant response successfully.
    
*   No retrieval calls fire.
    
*   source\_refs\[\] is empty.
    
*   No confidence marker is emitted.
    
*   Response latency remains within the Phase 4 baseline band.
    

**Scenario 6: Stage resolution graceful degradation.**Manager service returns 503 on the stage-resolution get\_rfq call for a retrieval-independent user turn (e.g., a greeting). Assert:

*   Turn still completes successfully.
    
*   phase5.stage\_resolved logs the failure reason.
    
*   Default stage profile is applied.
    
*   No 503 propagates to the API response.
    

### J.3 Out of scope for Phase 5 tests

*   No grounding-guardrail tests (Phase 6).
    
*   No knowledge-boundary routing tests (Phase 6).
    
*   No load testing (Phase 5 doesn't change performance characteristics enough to warrant it).
    
*   No Mode B regression tests beyond "existing Mode B tests still pass."
    

12\. Acceptance criteria — Phase 5 is done when
-----------------------------------------------

All of the following are true simultaneously:

1.  All six scenarios in §J.2 pass as pytest integration tests in CI.
    
2.  All six scenarios exist as executable Postman demo beats in the demo collection.
    
3.  The eight required log fields in §H.2 appear correctly for every turn.
    
4.  The Phase 4 unsupported\_keywords tuple and its associated 422 branch are deleted from ToolController.
    
5.  src/config/stage\_profiles.py and src/config/role\_profiles.py exist, are typed, and contain at least the default profile plus one non-default stage and two personas.
    
6.  PromptEnvelope Pydantic class is byte-identical to its Phase 4 definition. (Hard contract check.)
    
7.  The OpenAPI YAML (docs/rfq\_chatbot\_ms\_openapi\_current.yaml) requires no changes to pass review. (Hard contract check.)
    
8.  No code changes exist under any path that is exclusive to Mode B.
    
9.  Existing Phase 4 demo beats still pass unchanged.
    
10.  The implementer can demonstrate all six scenarios live in the Postman collection in a single session without manual intervention.
    

When all ten hold, Phase 5 Mode A is done.

13\. Out-of-scope / Phase 6 fence (restated)
--------------------------------------------

The following remain explicitly out of Phase 5 and belong to Phase 6 or later:

*   Intent classification.
    
*   Knowledge-boundary routing.
    
*   Output guardrails and retry/fail-closed enforcement.
    
*   Multi-tool turns and native function-calling.
    
*   Planner rewriting (as opposed to subtractive gating).
    
*   Portfolio/Mode B tool surface and disambiguation.
    
*   Document RAG and chunk-vector retrieval.
    
*   Semantic or procedural memory.
    
*   History compression.
    
*   JWT / IAM middleware and request-path authentication.
    
*   Correlation-ID middleware and /metrics endpoint parity with manager.
    
*   Surfacing tool\_calls on response DTOs.
    
*   YAML- or DB-backed configuration.
    
*   Admin endpoints for stage/role profile management.
    
*   Role taxonomy beyond the two Phase 5 personas.
    
*   A GET /capabilities discovery endpoint.
    

This list is exhaustive for Phase 5 scope fencing. Anything in this list appearing in a Phase 5 PR is grounds for rejection.

14\. Handoff to the Blueprint
-----------------------------

The Pack locks _what_. The Blueprint will lock _how_, in this expected order:

1.  Config modules (stage\_profiles.py, role\_profiles.py, capability\_status.py).
    
2.  New controllers (stage\_controller.py, role\_controller.py).
    
3.  ToolController surgery (subtractive gating, intersection rule, capability-status migration, unsupported\_keywords deletion).
    
4.  ContextBuilder restructure (internal composition, confidence directives, absence template).
    
5.  ChatController rewiring (pipeline order from §G.1, intra-turn reuse from §F).
    
6.  Observability instrumentation (the eight log fields from §H.2).
    
7.  Pytest integration tests (the six scenarios from §J.2).
    
8.  Postman demo beat extensions (the six scenarios as demo steps).
    
9.  Documentation updates (CLAUDE.md for rfq\_chatbot\_ms, README notes, brief alignment check).
    

This order makes each step independently reviewable and independently testable. The correctness-critical pipeline-order fix lands in step 5, where it's most visible to reviewers.