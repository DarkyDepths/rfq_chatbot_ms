"""Execution harness for golden_set JSON cases."""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from src.app_context import (
    get_azure_openai_connector,
    get_intelligence_connector,
    get_manager_connector,
)
from src.config.stage_profiles import DEFAULT_STAGE_PROFILE, STAGE_PROFILES
from src.connectors.azure_openai_connector import ChatCompletionResult
from src.connectors.intelligence_connector import (
    IntelligenceConnector,
    IntelligenceSnapshotArtifact,
    IntelligenceSnapshotContent,
    SnapshotAnalyticalStatusSummary,
    SnapshotArtifactMeta,
    SnapshotBriefingPanelSummary,
    SnapshotConsumerHints,
    SnapshotIntakePanelSummary,
    SnapshotOutcomeSummary,
    SnapshotReviewPanel,
    SnapshotRfqSummary,
    SnapshotWorkbookPanel,
)
from src.connectors.manager_connector import (
    ManagerConnector,
    ManagerRfqDetail,
    ManagerRfqStageListResponse,
)
from src.controllers.context_builder import CONFIDENCE_PATTERN_MARKER
from src.models.conversation import Message
from src.utils.errors import UpstreamServiceError


CASES_DIR = Path(__file__).parent / "cases"
KNOWN_STAGE_ID = next(iter(STAGE_PROFILES.keys()))
UNKNOWN_STAGE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


@dataclass
class GoldenAzureConnector:
    """Deterministic chat-completion fake that reacts to prompt structure."""

    calls: list = field(default_factory=list)

    def create_chat_completion(self, messages, tools=None):
        stable_prefix = messages[0]["content"]
        variable_suffix = messages[-1]["content"]
        latest_user_turn = self._extract_latest_user_turn(variable_suffix)
        lowered_latest = latest_user_turn.lower()

        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "stable_prefix": stable_prefix,
                "variable_suffix": variable_suffix,
                "latest_user_turn": latest_user_turn,
            }
        )

        if "Disambiguation behavior: RFQ resolution mode." in stable_prefix:
            return ChatCompletionResult(
                assistant_text=(
                    "Which RFQ are you referring to? Please provide an RFQ code "
                    "(for example IF-25144)."
                )
            )

        if "template exactly: I don't have grounded facts for" in stable_prefix:
            template_line = stable_prefix.split("template exactly: ", 1)[1].split("\n", 1)[0]
            return ChatCompletionResult(assistant_text=template_line)

        if "Grounding behavior: grounding gap mode." in stable_prefix:
            return ChatCompletionResult(
                assistant_text=(
                    "I cannot retrieve the requested information right now. "
                    "Please ask for another grounded RFQ fact."
                )
            )

        if self._is_greeting(lowered_latest):
            return ChatCompletionResult(
                assistant_text=self._build_greeting_response(stable_prefix)
            )

        if "pwht" in lowered_latest:
            return ChatCompletionResult(
                assistant_text="PWHT is post-weld heat treatment used to reduce residual stress."
            )

        if re.search(r"\brt\b|radiographic", lowered_latest):
            return ChatCompletionResult(
                assistant_text="RT is radiographic testing used to detect internal weld defects."
            )

        if "margin" in lowered_latest or "cost status" in lowered_latest:
            if "Role tone directive: Respond in a decision-oriented executive tone." in stable_prefix:
                return ChatCompletionResult(
                    assistant_text=(
                        "Executive margin summary: healthy position around 18% with room "
                        "for strategic concession if needed."
                    )
                )
            return ChatCompletionResult(
                assistant_text=(
                    "Working-level margin detail: gross margin is around 18% with "
                    "materials and labor as primary cost drivers."
                )
            )

        if "owner" in lowered_latest or "deadline" in lowered_latest:
            return ChatCompletionResult(
                assistant_text="The RFQ owner is Sarah and the deadline is 2026-05-01."
            )

        if "stage" in lowered_latest:
            if "Current stage label: Go / No-Go" in stable_prefix:
                return ChatCompletionResult(
                    assistant_text=(
                        "Current stage is Go / No-Go, so qualification risk and decision "
                        "clarity should be emphasized."
                    )
                )
            if DEFAULT_STAGE_PROFILE["prompt_frame_fragment"] in stable_prefix:
                return ChatCompletionResult(
                    assistant_text=(
                        "Current stage context is unavailable, so neutral stage framing "
                        "is being used."
                    )
                )

        if "snapshot" in lowered_latest or "aramco" in lowered_latest:
            response = (
                "Based on observed standards keywords, this appears to be an Aramco "
                "pressure vessel project."
            )
            if CONFIDENCE_PATTERN_MARKER in stable_prefix:
                response = f"{response}\n{CONFIDENCE_PATTERN_MARKER}"
            return ChatCompletionResult(assistant_text=response)

        return ChatCompletionResult(assistant_text="assistant-response")

    @staticmethod
    def _extract_latest_user_turn(variable_suffix: str) -> str:
        marker = "Latest user turn:\n"
        if marker in variable_suffix:
            return variable_suffix.split(marker, 1)[1].strip()
        return variable_suffix.strip()

    @staticmethod
    def _is_greeting(lowered_latest: str) -> bool:
        return lowered_latest.startswith(("hi", "hello", "hey", "good morning", "good afternoon", "good evening", "salam"))

    @staticmethod
    def _line_value(stable_prefix: str, field_name: str) -> str | None:
        pattern = rf"^{re.escape(field_name)}:\s*(.+)$"
        for line in stable_prefix.splitlines():
            match = re.match(pattern, line.strip())
            if match:
                return match.group(1).strip()
        return None

    def _build_greeting_response(self, stable_prefix: str) -> str:
        if "first-turn conversational greeting in RFQ-bound mode" in stable_prefix:
            rfq_name = self._line_value(stable_prefix, "RFQ name") or "this RFQ"
            client_name = self._line_value(stable_prefix, "Client") or "the client"
            stage_name = self._line_value(stable_prefix, "Current stage") or "current stage"
            return (
                f"Welcome back. I can help with {rfq_name} for {client_name}, "
                f"currently in {stage_name}."
            )

        return (
            "Welcome. I can help across your RFQ portfolio with status, deadlines, "
            "and next-step planning."
        )


