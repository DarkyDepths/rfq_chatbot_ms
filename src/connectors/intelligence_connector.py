"""Sync HTTP connector for read-only RFQ intelligence retrieval."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.config.settings import get_settings
from src.utils.errors import NotFoundError, UpstreamServiceError, UpstreamTimeoutError


class SnapshotArtifactMeta(BaseModel):
    """Typed artifact metadata inside snapshot content."""

    model_config = ConfigDict(extra="ignore")

    artifact_type: str
    slice: str | None = None
    generated_at: datetime | None = None
    source_event_id: str | None = None
    source_event_type: str | None = None


class SnapshotRfqSummary(BaseModel):
    """Typed RFQ summary inside intelligence snapshot content."""

    model_config = ConfigDict(extra="ignore")

    rfq_id: str | None = None
    rfq_code: str | None = None
    project_title: str | None = None
    client_name: str | None = None


class SnapshotIntakePanelSummary(BaseModel):
    """Typed intake summary inside intelligence snapshot content."""

    model_config = ConfigDict(extra="ignore")

    status: str
    source_reference: Any = None
    quality_status: str | None = None
    key_gaps: list[str] = Field(default_factory=list)


class SnapshotBriefingPanelSummary(BaseModel):
    """Typed briefing summary inside intelligence snapshot content."""

    model_config = ConfigDict(extra="ignore")

    status: str
    executive_summary: str | None = None
    missing_info: list[str] = Field(default_factory=list)


class SnapshotWorkbookPanel(BaseModel):
    """Typed workbook summary inside intelligence snapshot content."""

    model_config = ConfigDict(extra="ignore")

    status: str
    reason: str | None = None
    template_recognition: Any = None
    pairing_validation: Any = None
    parser_status: str | None = None
    parser_failure: Any = None


class SnapshotReviewPanel(BaseModel):
    """Typed review summary inside intelligence snapshot content."""

    model_config = ConfigDict(extra="ignore")

    status: str
    reason: str | None = None
    active_findings_count: int = 0


class SnapshotAnalyticalStatusSummary(BaseModel):
    """Typed analytical status section inside intelligence snapshot content."""

    model_config = ConfigDict(extra="ignore")

    status: str
    historical_readiness: bool = False
    notes: list[str] = Field(default_factory=list)


class SnapshotOutcomeSummary(BaseModel):
    """Typed outcome section inside intelligence snapshot content."""

    model_config = ConfigDict(extra="ignore")

    status: str
    outcome: str | None = None
    reason: str | None = None
    recorded_at: str | None = None
    learning_loop_status: str | None = None


class SnapshotConsumerHints(BaseModel):
    """Typed consumer hints section inside intelligence snapshot content."""

    model_config = ConfigDict(extra="ignore")

    ui_recommended_tabs: list[str] = Field(default_factory=list)
    chatbot_suggested_questions: list[str] = Field(default_factory=list)


class IntelligenceSnapshotContent(BaseModel):
    """Typed snapshot content used by the Phase 4 retrieval tool."""

    model_config = ConfigDict(extra="ignore")

    artifact_meta: SnapshotArtifactMeta
    rfq_summary: SnapshotRfqSummary
    availability_matrix: dict[str, str] = Field(default_factory=dict)
    intake_panel_summary: SnapshotIntakePanelSummary
    briefing_panel_summary: SnapshotBriefingPanelSummary
    workbook_panel: SnapshotWorkbookPanel
    review_panel: SnapshotReviewPanel
    analytical_status_summary: SnapshotAnalyticalStatusSummary
    outcome_summary: SnapshotOutcomeSummary
    consumer_hints: SnapshotConsumerHints
    requires_human_review: bool = True
    overall_status: str


class IntelligenceSnapshotArtifact(BaseModel):
    """Typed response for intelligence GET /rfqs/{rfq_id}/snapshot."""

    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID
    rfq_id: uuid.UUID
    artifact_type: str
    version: int
    status: str
    is_current: bool
    content: IntelligenceSnapshotContent
    source_event_type: str | None = None
    source_event_id: str | None = None
    schema_version: str
    created_at: datetime
    updated_at: datetime | None = None


class IntelligenceConnector:
    """Thin sync wrapper around rfq_intelligence_ms read endpoints."""

    api_prefix = "/intelligence/v1"

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ):
        settings = get_settings()

        self._client = client
        self._base_url = self._normalize_base_url(
            base_url or settings.INTELLIGENCE_BASE_URL,
            self.api_prefix,
        )
        self._timeout_seconds = (
            timeout_seconds or settings.INTELLIGENCE_REQUEST_TIMEOUT_SECONDS
        )

    def get_snapshot(self, rfq_id: uuid.UUID) -> IntelligenceSnapshotArtifact:
        """Fetch the current intelligence snapshot for one RFQ."""

        payload = self._get_json(
            f"/rfqs/{rfq_id}/snapshot",
            not_found_message=(
                f"Intelligence snapshot for RFQ '{rfq_id}' not found in intelligence service"
            ),
        )
        return self._validate_payload(
            IntelligenceSnapshotArtifact,
            payload,
            "Intelligence service returned malformed snapshot payload",
        )

    def _get_json(self, path: str, *, not_found_message: str) -> dict:
        if self._client is None and not self._base_url:
            raise UpstreamServiceError("Intelligence service is not configured")

        try:
            if self._client is not None:
                response = self._client.get(path)
            else:
                with httpx.Client(
                    base_url=self._base_url,
                    timeout=self._timeout_seconds,
                ) as client:
                    response = client.get(path)
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError("Intelligence service request timed out") from exc
        except httpx.RequestError as exc:
            raise UpstreamServiceError("Intelligence service request failed") from exc

        if response.status_code == 404:
            raise NotFoundError(not_found_message)
        if response.status_code >= 400:
            raise UpstreamServiceError(
                f"Intelligence service request failed with status {response.status_code}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise UpstreamServiceError(
                "Intelligence service returned invalid JSON"
            ) from exc

    @staticmethod
    def _validate_payload(model, payload: dict, message: str):
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            raise UpstreamServiceError(message) from exc

    @staticmethod
    def _normalize_base_url(base_url: str, api_prefix: str) -> str:
        normalized = (base_url or "").strip().rstrip("/")
        if not normalized:
            return ""
        if normalized.endswith(api_prefix):
            return normalized
        return normalized + api_prefix
