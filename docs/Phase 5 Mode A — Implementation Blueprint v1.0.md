Phase 5 Mode A — Implementation Blueprint v1.0
==============================================

**Pair:** Execution plan for rfq\_chatbot\_ms Phase 5 Mode A — Implementation Pack v1.0**Posture:** File-by-file sequence. Each step is independently reviewable and independently testable.**Scope discipline:** This Blueprint adds _no_ decisions beyond the Pack. Where the Pack is silent, the Blueprint defers (not invents).**Acceptance:** Blueprint is complete when all ten criteria in Pack §12 hold.

0\. How to read this Blueprint
------------------------------

Each step names:

*   **Files** — create vs modify, with path.
    
*   **Responsibilities** — what the file/code must do, sourced from Pack decisions.
    
*   **Dependencies** — which prior steps must be green before starting.
    
*   **Tests to add in this step** — unit-level where possible, integration-level only where unavoidable.
    
*   **Review checkpoint** — the specific invariants a reviewer must confirm before merging.
    
*   **Pack references** — which Pack sections govern this step.
    

Steps are numbered and must be executed in order. A step may only ship if all prior steps are merged to main and green. No parallel work on later steps; no "I'll fix that in step 7" shortcuts that require step 7 to exist first.

Every step ends with a working, shippable codebase. If a step cannot end in that state, it's the wrong step and must be split.

Step 1 — Configuration modules
------------------------------

### 1.1 Files

*   **Create** src/config/stage\_profiles.py
    
*   **Create** src/config/role\_profiles.py
    
*   **Create** src/config/capability\_status.py
    

### 1.2 Responsibilities

**src/config/stage\_profiles.py** (Pack §A.4)

Defines:

python

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   from typing import TypedDict  from uuid import UUID  class StageProfile(TypedDict):      prompt_frame_fragment: str      tool_allow_list: frozenset[str]  STAGE_PROFILES: dict[UUID, StageProfile]  DEFAULT_STAGE_PROFILE: StageProfile   `

STAGE\_PROFILES must contain at least one non-default stage entry (Pack §12 acceptance #5). The stage UUIDs used must correspond to real manager-side stage identifiers from the golden reference RFQ — not invented UUIDs. If the implementer does not know a real stage UUID at build time, they stop and ask; they do not invent one.

DEFAULT\_STAGE\_PROFILE.tool\_allow\_list is the full set of current tool names: frozenset({"get\_rfq\_profile", "get\_rfq\_stage", "get\_rfq\_snapshot"}). This guarantees that unknown stages do not silently subtract any tool.

No class-based abstraction, no registry pattern, no loader. Plain module-level dict.

**src/config/role\_profiles.py** (Pack §B.3)

Defines:

python

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   from typing import TypedDict  class RoleProfile(TypedDict):      tone_directive: str      depth_directive: str      tool_allow_list: frozenset[str]  ROLE_PROFILES: dict[str, RoleProfile] = {      "estimation_dept_lead": { ... },      "executive": { ... },  }  FALLBACK_ROLE: str = "estimation_dept_lead"   `

Exactly two entries in ROLE\_PROFILES. Adding a third entry is a Pack violation.

tone\_directive and depth\_directive are short strings (one or two sentences each) written as imperatives the LLM can follow. Example shape (not verbatim; implementer selects the final wording):

*   estimation\_dept\_lead.tone\_directive: "Speak as a technical peer to an estimation engineer."
    
*   executive.depth\_directive: "Summarize to the decision level; omit field-level detail unless asked."
    

The strings themselves are prompt-engineering territory. The structure is frozen.

**src/config/capability\_status.py** (Pack §D.2, §C.4)

Defines:

python

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   from typing import TypedDict  class CapabilityStatus(TypedDict):      capability_name: str      named_future_condition: str  CAPABILITY_STATUS_ENTRIES: dict[str, CapabilityStatus]   `

Keys are the keyword triggers (lowercased, substring-match style consistent with the current ToolController keyword behavior). Values are the speakable-absence metadata.

The closed list is the exact migration of the Phase 4 unsupported\_keywords tuple:

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   briefing, workbook review, workbook profile, analytics, stats,  list rfqs, portfolio, grand total, final price, estimation amount   `

Each keyword maps to a capability name (human-readable, for the LLM to say) and a named future condition (for the LLM to justify the absence). Writing these strings is also prompt-engineering work; the structure is what this Pack/Blueprint locks.

### 1.3 Dependencies

None. This is the foundation step.

### 1.4 Tests to add