class GoldenManagerConnector(ManagerConnector):
    """Scenario manager connector supporting known/default/failure modes."""

    def __init__(self, *, mode: str = "known_stage"):
        self.mode = mode
        self.get_rfq_calls = 0
        self.get_rfq_stages_calls = 0

    def get_rfq(self, rfq_id):
        self.get_rfq_calls += 1

        if self.mode == "upstream_failure":
            raise UpstreamServiceError("Manager service request failed")

        if self.mode == "default_stage":
            return _build_manager_rfq_detail(
                rfq_id=rfq_id,
                stage_id=UNKNOWN_STAGE_ID,
                stage_name="Unknown Stage",
            )

        return _build_manager_rfq_detail(
            rfq_id=rfq_id,
            stage_id=KNOWN_STAGE_ID,
            stage_name="Go / No-Go",
        )

    def get_rfq_stages(self, rfq_id):
        self.get_rfq_stages_calls += 1
        if self.mode == "stage_failure":
            raise UpstreamServiceError("Manager stage service request failed")

        return ManagerRfqStageListResponse.model_validate(
            {
                "data": [
                    {
                        "id": str(uuid.uuid4()),
                        "name": "Review",
                        "order": 2,
                        "assigned_team": "Estimating",
                        "status": "open",
                        "progress": 35,
                    }
                ]
            }
        )


