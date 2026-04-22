"""Normalized RFQ response planning and grounded rfq_specific composition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal
import uuid

from src.connectors.intelligence_connector import IntelligenceSnapshotArtifact
from src.connectors.manager_connector import (
    ManagerRfqDetail,
    ManagerRfqStage,
    ManagerRfqStageListResponse,
)
from src.models.conversation import ToolCallRecord
from src.models.envelope import ConfidenceLevel, SourceRef
from src.tools.common.envelope import build_tool_result_envelope


RfqResponseMode = Literal["FACT_FIELD", "RFQ_SUMMARY", "RFQ_DETAIL", "RFQ_ADVISORY"]
AdvisoryFocus = Literal["watchouts", "risks", "missing", "attention"]


@dataclass(frozen=True)
class UnifiedStageView:
    """Normalized current-stage view."""

    name: str | None
    assigned_team: str | None
    status: str | None
    blocker_status: str | None
    blocker_reason_code: str | None


@dataclass(frozen=True)
class UnifiedSnapshotView:
    """Normalized intelligence snapshot view."""

    overall_status: str | None
    briefing_status: str | None
    briefing_summary: str | None
    briefing_missing_info: tuple[str, ...]
    intake_status: str | None
    intake_key_gaps: tuple[str, ...]
    workbook_status: str | None
    review_status: str | None
    active_findings_count: int
    analytical_status: str | None
    analytical_notes: tuple[str, ...]
    historical_readiness: bool
    outcome_status: str | None
    outcome_reason: str | None
    requires_human_review: bool


@dataclass(frozen=True)
class UnifiedRfqView:
    """Single normalized RFQ view used for grounded answer composition."""

    rfq_id: uuid.UUID | None
    rfq_code: str | None
    name: str | None
    client: str | None
    status: str | None
    progress: int | None
    deadline: date | None
    current_stage_name: str | None
    workflow_name: str | None
    industry: str | None
    country: str | None
    priority: str | None
    owner: str | None
    description: str | None
    source_package_available: bool | None
    workbook_available: bool | None
    profile_outcome_reason: str | None
    stage: UnifiedStageView | None
    snapshot: UnifiedSnapshotView | None
    profile_source_ref: SourceRef | None
    stage_source_ref: SourceRef | None
    snapshot_source_ref: SourceRef | None


@dataclass(frozen=True)
class ResponseModeSelection:
    """Deterministic RFQ response-mode choice."""

    mode: RfqResponseMode
    advisory_focus: AdvisoryFocus | None = None


@dataclass(frozen=True)
class RfqResponsePlan:
    """Deterministic grounded RFQ response plus persistence payload."""

    response_mode: RfqResponseMode
    assistant_text: str
    grounded: bool
    source_refs: list[SourceRef]
    tool_call_records: list[ToolCallRecord]


class RfqResponseController:
    """Build a unified RFQ view and compose grounded rfq_specific answers."""

    ready_statuses = frozenset({"ready", "available", "complete", "completed"})
    clear_blocker_statuses = frozenset({"clear", "none", "not_blocked", "not blocked"})

    owner_terms = ("owner", "owns", "responsible", "point of contact")
    deadline_terms = ("deadline", "due date", "due")
    status_terms = ("status",)
    progress_terms = ("progress", "complete", "completion")
    client_terms = ("client",)
    workflow_terms = ("workflow",)
    priority_terms = ("priority",)
    country_terms = ("country", "location")
    industry_terms = ("industry",)
    rfq_code_terms = ("rfq code", "reference code")
    lifecycle_terms = ("lifecycle", "lifecycle state")
    stage_terms = ("stage", "assigned team", "team", "blocker", "blocked")
    detail_terms = (
        "snapshot",
        "currently known",
        "current details",
        "current detail",
        "current information",
        "current info",
        "known about this rfq",
        "details about this rfq",
        "briefing",
        "intelligence",
        "detailed view",
        "full details",
    )
    summary_terms = (
        "tell me about",
        "overview",
        "summary",
        "summarize",
        "about this rfq",
        "about the rfq",
    )
    advisory_watchout_terms = ("watch out", "watch for", "be careful", "pay attention")
    advisory_risk_terms = ("risk", "risks", "concern", "concerns")
    advisory_missing_terms = (
        "missing",
        "incomplete",
        "gap",
        "gaps",
        "what is missing",
        "what's missing",
    )
    advisory_attention_terms = (
        "needs attention",
        "need attention",
        "attention right now",
        "needs focus",
        "what needs attention",
    )

    def compose_response(
        self,
        *,
        user_content: str,
        rfq_detail: ManagerRfqDetail | None,
        tool_call_records: list[ToolCallRecord],
        rfq_id: str | uuid.UUID | None,
    ) -> RfqResponsePlan:
        normalized_tool_call_records = self._ensure_primary_profile_record(
            rfq_detail=rfq_detail,
            tool_call_records=tool_call_records,
            rfq_id=rfq_id,
        )
        unified_view = self._build_unified_view(
            rfq_detail=rfq_detail,
            tool_call_records=normalized_tool_call_records,
        )
        normalized_content = " ".join(user_content.lower().split())
        selection = self._select_response_mode(normalized_content)
        assistant_text, source_refs = self._render_for_mode(
            selection=selection,
            normalized_content=normalized_content,
            unified_view=unified_view,
        )
        return RfqResponsePlan(
            response_mode=selection.mode,
            assistant_text=assistant_text,
            grounded=bool(source_refs),
            source_refs=source_refs,
            tool_call_records=normalized_tool_call_records,
        )

    def _ensure_primary_profile_record(
        self,
        *,
        rfq_detail: ManagerRfqDetail | None,
        tool_call_records: list[ToolCallRecord],
        rfq_id: str | uuid.UUID | None,
    ) -> list[ToolCallRecord]:
        if rfq_detail is None:
            return tool_call_records

        if any(
            record.tool_name == "get_rfq_profile"
            and record.result is not None
            and record.result.confidence != ConfidenceLevel.ABSENT
            for record in tool_call_records
        ):
            return tool_call_records

        effective_rfq_id = getattr(rfq_detail, "id", None) or self._coerce_uuid(rfq_id)
        if effective_rfq_id is None:
            return tool_call_records

        result = build_tool_result_envelope(
            value=rfq_detail,
            system="rfq_manager_ms",
            artifact="rfq",
            locator=f"/rfq-manager/v1/rfqs/{effective_rfq_id}",
            parsed_at=rfq_detail.updated_at,
            confidence=ConfidenceLevel.DETERMINISTIC,
        )
        return [
            ToolCallRecord(
                tool_name="get_rfq_profile",
                arguments={
                    "rfq_id": str(effective_rfq_id),
                    "selection_reason": "Primary RFQ profile normalization source",
                },
                result=result,
                source_refs=[result.source_ref] if result.source_ref else [],
            ),
            *tool_call_records,
        ]

    def _build_unified_view(
        self,
        *,
        rfq_detail: ManagerRfqDetail | None,
        tool_call_records: list[ToolCallRecord],
    ) -> UnifiedRfqView:
        profile_record = self._latest_record(tool_call_records, "get_rfq_profile")
        stage_record = self._latest_record(tool_call_records, "get_rfq_stage")
        snapshot_record = self._latest_record(tool_call_records, "get_rfq_snapshot")

        profile = rfq_detail or self._coerce_profile(
            getattr(profile_record.result, "value", None) if profile_record and profile_record.result else None
        )
        stage_list = self._coerce_stage_list(
            getattr(stage_record.result, "value", None) if stage_record and stage_record.result else None
        )
        snapshot = self._coerce_snapshot(
            getattr(snapshot_record.result, "value", None) if snapshot_record and snapshot_record.result else None
        )

        current_stage = self._select_current_stage(profile=profile, stage_list=stage_list)
        profile_source_ref = (
            profile_record.result.source_ref
            if profile_record and profile_record.result and profile_record.result.source_ref
            else None
        )
        stage_source_ref = (
            stage_record.result.source_ref
            if stage_record and stage_record.result and stage_record.result.source_ref
            else None
        )
        snapshot_source_ref = (
            snapshot_record.result.source_ref
            if snapshot_record and snapshot_record.result and snapshot_record.result.source_ref
            else None
        )

        return UnifiedRfqView(
            rfq_id=getattr(profile, "id", None) or getattr(snapshot, "rfq_id", None),
            rfq_code=getattr(profile, "rfq_code", None)
            or self._snapshot_summary_value(snapshot, "rfq_code"),
            name=getattr(profile, "name", None)
            or self._snapshot_summary_value(snapshot, "project_title"),
            client=getattr(profile, "client", None)
            or self._snapshot_summary_value(snapshot, "client_name"),
            status=getattr(profile, "status", None),
            progress=getattr(profile, "progress", None),
            deadline=getattr(profile, "deadline", None),
            current_stage_name=getattr(profile, "current_stage_name", None)
            or getattr(current_stage, "name", None),
            workflow_name=getattr(profile, "workflow_name", None),
            industry=getattr(profile, "industry", None),
            country=getattr(profile, "country", None),
            priority=getattr(profile, "priority", None),
            owner=getattr(profile, "owner", None),
            description=getattr(profile, "description", None),
            source_package_available=getattr(profile, "source_package_available", None),
            workbook_available=getattr(profile, "workbook_available", None),
            profile_outcome_reason=getattr(profile, "outcome_reason", None),
            stage=(
                UnifiedStageView(
                    name=current_stage.name,
                    assigned_team=current_stage.assigned_team,
                    status=current_stage.status,
                    blocker_status=current_stage.blocker_status,
                    blocker_reason_code=current_stage.blocker_reason_code,
                )
                if current_stage is not None
                else None
            ),
            snapshot=(
                UnifiedSnapshotView(
                    overall_status=snapshot.content.overall_status,
                    briefing_status=snapshot.content.briefing_panel_summary.status,
                    briefing_summary=snapshot.content.briefing_panel_summary.executive_summary,
                    briefing_missing_info=tuple(snapshot.content.briefing_panel_summary.missing_info),
                    intake_status=snapshot.content.intake_panel_summary.status,
                    intake_key_gaps=tuple(snapshot.content.intake_panel_summary.key_gaps),
                    workbook_status=snapshot.content.workbook_panel.status,
                    review_status=snapshot.content.review_panel.status,
                    active_findings_count=snapshot.content.review_panel.active_findings_count,
                    analytical_status=snapshot.content.analytical_status_summary.status,
                    analytical_notes=tuple(snapshot.content.analytical_status_summary.notes),
                    historical_readiness=snapshot.content.analytical_status_summary.historical_readiness,
                    outcome_status=snapshot.content.outcome_summary.status,
                    outcome_reason=snapshot.content.outcome_summary.reason,
                    requires_human_review=snapshot.content.requires_human_review,
                )
                if snapshot is not None
                else None
            ),
            profile_source_ref=profile_source_ref,
            stage_source_ref=stage_source_ref,
            snapshot_source_ref=snapshot_source_ref,
        )

    def _select_response_mode(self, normalized_content: str) -> ResponseModeSelection:
        if self._contains_any(normalized_content, self.advisory_missing_terms):
            return ResponseModeSelection(mode="RFQ_ADVISORY", advisory_focus="missing")
        if self._contains_any(normalized_content, self.advisory_attention_terms):
            return ResponseModeSelection(mode="RFQ_ADVISORY", advisory_focus="attention")
        if self._contains_any(normalized_content, self.advisory_watchout_terms):
            return ResponseModeSelection(mode="RFQ_ADVISORY", advisory_focus="watchouts")
        if self._contains_any(normalized_content, self.advisory_risk_terms):
            return ResponseModeSelection(mode="RFQ_ADVISORY", advisory_focus="risks")
        if self._is_detail_request(normalized_content):
            return ResponseModeSelection(mode="RFQ_DETAIL")
        if self._is_summary_request(normalized_content):
            return ResponseModeSelection(mode="RFQ_SUMMARY")
        if self._is_fact_field_request(normalized_content):
            return ResponseModeSelection(mode="FACT_FIELD")
        return ResponseModeSelection(mode="RFQ_SUMMARY")

    def _render_for_mode(
        self,
        *,
        selection: ResponseModeSelection,
        normalized_content: str,
        unified_view: UnifiedRfqView,
    ) -> tuple[str, list[SourceRef]]:
        if selection.mode == "FACT_FIELD":
            return self._render_fact_field(
                normalized_content=normalized_content,
                unified_view=unified_view,
            )
        if selection.mode == "RFQ_DETAIL":
            return self._render_detail(unified_view)
        if selection.mode == "RFQ_ADVISORY":
            return self._render_advisory(
                unified_view=unified_view,
                focus=selection.advisory_focus or "watchouts",
            )
        return self._render_summary(unified_view)

    def _render_fact_field(
        self,
        *,
        normalized_content: str,
        unified_view: UnifiedRfqView,
    ) -> tuple[str, list[SourceRef]]:
        if self._contains_any(normalized_content, self.rfq_code_terms):
            return self._render_rfq_code_answer(unified_view)

        if self._contains_any(normalized_content, self.lifecycle_terms):
            return self._render_lifecycle_answer(unified_view)

        if self._contains_any(normalized_content, self.stage_terms):
            return self._render_stage_fact_answer(
                normalized_content=normalized_content,
                unified_view=unified_view,
            )

        profile_answer = self._render_profile_answer(
            normalized_content=normalized_content,
            unified_view=unified_view,
        )
        if profile_answer is not None:
            return profile_answer

        return self._render_summary(unified_view)

    def _render_rfq_code_answer(self, unified_view: UnifiedRfqView) -> tuple[str, list[SourceRef]]:
        refs = self._dedupe_refs([unified_view.profile_source_ref, unified_view.snapshot_source_ref])
        if not unified_view.rfq_code or not refs:
            return ("I don't have grounded RFQ code data available right now.", [])
        return (f"The RFQ code is {unified_view.rfq_code}.", refs)

    def _render_lifecycle_answer(self, unified_view: UnifiedRfqView) -> tuple[str, list[SourceRef]]:
        refs = self._dedupe_refs([unified_view.profile_source_ref, unified_view.stage_source_ref])
        facts: list[str] = []
        if unified_view.status:
            facts.append(f"status is {unified_view.status}")
        if unified_view.current_stage_name:
            facts.append(f"current stage is {unified_view.current_stage_name}")
        if unified_view.progress is not None:
            facts.append(f"progress is {unified_view.progress}%")
        if not facts or not refs:
            return ("I don't have grounded RFQ lifecycle-state data available right now.", [])
        return (f"The RFQ lifecycle state is that {self._join_facts(facts)}.", refs)

    def _render_profile_answer(
        self,
        *,
        normalized_content: str,
        unified_view: UnifiedRfqView,
    ) -> tuple[str, list[SourceRef]] | None:
        requested_fields: list[tuple[str, str | None]] = []

        if self._contains_any(normalized_content, self.owner_terms):
            requested_fields.append(("owner", unified_view.owner))
        if self._contains_any(normalized_content, self.deadline_terms):
            requested_fields.append(
                ("deadline", unified_view.deadline.isoformat() if unified_view.deadline else None)
            )
        if self._contains_any(normalized_content, self.status_terms):
            requested_fields.append(("status", unified_view.status))
        if self._contains_any(normalized_content, self.progress_terms):
            requested_fields.append(
                ("progress", f"{unified_view.progress}%" if unified_view.progress is not None else None)
            )
        if self._contains_any(normalized_content, self.client_terms):
            requested_fields.append(("client", unified_view.client))
        if self._contains_any(normalized_content, self.workflow_terms):
            requested_fields.append(("workflow", unified_view.workflow_name))
        if self._contains_any(normalized_content, self.priority_terms):
            requested_fields.append(("priority", unified_view.priority))
        if self._contains_any(normalized_content, self.country_terms):
            requested_fields.append(("country", unified_view.country))
        if self._contains_any(normalized_content, self.industry_terms):
            requested_fields.append(("industry", unified_view.industry))

        if not requested_fields:
            return None

        if unified_view.profile_source_ref is None:
            labels = ", ".join(label for label, _ in requested_fields)
            return (
                f"I don't have grounded RFQ {labels} data available right now.",
                [],
            )

        answer_parts = []
        missing_parts = []
        for label, value in requested_fields:
            if value:
                answer_parts.append(self._field_sentence(label, value))
            else:
                missing_parts.append(label)

        if answer_parts and not missing_parts:
            return (" ".join(answer_parts), [unified_view.profile_source_ref])

        if answer_parts:
            missing_text = ", ".join(missing_parts)
            return (
                f"{' '.join(answer_parts)} I don't have grounded {missing_text} data for this RFQ yet.",
                [unified_view.profile_source_ref],
            )

        missing_text = ", ".join(missing_parts)
        return (
            f"I don't have grounded {missing_text} data for this RFQ right now.",
            [],
        )

    def _render_stage_fact_answer(
        self,
        *,
        normalized_content: str,
        unified_view: UnifiedRfqView,
    ) -> tuple[str, list[SourceRef]]:
        refs = self._dedupe_refs([unified_view.profile_source_ref, unified_view.stage_source_ref])
        if not refs or (unified_view.current_stage_name is None and unified_view.stage is None):
            return ("I don't have grounded current-stage data for this RFQ right now.", [])

        answer_parts: list[str] = []
        if "stage" in normalized_content and unified_view.current_stage_name:
            answer_parts.append(f"The current stage is {unified_view.current_stage_name}.")
        if "team" in normalized_content and unified_view.stage and unified_view.stage.assigned_team:
            answer_parts.append(f"The assigned team is {unified_view.stage.assigned_team}.")
        if self._contains_any(normalized_content, ("blocker", "blocked")):
            blocker_text = self._blocker_sentence(unified_view)
            if blocker_text:
                answer_parts.append(blocker_text)
            else:
                answer_parts.append("I don't have a grounded blocker signal for this RFQ right now.")

        if not answer_parts and unified_view.current_stage_name:
            answer_parts.append(f"The current stage is {unified_view.current_stage_name}.")

        return (" ".join(answer_parts), refs)

    def _render_summary(self, unified_view: UnifiedRfqView) -> tuple[str, list[SourceRef]]:
        refs = self._dedupe_refs([unified_view.profile_source_ref, unified_view.snapshot_source_ref])
        if not refs:
            return ("I don't have grounded RFQ data available right now.", [])

        lines = ["RFQ summary"]
        core_lines = self._summary_core_lines(unified_view)
        if core_lines:
            lines.extend(core_lines)

        readiness_lines = self._summary_readiness_lines(unified_view)
        if readiness_lines:
            lines.append("Readiness")
            lines.extend(readiness_lines)

        return ("\n".join(lines), refs)

    def _render_detail(self, unified_view: UnifiedRfqView) -> tuple[str, list[SourceRef]]:
        refs = self._dedupe_refs(
            [
                unified_view.profile_source_ref,
                unified_view.stage_source_ref,
                unified_view.snapshot_source_ref,
            ]
        )
        if not refs:
            return ("I don't have grounded current RFQ details available right now.", [])

        lines = ["Current RFQ details"]

        core_lines = self._detail_core_lines(unified_view)
        if core_lines:
            lines.append("Core facts")
            lines.extend(core_lines)

        execution_lines = self._detail_execution_lines(unified_view)
        if execution_lines:
            lines.append("Execution state")
            lines.extend(execution_lines)

        intelligence_lines = self._detail_intelligence_lines(unified_view)
        if intelligence_lines:
            lines.append("Intelligence state")
            lines.extend(intelligence_lines)

        gap_lines = self._detail_gap_lines(unified_view)
        if gap_lines:
            lines.append("Known gaps")
            lines.extend(gap_lines)

        return ("\n".join(lines), refs)

    def _render_advisory(
        self,
        *,
        unified_view: UnifiedRfqView,
        focus: AdvisoryFocus,
    ) -> tuple[str, list[SourceRef]]:
        sections, refs = self._derive_advisory_sections(unified_view)
        if not refs:
            return ("I don't have grounded RFQ advisory signals available right now.", [])

        ordered_sections = [
            ("Main concerns", sections["concerns"]),
            ("Missing / incomplete", sections["missing"]),
            ("What needs attention", sections["attention"]),
        ]
        if focus == "missing":
            ordered_sections = [
                ("Missing / incomplete", sections["missing"]),
                ("Main concerns", sections["concerns"]),
                ("What needs attention", sections["attention"]),
            ]
        elif focus == "attention":
            ordered_sections = [
                ("What needs attention", sections["attention"]),
                ("Main concerns", sections["concerns"]),
                ("Missing / incomplete", sections["missing"]),
            ]

        lines = ["RFQ advisory"]
        for header, bullets in ordered_sections:
            lines.append(header)
            lines.extend(f"- {bullet}" for bullet in bullets)

        return ("\n".join(lines), refs)

    def _summary_core_lines(self, unified_view: UnifiedRfqView) -> list[str]:
        lines: list[str] = []
        if unified_view.name:
            lines.append(f"- RFQ: {unified_view.name}")
        if unified_view.rfq_code:
            lines.append(f"- Code: {unified_view.rfq_code}")
        if unified_view.client:
            lines.append(f"- Client: {unified_view.client}")
        if unified_view.status:
            lines.append(f"- Status: {unified_view.status}")
        if unified_view.current_stage_name:
            lines.append(f"- Stage: {unified_view.current_stage_name}")
        if unified_view.progress is not None:
            lines.append(f"- Progress: {unified_view.progress}%")
        if unified_view.deadline is not None:
            lines.append(f"- Deadline: {unified_view.deadline.isoformat()}")
        if unified_view.owner:
            lines.append(f"- Owner: {unified_view.owner}")
        return lines

    def _summary_readiness_lines(self, unified_view: UnifiedRfqView) -> list[str]:
        lines: list[str] = []
        if unified_view.source_package_available is not None:
            lines.append(
                f"- Source package: {self._availability_text(unified_view.source_package_available)}"
            )

        readiness_bits: list[str] = []
        if unified_view.workbook_available is not None:
            readiness_bits.append(
                f"manager workbook {self._availability_text(unified_view.workbook_available)}"
            )
        if unified_view.snapshot is not None and unified_view.snapshot.workbook_status:
            readiness_bits.append(f"snapshot workbook {unified_view.snapshot.workbook_status}")
        if unified_view.snapshot is not None and unified_view.snapshot.review_status:
            readiness_bits.append(f"review {unified_view.snapshot.review_status}")
        if unified_view.snapshot is not None and unified_view.snapshot.overall_status:
            readiness_bits.append(f"intelligence {unified_view.snapshot.overall_status}")
        if readiness_bits:
            lines.append(f"- Readiness: {'; '.join(readiness_bits)}")
        return lines

    def _detail_core_lines(self, unified_view: UnifiedRfqView) -> list[str]:
        lines: list[str] = []
        if unified_view.name:
            lines.append(f"- RFQ: {unified_view.name}")
        if unified_view.rfq_code:
            lines.append(f"- Code: {unified_view.rfq_code}")
        if unified_view.client:
            lines.append(f"- Client: {unified_view.client}")
        if unified_view.workflow_name:
            lines.append(f"- Workflow: {unified_view.workflow_name}")
        if unified_view.status:
            lines.append(f"- Status: {unified_view.status}")
        if unified_view.priority:
            lines.append(f"- Priority: {unified_view.priority}")
        if unified_view.deadline is not None:
            lines.append(f"- Deadline: {unified_view.deadline.isoformat()}")
        if unified_view.owner:
            lines.append(f"- Owner: {unified_view.owner}")
        return lines

    def _detail_execution_lines(self, unified_view: UnifiedRfqView) -> list[str]:
        lines: list[str] = []
        if unified_view.current_stage_name:
            lines.append(f"- Stage: {unified_view.current_stage_name}")
        if unified_view.progress is not None:
            lines.append(f"- Overall progress: {unified_view.progress}%")
        if unified_view.stage and unified_view.stage.assigned_team:
            lines.append(f"- Assigned team: {unified_view.stage.assigned_team}")
        blocker_text = self._blocker_sentence(unified_view, bullet_prefix=False)
        if blocker_text:
            lines.append(f"- {blocker_text}")
        if unified_view.source_package_available is not None:
            lines.append(
                f"- Source package: {self._availability_text(unified_view.source_package_available)}"
            )
        if unified_view.workbook_available is not None:
            lines.append(
                f"- Manager workbook: {self._availability_text(unified_view.workbook_available)}"
            )
        return lines

    def _detail_intelligence_lines(self, unified_view: UnifiedRfqView) -> list[str]:
        snapshot = unified_view.snapshot
        if snapshot is None:
            if unified_view.profile_source_ref is None:
                return []
            return ["- I don't have grounded intelligence snapshot details for this RFQ yet."]

        lines: list[str] = []
        if snapshot.overall_status:
            lines.append(f"- Snapshot: {snapshot.overall_status}")
        if snapshot.briefing_status:
            lines.append(f"- Briefing: {snapshot.briefing_status}")
        if snapshot.workbook_status:
            lines.append(f"- Workbook: {snapshot.workbook_status}")
        if snapshot.review_status:
            lines.append(f"- Review: {snapshot.review_status}")
        if snapshot.analytical_status:
            lines.append(f"- Analytical status: {snapshot.analytical_status}")
        if snapshot.requires_human_review:
            lines.append("- Human review is still required")
        if snapshot.active_findings_count > 0:
            lines.append(f"- Active review findings: {snapshot.active_findings_count}")
        if snapshot.outcome_status:
            lines.append(f"- Outcome status: {snapshot.outcome_status}")
        if snapshot.outcome_reason:
            lines.append(f"- Outcome reason: {snapshot.outcome_reason}")
        if snapshot.briefing_summary:
            lines.append(f"- Briefing summary: {snapshot.briefing_summary}")
        return lines

    def _detail_gap_lines(self, unified_view: UnifiedRfqView) -> list[str]:
        lines: list[str] = []
        if unified_view.snapshot is not None:
            gap_lines = self._gap_bullets(unified_view.snapshot)
            lines.extend(gap_lines)
        if not lines:
            lines.append("- No grounded briefing or intake gaps are currently available.")
        return lines

    def _derive_advisory_sections(
        self,
        unified_view: UnifiedRfqView,
    ) -> tuple[dict[str, list[str]], list[SourceRef]]:
        sections = {
            "concerns": [],
            "missing": [],
            "attention": [],
        }
        refs: list[SourceRef | None] = []

        progress_deadline_tension = self._has_progress_deadline_tension(unified_view)
        if progress_deadline_tension:
            sections["concerns"].append(
                f"Progress is {unified_view.progress}% against the current deadline of {unified_view.deadline.isoformat()}."
            )
            sections["attention"].append(
                "Recheck schedule confidence and delivery assumptions against the current deadline."
            )
            refs.append(unified_view.profile_source_ref)

        blocker_text = self._blocker_sentence(unified_view, bullet_prefix=False)
        if blocker_text:
            sections["concerns"].append(blocker_text)
            sections["attention"].append(
                "Clear the current blocker before treating downstream RFQ execution assumptions as stable."
            )
            refs.extend([unified_view.profile_source_ref, unified_view.stage_source_ref])

        if unified_view.source_package_available is False:
            sections["missing"].append("Source package is not available from the manager-backed RFQ record.")
            sections["attention"].append("Confirm the source package before relying on a complete RFQ read.")
            refs.append(unified_view.profile_source_ref)

        if unified_view.workbook_available is False:
            sections["missing"].append("Manager-backed workbook availability is still false.")
            sections["attention"].append("Finish workbook readiness before treating the RFQ as execution-ready.")
            refs.append(unified_view.profile_source_ref)

        snapshot = unified_view.snapshot
        if snapshot is not None:
            if snapshot.overall_status and snapshot.overall_status.lower() not in self.ready_statuses:
                sections["missing"].append(
                    f"Current intelligence snapshot is {snapshot.overall_status}."
                )
                refs.append(unified_view.snapshot_source_ref)
            if snapshot.requires_human_review:
                sections["concerns"].append("The current intelligence snapshot still requires human review.")
                sections["attention"].append("Resolve the outstanding human review before relying on the intelligence output as final.")
                refs.append(unified_view.snapshot_source_ref)
            if snapshot.workbook_status and snapshot.workbook_status.lower() not in self.ready_statuses:
                sections["missing"].append(f"Snapshot workbook status is {snapshot.workbook_status}.")
                sections["attention"].append("Complete workbook preparation before using the RFQ as fully estimation-ready.")
                refs.append(unified_view.snapshot_source_ref)
            if snapshot.review_status and snapshot.review_status.lower() not in self.ready_statuses:
                sections["missing"].append(f"Review status is {snapshot.review_status}.")
                sections["attention"].append("Complete review readiness before treating the RFQ as fully checked.")
                refs.append(unified_view.snapshot_source_ref)
            if snapshot.active_findings_count > 0:
                sections["concerns"].append(
                    f"There are {snapshot.active_findings_count} active review findings."
                )
                sections["attention"].append("Address the active review findings before treating the current RFQ position as clean.")
                refs.append(unified_view.snapshot_source_ref)
            gaps = self._snapshot_gap_values(snapshot)
            if gaps:
                sections["missing"].append(f"Grounded gaps are still open: {', '.join(gaps[:3])}.")
                sections["attention"].append(f"Close the highest-impact gaps first: {', '.join(gaps[:2])}.")
                refs.append(unified_view.snapshot_source_ref)
            if snapshot.analytical_notes:
                sections["concerns"].append(
                    f"Analytical notes flag: {snapshot.analytical_notes[0]}."
                )
                refs.append(unified_view.snapshot_source_ref)
            if snapshot.outcome_reason:
                sections["concerns"].append(f"Outcome reason currently recorded: {snapshot.outcome_reason}.")
                refs.append(unified_view.snapshot_source_ref)
        elif unified_view.profile_source_ref is not None:
            sections["missing"].append("I do not have a grounded intelligence snapshot to assess workbook, review, or gap signals fully.")
            refs.append(unified_view.profile_source_ref)

        if not sections["concerns"]:
            sections["concerns"].append(
                "I do not have enough grounded risk signals to identify specific concerns reliably right now."
            )
        if not sections["missing"]:
            sections["missing"].append(
                "I do not have enough grounded completeness signals to name specific missing elements reliably right now."
            )
        if not sections["attention"]:
            sections["attention"].append(
                "I do not have enough grounded operational signals to prioritize next actions confidently right now."
            )

        return sections, self._dedupe_refs(refs)

    @staticmethod
    def _field_sentence(label: str, value: str) -> str:
        if label == "owner":
            return f"The RFQ owner is {value}."
        if label == "deadline":
            return f"The RFQ deadline is {value}."
        if label == "status":
            return f"The RFQ status is {value}."
        if label == "progress":
            return f"The RFQ progress is {value}."
        if label == "client":
            return f"The client is {value}."
        if label == "workflow":
            return f"The workflow is {value}."
        if label == "priority":
            return f"The priority is {value}."
        if label == "country":
            return f"The country is {value}."
        if label == "industry":
            return f"The industry is {value}."
        return f"{label.capitalize()}: {value}."

    def _is_fact_field_request(self, normalized_content: str) -> bool:
        field_families = (
            self.owner_terms,
            self.deadline_terms,
            self.status_terms,
            self.progress_terms,
            self.client_terms,
            self.workflow_terms,
            self.priority_terms,
            self.country_terms,
            self.industry_terms,
            self.rfq_code_terms,
            self.lifecycle_terms,
            self.stage_terms,
        )
        return any(self._contains_any(normalized_content, family) for family in field_families)

    def _is_summary_request(self, normalized_content: str) -> bool:
        return self._contains_any(normalized_content, self.summary_terms)

    def _is_detail_request(self, normalized_content: str) -> bool:
        return self._contains_any(normalized_content, self.detail_terms)

    def _blocker_sentence(
        self,
        unified_view: UnifiedRfqView,
        *,
        bullet_prefix: bool = True,
    ) -> str | None:
        if unified_view.stage is None or not unified_view.stage.blocker_status:
            return None
        status = unified_view.stage.blocker_status.strip()
        if status.lower() in self.clear_blocker_statuses:
            return None
        message = f"Current stage blocker status is {status}"
        if unified_view.stage.blocker_reason_code:
            message = f"{message} ({unified_view.stage.blocker_reason_code})"
        if bullet_prefix:
            return f"- {message}."
        return f"{message}."

    @staticmethod
    def _availability_text(is_available: bool) -> str:
        return "available" if is_available else "not available"

    def _gap_bullets(self, snapshot: UnifiedSnapshotView) -> list[str]:
        return [f"- {gap}" for gap in self._snapshot_gap_values(snapshot)[:4]]

    @staticmethod
    def _snapshot_gap_values(snapshot: UnifiedSnapshotView) -> list[str]:
        return list(snapshot.briefing_missing_info) + [
            gap for gap in snapshot.intake_key_gaps if gap not in snapshot.briefing_missing_info
        ]

    @staticmethod
    def _has_progress_deadline_tension(unified_view: UnifiedRfqView) -> bool:
        return (
            unified_view.deadline is not None
            and unified_view.progress is not None
            and unified_view.progress < 60
        )

    @staticmethod
    def _contains_any(normalized_content: str, terms: tuple[str, ...]) -> bool:
        return any(term in normalized_content for term in terms)

    @staticmethod
    def _latest_record(
        tool_call_records: list[ToolCallRecord],
        tool_name: str,
    ) -> ToolCallRecord | None:
        for record in reversed(tool_call_records):
            if record.tool_name == tool_name and record.result is not None:
                return record
        return None

    @staticmethod
    def _coerce_profile(value) -> ManagerRfqDetail | None:
        if value is None:
            return None
        if isinstance(value, ManagerRfqDetail):
            return value
        if isinstance(value, dict):
            return ManagerRfqDetail.model_validate(value)
        return None

    @staticmethod
    def _coerce_stage_list(value) -> ManagerRfqStageListResponse | None:
        if value is None:
            return None
        if isinstance(value, ManagerRfqStageListResponse):
            return value
        if isinstance(value, dict):
            return ManagerRfqStageListResponse.model_validate(value)
        return None

    @staticmethod
    def _coerce_snapshot(value) -> IntelligenceSnapshotArtifact | None:
        if value is None:
            return None
        if isinstance(value, IntelligenceSnapshotArtifact):
            return value
        if isinstance(value, dict):
            return IntelligenceSnapshotArtifact.model_validate(value)
        return None

    @staticmethod
    def _select_current_stage(
        *,
        profile: ManagerRfqDetail | None,
        stage_list: ManagerRfqStageListResponse | None,
    ) -> ManagerRfqStage | None:
        if stage_list is None or not stage_list.data:
            return None

        if profile is not None and profile.current_stage_name:
            for stage in stage_list.data:
                if (stage.name or "").strip().lower() == profile.current_stage_name.strip().lower():
                    return stage

        for stage in stage_list.data:
            if (stage.status or "").strip().lower() in {"open", "active", "in_progress"}:
                return stage

        return stage_list.data[0]

    @staticmethod
    def _dedupe_refs(source_refs: list[SourceRef | None]) -> list[SourceRef]:
        deduped: list[SourceRef] = []
        seen = set()
        for source_ref in source_refs:
            if source_ref is None:
                continue
            key = (source_ref.system, source_ref.artifact, source_ref.locator)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(source_ref)
        return deduped

    @staticmethod
    def _join_facts(facts: list[str]) -> str:
        if len(facts) == 1:
            return facts[0]
        return ", ".join(facts[:-1]) + f", and {facts[-1]}"

    @staticmethod
    def _snapshot_summary_value(
        snapshot: IntelligenceSnapshotArtifact | None,
        field_name: str,
    ) -> str | None:
        if snapshot is None:
            return None
        return getattr(snapshot.content.rfq_summary, field_name, None)

    @staticmethod
    def _coerce_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(str(value))
        except ValueError:
            return None