*   **Create** tests/unit/config/test\_stage\_profiles.py
    
    *   Assert DEFAULT\_STAGE\_PROFILE.tool\_allow\_list equals the full current tool name set.
        
    *   Assert every entry in STAGE\_PROFILES has non-empty prompt\_frame\_fragment and a tool\_allow\_list that is a subset of the full tool set.
        
*   **Create** tests/unit/config/test\_role\_profiles.py
    
    *   Assert ROLE\_PROFILES has exactly two keys: {"estimation\_dept\_lead", "executive"}.
        
    *   Assert FALLBACK\_ROLE == "estimation\_dept\_lead".
        
    *   Assert both profiles' tool\_allow\_list values are subsets of the full tool set.
        
*   **Create** tests/unit/config/test\_capability\_status.py
    
    *   Assert CAPABILITY\_STATUS\_ENTRIES keys are exactly the Phase 4 unsupported\_keywords set (verifies the migration is complete, not partial).
        
    *   Assert every entry has non-empty capability\_name and named\_future\_condition.
        

### 1.5 Review checkpoint

*   No YAML files introduced.
    
*   No DB migrations introduced.
    
*   No admin endpoints introduced.
    
*   Module-level constants only; no classes with behavior.
    
*   ROLE\_PROFILES contains exactly two entries.
    
*   CAPABILITY\_STATUS\_ENTRIES keys set-equal to the Phase 4 unsupported\_keywords tuple.
    
*   Tests green.
    

### 1.6 Pack references