class GoldenIntelligenceConnector(IntelligenceConnector):
    """Scenario intelligence connector supporting success/failure modes."""

    def __init__(self, *, mode: str = "ok"):
        self.mode = mode
        self.get_snapshot_calls = 0

    def get_snapshot(self, rfq_id):
        self.get_snapshot_calls += 1

        if self.mode == "failure":
            raise UpstreamServiceError("Intelligence service request failed")

        return IntelligenceSnapshotArtifact(
            id=uuid.uuid4(),
            rfq_id=rfq_id,
            artifact_type="rfq_intelligence_snapshot",
            version=1,
            status="partial",
            is_current=True,
            content=IntelligenceSnapshotContent(
                artifact_meta=SnapshotArtifactMeta(
                    artifact_type="rfq_intelligence_snapshot",
                ),
                rfq_summary=SnapshotRfqSummary(
                    rfq_id=str(rfq_id),
                    rfq_code="IF-25144",
                    project_title="Boiler Upgrade",
                    client_name="Acme Industrial",
                ),
                availability_matrix={"intelligence_briefing": "available"},
                intake_panel_summary=SnapshotIntakePanelSummary(status="available"),
                briefing_panel_summary=SnapshotBriefingPanelSummary(status="available"),
                workbook_panel=SnapshotWorkbookPanel(status="not_ready"),
                review_panel=SnapshotReviewPanel(status="not_ready"),
                analytical_status_summary=SnapshotAnalyticalStatusSummary(status="not_ready"),
                outcome_summary=SnapshotOutcomeSummary(status="not_recorded"),
                consumer_hints=SnapshotConsumerHints(),
                overall_status="partial",
            ),
            schema_version="1.0",
            created_at="2026-04-10T10:00:00Z",
            updated_at="2026-04-10T10:00:00Z",
        )


def _build_manager_rfq_detail(*, rfq_id, stage_id: uuid.UUID, stage_name: str) -> ManagerRfqDetail:
    return ManagerRfqDetail.model_validate(
        {
            "id": str(rfq_id),
            "rfq_code": "IF-25144",
            "name": "Boiler Upgrade",
            "client": "Acme Industrial",
            "status": "open",
            "progress": 35,
            "deadline": "2026-05-01",
            "current_stage_name": stage_name,
            "workflow_name": "Industrial RFQ",
            "industry": "Oil & Gas",
            "country": "SA",
            "priority": "critical",
            "owner": "Sarah",
            "workflow_id": str(uuid.uuid4()),
            "current_stage_id": str(stage_id),
            "source_package_available": True,
            "workbook_available": False,
            "created_at": "2026-04-01T10:00:00Z",
            "updated_at": "2026-04-10T10:00:00Z",
        }
    )


def case_paths() -> list[Path]:
    """Return sorted case-file paths."""

    return sorted(CASES_DIR.glob("*.json"))


def load_case(case_path: Path) -> dict:
    """Load one golden case from disk."""

    with case_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def run_case(case: dict, *, client, app, db_session, caplog) -> None:
    """Execute one case end-to-end through the real API pipeline."""

    scenario = case.get("scenario", {})
    azure_connector = GoldenAzureConnector()
    manager_connector = GoldenManagerConnector(mode=scenario.get("manager_mode", "known_stage"))
    intelligence_connector = GoldenIntelligenceConnector(
        mode=scenario.get("intelligence_mode", "ok")
    )

    _override_dependencies(
        app,
        azure_connector=azure_connector,
        manager_connector=manager_connector,
        intelligence_connector=intelligence_connector,
    )

    try:
        session_id = _create_session(client, case["session"])
        for turn in case["turns"]:
            _execute_turn(
                turn=turn,
                session_id=session_id,
                client=client,
                db_session=db_session,
                caplog=caplog,
                azure_connector=azure_connector,
            )
    finally:
        _clear_dependencies(app)