§A.4, §B.3, §C.4, §D.2, §12 (acceptance #5).

Step 2 — Stage resolution controller
------------------------------------

### 2.1 Files

*   **Create** src/controllers/stage\_controller.py
    

### 2.2 Responsibilities

Defines StageController. Single public method:

python

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   def resolve_stage(self, session: ChatbotSession) -> StageResolution:   `

Behavior:

1.  If session.mode != SessionMode.RFQ\_BOUND, return a StageResolution whose profile is DEFAULT\_STAGE\_PROFILE and whose rfq\_detail is None. Emit phase5.stage\_resolved="skipped\_non\_rfq\_session". (Pack §A.1)
    
2.  If session.rfq\_id does not parse as a UUID, return the default-profile resolution with rfq\_detail=None and log phase5.stage\_resolved="invalid\_rfq\_id\_format". This mirrors the existing ToolController.\_require\_rfq\_uuid conservative behavior.
    
3.  Call ManagerConnector.get\_rfq(rfq\_id) exactly once. (Pack §A.3, §F.2)
    
4.  On UpstreamTimeoutError, UpstreamServiceError, or NotFoundError: return the default-profile resolution with rfq\_detail=None, log the failure reason via phase5.stage\_resolved. Do not re-raise. (Pack §A.5)
    
5.  On success: look up rfq\_detail.current\_stage\_id in STAGE\_PROFILES. If missing, apply DEFAULT\_STAGE\_PROFILE. Log phase5.stage\_resolved= (success) or phase5.stage\_resolved="default\_profile\_applied" (miss).
    
6.  Return a StageResolution containing:
    
    *   profile: StageProfile
        
    *   rfq\_detail: ManagerRfqDetail | None (the stashed artifact for intra-turn reuse per Pack §F.2)
        
    *   stage\_id: UUID | None (for later prompt-framing use via current\_stage\_name)
        

StageResolution is a small Pydantic model or dataclass — not a new DTO, not exposed on the API.

The controller is constructed with a ManagerConnector dependency via the existing app\_context wiring.

### 2.3 Dependencies

*   Step 1 complete (stage\_profiles.py exists).
    
*   No changes to ManagerConnector — it already exposes get\_rfq(rfq\_id).
    

### 2.4 Tests to add

*   **Create** tests/unit/controllers/test\_stage\_controller.py
    
    *   Portfolio session → default profile, no manager call made.
        
    *   RFQ-bound session with non-UUID rfq\_id → default profile, no manager call made.
        
    *   RFQ-bound session with valid UUID and known current\_stage\_id → correct profile selected, rfq\_detail returned.
        
    *   RFQ-bound session with valid UUID and unknown current\_stage\_id → default profile, rfq\_detail still returned.
        
    *   Manager call raises UpstreamTimeoutError → default profile, no re-raise.
        
    *   Manager call raises UpstreamServiceError → default profile, no re-raise.
        
    *   Manager call raises NotFoundError → default profile, no re-raise.
        
    *   Successful resolution calls ManagerConnector.get\_rfq exactly once.
        

Tests mock ManagerConnector; no live HTTP.

### 2.5 Review checkpoint

*   StageController.resolve\_stage never raises to the caller — all upstream failures degrade gracefully.
    
*   Manager is called at most once per resolve\_stage invocation.
    
*   StageResolution exposes rfq\_detail so Step 4 can implement intra-turn reuse.
    
*   Tests green.
    

### 2.6 Pack references

§A.1, §A.2, §A.3, §A.5, §F.2, §F.5.

Step 3 — Role resolution controller
-----------------------------------

### 3.1 Files

*   **Create** src/controllers/role\_controller.py
    

### 3.2 Responsibilities

Defines RoleController. Single public method:

python

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   def resolve_role(self, session: ChatbotSession) -> RoleResolution:   `

Behavior:

1.  Read session.role as stored.
    
2.  If session.role is in ROLE\_PROFILES, return RoleResolution(role=session.role, profile=ROLE\_PROFILES\[session.role\], fallback\_used=False, original\_role=session.role).
    
3.  Otherwise, return RoleResolution(role=FALLBACK\_ROLE, profile=ROLE\_PROFILES\[FALLBACK\_ROLE\], fallback\_used=True, original\_role=session.role). (Pack §B.2)
    

No manager call, no intelligence call, no Azure OpenAI call. Pure in-process resolution.

RoleResolution is a small Pydantic model or dataclass with exactly those four fields. original\_role may be None or any string; it is preserved for logging.

### 3.3 Dependencies

*   Step 1 complete (role\_profiles.py exists).
    

### 3.4 Tests to add

*   **Create** tests/unit/controllers/test\_role\_controller.py
    
    *   session.role == "estimation\_dept\_lead" → resolves to that profile, fallback\_used=False.
        
    *   session.role == "executive" → resolves to that profile, fallback\_used=False.
        
    *   session.role == "estimator" (historical) → fallback, fallback\_used=True, original\_role="estimator".
        
    *   session.role == "" → fallback, fallback\_used=True.
        
    *   session.role = some random string → fallback.
        
    *   Case sensitivity: session.role == "Executive" → fallback (profile names are lowercase exact match).
        

### 3.5 Review checkpoint

*   Exactly two profiles are recognized.
    
*   Fallback is estimation\_dept\_lead, not executive.
    
*   original\_role is preserved in the resolution output for logging in Step 6.
    
*   No external calls.
    

### 3.6 Pack references

§B.1, §B.2, §B.4.

Step 4 — ToolController surgery
-------------------------------

### 4.1 Files

*   **Modify** src/controllers/tool\_controller.py
    

### 4.2 Responsibilities

This is the largest single change in Phase 5. It has four sub-parts, which **must ship together** in one PR because they jointly maintain the tool planner's invariants.

**4.2.a — Delete the unsupported\_keywords tuple and its 422 branch.** (Pack §C.4)

Remove the unsupported\_keywords class attribute. Remove the if any(keyword in normalized for keyword in self.unsupported\_keywords): raise UnprocessableEntityError(...) block in \_plan\_tool\_use.

**4.2.b — Add capability-status pre-check.** (Pack §D.2)

Before the keyword-matching logic in \_plan\_tool\_use, check whether any entry in CAPABILITY\_STATUS\_ENTRIES matches the normalized user content. If one matches:

*   Short-circuit the planner.
    
*   Return a sentinel value (e.g., CapabilityStatusHit(capability\_name=..., named\_future\_condition=...)) that ToolController.maybe\_execute\_retrieval recognizes.
    
*   maybe\_execute\_retrieval then emits a ToolCallRecord whose result is a ToolResultEnvelope with confidence=ConfidenceLevel.ABSENT and no source\_ref (the existing envelope validator permits absent with no source\_ref — verify this holds).
    

Capability-status match takes precedence over all other keyword matches. If a user content matches both a capability-status entry and a regular keyword, capability-status wins. No retrieval fires.

**4.2.c — Add subtractive gating via intersection.** (Pack §C.1, §C.2, §C.3)

Change the signature of maybe\_execute\_retrieval to accept the resolved stage profile and role profile. In terms of behavior:

1.  Run the existing keyword router. Produce the set of matched tool names.
    
2.  Subtract tools not in stage\_profile.tool\_allow\_list.
    
3.  Subtract tools not in role\_profile.tool\_allow\_list.
    
4.  If the resulting set is empty and the original keyword match was non-empty, the turn proceeds without retrieval. No tool call, no error. (This is a Confidence State A deterministic answer without backing — acceptable per Pack §C.2 last paragraph.)
    
5.  If multiple distinct tool _families_ remain after gating, raise the existing ambiguous 422 — this path is retained. (Pack §C.4 second paragraph)
    

**4.2.d — Support intra-turn reuse of ManagerRfqDetail.** (Pack §F.2)

maybe\_execute\_retrieval accepts an optional preloaded\_rfq\_detail: ManagerRfqDetail | None argument. If the planner selects get\_rfq\_profile and preloaded\_rfq\_detail is not None, the tool function constructs a ToolResultEnvelope from the preloaded data instead of calling ManagerConnector.get\_rfq a second time.

The envelope must be indistinguishable from a fresh-fetch envelope in confidence, source\_ref.system, source\_ref.artifact, source\_ref.locator, and source\_ref.parsed\_at fields. Downstream tests should not be able to tell the difference.

Intra-turn reuse applies **only** to get\_rfq\_profile / ManagerRfqDetail. get\_rfq\_stage and get\_rfq\_snapshot fetch normally. (Pack §F.3)

### 4.3 Dependencies

*   Step 1 complete (capability\_status.py exists).
    
*   Step 2 complete (StageController produces rfq\_detail for reuse).
    
*   Step 3 complete (RoleController produces role\_profile).
    

### 4.4 Tests to add

**Modify** tests/unit/controllers/test\_tool\_controller.py (file may or may not exist today; create if needed):

*   Capability-status hit: user says "what's the briefing?" → returns CapabilityStatusHit, no manager or intelligence call made.
    
*   Capability-status precedence: user says "what's the briefing stage?" → capability-status wins, no get\_rfq\_stage call.
    
*   All Phase 4 unsupported\_keywords now route to capability-status, not 422. (One test per keyword is overkill; a parametrized test covering the full set is sufficient.)
    
*   Keyword match with full allow-lists → tool selected, retrieval fires.
    
*   Keyword match with stage subtraction → tool not selected, no retrieval, no error.
    
*   Keyword match with role subtraction → tool not selected, no retrieval, no error.
    
*   Keyword match surviving both gates → tool selected.
    
*   Multiple tool families match, all survive gating → 422 ambiguous (existing behavior retained).
    
*   get\_rfq\_profile selected with preloaded\_rfq\_detail provided → no second manager call, envelope equivalent to fresh fetch.
    
*   get\_rfq\_stage selected with preloaded\_rfq\_detail provided → manager call fires anyway (confirming intra-turn reuse is ManagerRfqDetail-only).
    
*   Portfolio session with preloaded\_rfq\_detail=None and retrieval-needing question → existing 422 "retrieval requires RFQ-bound session" path still fires.
    

### 4.5 Review checkpoint

*   unsupported\_keywords tuple is deleted.
    
*   The Phase 4 "This retrieval request is not supported in Phase 4 yet" error string does not appear anywhere in the codebase (grep check).
    
*   Capability-status takes precedence over keyword routing.
    
*   Intersection rule is implemented literally: keyword\_matches & stage.tool\_allow\_list & role.tool\_allow\_list.
    
*   Intra-turn reuse is scoped to ManagerRfqDetail only.
    
*   The existing ambiguous-422 path is preserved.
    
*   Tests green.
    

### 4.6 Pack references

§C.1, §C.2, §C.3, §C.4, §D.2, §F.2, §F.3.

Step 5 — ContextBuilder restructure
-----------------------------------

### 5.1 Files

*   **Modify** src/controllers/context\_builder.py
    

### 5.2 Responsibilities

Restructure ContextBuilder.build to compose the prompt per Pack §E.2.

**5.2.a — Preserve PromptEnvelope public shape.** (Pack §E.1)

The Pydantic class PromptEnvelope at src/models/prompt.py is not modified. Field names remain stable\_prefix, variable\_suffix, total\_budget. No new fields, no renames. This is a hard contract check at step-end (Pack §12 acceptance #6).

**5.2.b — Change the build signature.** (Pack §E.2)

New signature:

python

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   def build(      self,      recent_messages,      retrieval_context_blocks,      latest_user_turn,      stage_resolution: StageResolution,      role_resolution: RoleResolution,      any_pattern_based_tool_fired: bool,      capability_status_hit: CapabilityStatusHit | None,  ) -> PromptEnvelope:   `

**5.2.c — Assemble stable\_prefix in the locked order.** (Pack §E.2)

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   [base system prompt]  [role framing — tone_directive + depth_directive]  [stage framing — prompt_frame_fragment + optional current_stage_name reference]  [confidence-rendering directives]   `

The confidence-rendering directives include:

*   If capability\_status\_hit is not None: instruction to produce the absence-template response (Pack §D.4), naming the capability and the future condition from the hit payload. Do not invent.
    
*   Else if any\_pattern\_based\_tool\_fired: instruction to emit exactly the literal trailing line Confidence: pattern-based (validated against 1 sample) as the last line of the response. (Pack §D.3)
    
*   Else: instruction to emit no confidence marker.
    

The instructions are literal strings in the prefix. No templating engine, no conditional code-gen.

**5.2.d — Assemble variable\_suffix as today.** (Pack §E.2)

Recent history → retrieval context blocks → latest user turn → assistant: trailer. This is the existing composition; only stable\_prefix changes materially in Phase 5.

### 5.3 Dependencies

*   Step 2 complete (StageResolution type exists).
    
*   Step 3 complete (RoleResolution type exists).
    
*   Step 4 complete (CapabilityStatusHit type exists).
    

### 5.4 Tests to add

**Modify** tests/unit/controllers/test\_context\_builder.py (create if absent):

*   With RoleResolution(role="executive") vs RoleResolution(role="estimation\_dept\_lead"), the stable\_prefix contains role-specific directives that differ textually between the two.
    
*   With two different StageResolution values having distinct prompt\_frame\_fragment strings, stable\_prefix differs.
    
*   With any\_pattern\_based\_tool\_fired=True, stable\_prefix contains a directive that includes the literal string Confidence: pattern-based (validated against 1 sample).
    
*   With any\_pattern\_based\_tool\_fired=False, stable\_prefix does not instruct the LLM to emit the confidence marker.
    
*   With capability\_status\_hit set, stable\_prefix contains the absence-template directive and names the capability; no retrieval blocks appear in variable\_suffix.
    
*   variable\_suffix composition matches Phase 4 behavior for history, retrieval, and user turn when no new signals are present.
    
*   PromptEnvelope returned still has exactly three fields: stable\_prefix, variable\_suffix, total\_budget. (Hard contract check.)
    

### 5.5 Review checkpoint

*   src/models/prompt.py is byte-identical between Phase 4 and Phase 5. git diff shows no changes.
    
*   Role framing, stage framing, and confidence directives appear in stable\_prefix, not in variable\_suffix. (Cache-friendliness invariant.)
    
*   No post-processing of LLM output anywhere. The confidence marker is emitted _by the LLM_, not appended.
    
*   Tests green.
    

### 5.6 Pack references

§E.1, §E.2, §E.3, §D.3, §D.4, §D.5, §12 (acceptance #6).

Step 6 — ChatController rewiring + observability
------------------------------------------------

### 6.1 Files

*   **Modify** src/controllers/chat\_controller.py
    
*   **Modify** src/app\_context.py (dependency wiring for the two new controllers)
    

### 6.2 Responsibilities

This is the step that ties everything together. Two sub-parts that ship together.

**6.2.a — Update ChatController.\_\_init\_\_ and handle\_turn to the Pack §G.1 pipeline order.**

New constructor dependencies: StageController, RoleController. These are injected via app\_context.py following the existing FastAPI Depends pattern.

New handle\_turn sequence:

python

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   def handle_turn(self, session_id, command):      # 1. Load session (existing)      session = self.session_datasource.get_by_id(session_id)      if not session: raise NotFoundError(...)      # 2. Get-or-create conversation (existing)      conversation = self.conversation_controller.get_or_create_conversation_for_session(session.id)      # 3. Resolve stage (NEW, proactive)      stage_resolution = self.stage_controller.resolve_stage(session)      log_structured("phase5.stage_resolved", ...)      # 4. Resolve role (NEW)      role_resolution = self.role_controller.resolve_role(session)      log_structured("phase5.role_applied", role_resolution.role)      log_structured("phase5.role_fallback_used", role_resolution.fallback_used)      if role_resolution.fallback_used:          log_structured("phase5.role_original", role_resolution.original_role)      # 5. Tool planner with gating and preloaded detail      tool_call_records, capability_status_hit = self.tool_controller.maybe_execute_retrieval(          session,          command.content,          stage_profile=stage_resolution.profile,          role_profile=role_resolution.profile,          preloaded_rfq_detail=stage_resolution.rfq_detail,      )      # (logging of tools_keyword_matched / tools_allowed_after_stage / tools_allowed_after_role / capability_status_hit      #  is emitted from within ToolController — see §6.2.c)      # 6. Fetch recent history (existing)      recent_messages = self.conversation_controller.get_recent_history(...)      # 7. Persist user message (existing)      self.conversation_controller.create_user_message(...)      # 8. Build prompt with new signals      any_pattern_based = any(          r.result and r.result.confidence == ConfidenceLevel.PATTERN_1_SAMPLE          for r in tool_call_records      )      prompt_envelope = self.context_builder.build(          recent_messages,          tool_call_records_to_prompt_blocks(tool_call_records),          latest_user_turn=command.content,          stage_resolution=stage_resolution,          role_resolution=role_resolution,          any_pattern_based_tool_fired=any_pattern_based,          capability_status_hit=capability_status_hit,      )      # 9. Azure OpenAI call (existing)      completion = self.azure_openai_connector.create_chat_completion(          self._build_azure_messages(prompt_envelope)      )      # 10. Persist assistant message (existing, but with marker log)      log_structured(          "phase5.confidence_marker_emitted",          "Confidence: pattern-based (validated against 1 sample)" in completion.assistant_text,      )      assistant_message = self.conversation_controller.create_assistant_message(...)      # 11. Return (existing)      return to_turn_response(conversation.id, assistant_message)   `

**6.2.b — Update app\_context.py wiring.**

Add:

python

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   def get_stage_controller(      manager_connector: ManagerConnector = Depends(get_manager_connector),  ) -> StageController:      return StageController(manager_connector=manager_connector)  def get_role_controller() -> RoleController:      return RoleController()   `

Extend get\_chat\_controller to inject the two new controllers.

**6.2.c — Observability: emit the eight Pack §H.2 log fields.**

Exact field names and emission points:

FieldEmitted inWhenphase5.stage\_resolvedStageController.resolve\_stageAt end of method, alwaysphase5.role\_appliedChatController.handle\_turn after role stepAlwaysphase5.role\_fallback\_usedChatController.handle\_turn after role stepAlwaysphase5.role\_originalChatController.handle\_turn after role stepOnly when fallback usedphase5.tools\_keyword\_matchedToolController.maybe\_execute\_retrievalAfter keyword matchingphase5.tools\_allowed\_after\_stageToolController.maybe\_execute\_retrievalAfter stage intersectionphase5.tools\_allowed\_after\_roleToolController.maybe\_execute\_retrievalAfter role intersectionphase5.capability\_status\_hitToolController.maybe\_execute\_retrievalOnly when capability-status firesphase5.confidence\_marker\_emittedChatController.handle\_turn after LLM callAlways

Logging uses the existing logging framework with key-value extras. No new logging infrastructure.

### 6.3 Dependencies

*   Steps 1–5 all complete and merged.
    

### 6.4 Tests to add

**Modify** tests/integration/test\_chat\_turn\_pipeline.py (create if absent):

*   Full pipeline test: portfolio session, simple greeting → returns 200, no retrieval, no manager calls, no marker emitted.
    
*   Full pipeline test: RFQ-bound session, question matching get\_rfq\_profile keywords → StageController fetches ManagerRfqDetail once, planner reuses it (manager called exactly once total).
    
*   Full pipeline test: RFQ-bound session, capability-status keyword → no manager/intelligence calls, assistant response follows absence template shape.
    
*   Full pipeline test: manager 503 on stage resolution, user greeting → 200 response, default profile applied, turn completes.
    
*   Full pipeline test: manager 503 on stage resolution, user asks about deadline → now the retrieval also fails (no reuse possible), surfaces 503 through the normal error path (not swallowed silently).
    
*   Log field test: every decision point in §6.2.c table emits its expected field for a standard RFQ-bound turn.
    

### 6.5 Review checkpoint

*   handle\_turn executes in the Pack §G.1 order — verifiable by reading the method top-to-bottom.
    
*   Tool planner receives both resolved profiles and the preloaded detail.
    
*   ContextBuilder.build receives all five new signals.
    
*   All eight Pack §H.2 log fields are emitted at the specified points.
    
*   No new HTTP response fields.
    
*   Existing Phase 4 contract tests still pass unchanged.
    
*   Tests green.
    

### 6.6 Pack references

§F.2, §G.1, §G.2, §H.1, §H.2, §H.3.

Step 7 — Pytest integration scenarios (Pack §J.2)
-------------------------------------------------

### 7.1 Files

*   **Create** tests/integration/test\_phase5\_scenarios.py
    

### 7.2 Responsibilities

One test function per scenario in Pack §J.2. Each test uses the full FastAPI TestClient against the composed app with mocked manager, intelligence, and Azure OpenAI connectors.

**Scenario 1 — Role contrast.** Create two sessions with different roles on the same RFQ. Post the same turn content to both. Assert:

*   Both returns are 200.
    
*   Both responses carry identical source\_refs\[\].
    
*   The two assistant response strings differ (a simple inequality assertion is sufficient as a first pass; content-specific assertions come from mocking the Azure OpenAI connector to echo the received system prompt).
    
*   Log capture shows different phase5.role\_applied values across the two turns.
    

**Scenario 2 — Stage contrast.** Configure two RFQs with distinct current\_stage\_id values known to STAGE\_PROFILES. Same user question. Assert different phase5.stage\_resolved values and different system prompts.

**Scenario 3 — Confidence marker presence and absence.** Mock IntelligenceConnector.get\_snapshot and ManagerConnector.get\_rfq. For a question selecting get\_rfq\_snapshot, have the mocked LLM respond with the literal marker; assert it's present and phase5.confidence\_marker\_emitted=true. For a question selecting get\_rfq\_profile, have the mocked LLM respond without the marker; assert absence and phase5.confidence\_marker\_emitted=false.

**Scenario 4 — Capability-status absence.** Post "what's the briefing?". Assert:

*   HTTP 200 (not 422).
    
*   No manager or intelligence mock was invoked.
    
*   phase5.capability\_status\_hit="briefing" (or whatever the configured capability name is for that keyword) appears in logs.
    
*   The mocked LLM received a prompt containing the absence-template directive and the future condition string.
    

**Scenario 5 — Trivial no-retrieval turn.** Post a greeting. Assert 200, empty source\_refs\[\], no marker, no manager/intelligence calls.

**Scenario 6 — Graceful degradation.** Configure ManagerConnector.get\_rfq mock to raise UpstreamServiceError. Post a greeting. Assert 200, default stage profile visible in prompt, phase5.stage\_resolved logs the failure reason.

### 7.3 Dependencies

*   Step 6 complete.
    

### 7.4 Review checkpoint

*   All six scenarios pass in CI.
    
*   Tests use mocks, not live services. No environment-dependent tests.
    
*   Tests are deterministic — no flakiness from ordering, timing, or randomness.
    

### 7.5 Pack references

§J.1, §J.2.

Step 8 — Postman demo beats
---------------------------

### 8.1 Files

*   **Modify** the existing rfq\_chatbot\_ms Postman demo collection (path as per existing convention; the Blueprint defers to how the current collection is stored).
    

### 8.2 Responsibilities

Add demo beats corresponding to each of the six pytest scenarios. The demo beats must:

*   Run against a locally composed stack: rfq\_chatbot\_ms + rfq\_manager\_ms + rfq\_intelligence\_ms + the real rfq\_chatbot\_db.
    
*   Use the golden reference RFQ (SA-AYPP-6-MR-022-derived test data in manager) so stage IDs are real.
    
*   Run end-to-end with no manual intervention between steps (Pack §12 acceptance #10).
    
*   Include Postman test scripts that assert the key observable outcome for each scenario — at minimum the HTTP status and the presence/absence of the confidence marker in response bodies.
    

For Scenario 6 (graceful degradation), the demo beat must be documented with the manual pre-step needed to simulate manager 503 (e.g., "stop the manager container, run this turn, restart manager"). If that manual pre-step is present, the rest of the scenario proceeds without intervention.

### 8.3 Dependencies

*   Step 7 complete and green.
    

### 8.4 Review checkpoint

*   All six beats runnable in a single Postman collection run.
    
*   Each beat has at least one Postman test assertion.
    
*   The collection's pre-request scripts cover any setup state needed (session creation, RFQ binding).
    
*   A fresh clone of the repo + a fresh database + the golden manager RFQ should be enough to run the collection end-to-end.
    

### 8.5 Pack references

§J.1, §12 (acceptance #2, #10).

Step 9 — Documentation
----------------------

### 9.1 Files

*   **Modify** CLAUDE.md (root-level for rfq\_chatbot\_ms)
    
*   **Modify** README.md
    
*   **Verify** docs/rfq\_chatbot\_ms\_architecture\_brief\_v2\_F.html alignment — no edit if already aligned; flag a finding if not.
    
*   **Verify** docs/implementation\_plan\_chatbot.md alignment.
    
*   **Do not touch** docs/rfq\_chatbot\_ms\_openapi\_current.yaml or docs/rfq\_chatbot\_ms\_api\_contract\_current.html. These should require zero changes, and that's a Phase 5 acceptance gate (Pack §12 acceptance #7).
    

### 9.2 Responsibilities

CLAUDE.md additions:

*   A "Phase 5 behaviors" section listing the nine frozen postures from Pack §0.
    
*   A "What not to do in rfq\_chatbot\_ms" section adding: no new endpoint, no DTO change, no YAML/DB config for stage or role profiles, no intent classification, no multi-tool turns, no Mode B code changes.
    
*   Pointer to this Blueprint and the Pack for canonical decisions.
    

README.md additions:

*   A short paragraph under "What this service does" acknowledging Phase 5 behaviors (stage-aware, role-aware, confidence-aware).
    
*   A STAGE\_PROFILES and ROLE\_PROFILES configuration note pointing to the config modules.
    

Alignment verification: open the brief and the implementation plan, read the Phase 5 sections, confirm they do not promise anything outside the Pack's scope fences. If they do, raise the discrepancy as a finding — do not silently edit the brief.

### 9.3 Dependencies

*   Step 8 complete.
    

### 9.4 Review checkpoint

*   OpenAPI YAML and HTML contract unchanged (hard check).
    
*   CLAUDE.md explicitly names the Phase 6 fences so future agents don't cross them.
    
*   No brief or plan changes without explicit reviewer approval.
    

### 9.5 Pack references

§12 (acceptance #7); all scope fences.

10\. Cross-cutting review checkpoints (applied after every step)
----------------------------------------------------------------

These are not per-step reviews; they are invariants the reviewer checks on every PR regardless of which step it implements.

1.  **No contract change.** git diff on src/models/prompt.py, src/models/turn.py, src/models/session.py, src/models/envelope.py, src/models/conversation.py, docs/rfq\_chatbot\_ms\_openapi\_current.yaml, docs/rfq\_chatbot\_ms\_api\_contract\_current.html shows no functional changes. (Docstrings or typo fixes don't count as functional.)
    
2.  **No Mode B code change.** git diff on paths matching portfolio or SessionEntryMode.GLOBAL handling shows no Phase 5 changes.
    
3.  **No new endpoint.** git grep -E '@router\\.(get|post|patch|put|delete)' shows the same set of decorators as Phase 4.
    
4.  **No unsupported\_keywords artifact remains.** git grep 'unsupported\_keywords' returns nothing after Step 4.
    
5.  **No LLM post-processing.** git grep on src/controllers/chat\_controller.py shows no string manipulation of completion.assistant\_text before persistence (other than stripping whitespace, which is existing behavior in the connector).
    
6.  **Confidence marker is literal.** git grep 'Confidence: pattern-based' returns matches only in prompt instructions and test assertions, not in response-rewriting code.
    
7.  **Persona count is two.** git grep on ROLE\_PROFILES shows exactly two keys.
    
8.  **Eight log fields exist, no more, no less.** git grep 'phase5\\.' shows exactly the Pack §H.2 field names (plus phase5.role\_original when fallback is used — nine identifiers total, since role\_original is conditional).
    

11\. Sequencing and parallelism
-------------------------------

Steps 1–3 have no mutual dependencies other than Step 1 coming first, so Steps 2 and 3 _could_ be parallelized by two implementers. However, for review simplicity, running them sequentially is recommended. Steps 4 onward are strictly sequential.

No step may be partially shipped. Each step either merges complete or does not merge. "I've got stage resolution working but haven't added the graceful-degradation case yet" is not acceptable — that's two half-steps, and they should have been split into two steps at Blueprint time if they were two.

The correctness-critical pipeline-order change from Pack §G.1 lands in Step 6 and is the highest-risk merge. It gets two reviewers minimum. Steps 1–5 lay foundation; Step 6 is the phase-defining change; Steps 7–9 are verification and documentation.

12\. When Phase 5 is done
-------------------------

Phase 5 is done when Pack §12's ten acceptance criteria all hold. Restated here for the Blueprint's close-out checklist:

*   All six scenarios pass as pytest integration tests in CI.
    
*   All six scenarios exist as executable Postman demo beats.
    
*   All nine log identifiers (eight always-on + phase5.role\_original conditional) appear in logs.
    
*   unsupported\_keywords tuple and its 422 branch deleted.
    
*   src/config/stage\_profiles.py and src/config/role\_profiles.py exist with the required structure.
    
*   PromptEnvelope Pydantic class byte-identical to Phase 4.
    
*   OpenAPI YAML requires no changes.
    
*   No code changes on Mode B paths.
    
*   Existing Phase 4 demo beats still pass unchanged.
    
*   Full six-beat demo runnable end-to-end without manual intervention (except documented Scenario 6 pre-step).
    

When all ten hold, Phase 5 Mode A ships. The Blueprint closes. The next phase — Phase 6 — starts from a known-good baseline.