def _execute_turn(*, turn: dict, session_id: str, client, db_session, caplog, azure_connector):
    records_start = len(caplog.records)
    calls_start = len(azure_connector.calls)

    with caplog.at_level(logging.INFO):
        response = client.post(
            f"/rfq-chatbot/v1/sessions/{session_id}/turn",
            json={"content": turn["user_content"]},
        )

    payload = response.json()
    assert response.status_code == turn.get("status_code", 200)

    assistant_message = db_session.query(Message).filter_by(
        conversation_id=uuid.UUID(payload["conversation_id"]),
        turn_number=payload["turn_number"],
        role="assistant",
    ).one()

    turn_records = caplog.records[records_start:]
    azure_call_occurred = len(azure_connector.calls) > calls_start
    azure_call = azure_connector.calls[calls_start] if azure_call_occurred else None
    tool_calls = assistant_message.tool_calls or []
    tool_names = [
        tool_call.get("tool_name")
        for tool_call in tool_calls
        if isinstance(tool_call, dict) and isinstance(tool_call.get("tool_name"), str)
    ]

    disambiguation_resolved_value = _last_extra(turn_records, "phase6.disambiguation_resolved")
    disambiguation_abandoned_value = _last_extra(turn_records, "phase6.disambiguation_abandoned")

    observed = {
        "intent": _last_extra(turn_records, "phase6.intent_classified"),
        "route": _last_extra(turn_records, "phase6.route_selected"),
        "disambiguation_resolved": (
            bool(disambiguation_resolved_value)
            if disambiguation_resolved_value is not None
            else None
        ),
        "disambiguation_abandoned": (
            bool(disambiguation_abandoned_value)
            if disambiguation_abandoned_value is not None
            else None
        ),
        "content": payload["content"],
        "source_refs_present": bool(payload.get("source_refs")),
        "source_ref_count": len(payload.get("source_refs") or []),
        "tools": tool_names,
        "azure_call_occurred": azure_call_occurred,
        "stable_prefix": azure_call["stable_prefix"] if azure_call else None,
        "response_mode_selected": _last_extra(
            turn_records,
            "phase7b.response_mode_selected",
        ),
        "response_mode_effective": _last_extra(
            turn_records,
            "phase7b.response_mode_effective",
        ),
        "evidence_sufficient": _last_extra(
            turn_records,
            "phase7b.evidence_sufficient",
        ),
        "downgrade_reason": _last_extra(
            turn_records,
            "phase7b.evidence_downgrade_reason",
        ),
        "grounded": _last_extra(turn_records, "phase7b.grounded"),
    }

    from golden_set.judges import assert_turn_expectations

    assert_turn_expectations(turn.get("expect", {}), observed)


def _last_extra(records, field_name: str):
    values = [record.__dict__[field_name] for record in records if field_name in record.__dict__]
    if not values:
        return None
    return values[-1]


def _create_session(client, session_spec: dict) -> str:
    payload = {
        "mode": session_spec["mode"],
        "user_id": session_spec.get("user_id", "golden-set-user"),
    }

    if "rfq_id" in session_spec:
        rfq_id = session_spec["rfq_id"]
        if rfq_id == "__AUTO_UUID__":
            rfq_id = str(uuid.uuid4())
        payload["rfq_id"] = rfq_id

    if "role" in session_spec:
        payload["role"] = session_spec["role"]

    response = client.post("/rfq-chatbot/v1/sessions", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def _override_dependencies(
    app,
    *,
    azure_connector,
    manager_connector,
    intelligence_connector,
):
    app.dependency_overrides[get_azure_openai_connector] = lambda: azure_connector
    app.dependency_overrides[get_manager_connector] = lambda: manager_connector
    app.dependency_overrides[get_intelligence_connector] = lambda: intelligence_connector


def _clear_dependencies(app):
    app.dependency_overrides.pop(get_azure_openai_connector, None)
    app.dependency_overrides.pop(get_manager_connector, None)
    app.dependency_overrides.pop(get_intelligence_connector, None)
