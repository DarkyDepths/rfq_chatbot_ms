"""Sync HTTP connector for read-only RFQ manager retrieval."""

from __future__ import annotations

import uuid
from datetime import date, datetime
import logging

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.config.settings import get_settings
from src.utils.correlation import get_correlation_id
from src.utils.errors import NotFoundError, UpstreamServiceError, UpstreamTimeoutError
from src.utils.metrics import record_upstream_error


logger = logging.getLogger(__name__)


class ManagerRfqDetail(BaseModel):
    """Typed response for manager GET /rfqs/{rfq_id}."""

    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID
    rfq_code: str | None = None
    name: str
    client: str
    status: str
    progress: int
    deadline: date
    current_stage_name: str | None = None
    workflow_name: str | None = None
    industry: str | None = None
    country: str | None = None
    priority: str
    owner: str
    description: str | None = None
    workflow_id: uuid.UUID
    current_stage_id: uuid.UUID | None = None
    source_package_available: bool = False
    source_package_updated_at: datetime | None = None
    workbook_available: bool = False
    workbook_updated_at: datetime | None = None
    outcome_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class ManagerRfqStage(BaseModel):
    """Typed stage row returned by manager stage listing."""

    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID
    name: str
    order: int
    assigned_team: str | None = None
    status: str
    progress: int
    planned_start: date | None = None
    planned_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    blocker_status: str | None = None
    blocker_reason_code: str | None = None


class ManagerRfqStageListResponse(BaseModel):
    """Typed response for manager GET /rfqs/{rfq_id}/stages."""

    model_config = ConfigDict(extra="ignore")

    data: list[ManagerRfqStage] = Field(default_factory=list)


class ManagerConnector:
    """Thin sync wrapper around rfq_manager_ms read endpoints."""

    api_prefix = "/rfq-manager/v1"

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
            base_url or settings.MANAGER_BASE_URL,
            self.api_prefix,
        )
        self._timeout_seconds = (
            timeout_seconds or settings.MANAGER_REQUEST_TIMEOUT_SECONDS
        )

    def get_rfq(self, rfq_id: uuid.UUID) -> ManagerRfqDetail:
        """Fetch one RFQ detail record."""

        payload = self._get_json(
            f"/rfqs/{rfq_id}",
            not_found_message=f"RFQ '{rfq_id}' not found in manager service",
        )
        return self._validate_payload(
            ManagerRfqDetail,
            payload,
            "Manager service returned malformed RFQ detail payload",
        )

    def get_rfq_stages(self, rfq_id: uuid.UUID) -> ManagerRfqStageListResponse:
        """Fetch the current stage list for one RFQ."""

        payload = self._get_json(
            f"/rfqs/{rfq_id}/stages",
            not_found_message=f"RFQ stages for '{rfq_id}' not found in manager service",
        )
        return self._validate_payload(
            ManagerRfqStageListResponse,
            payload,
            "Manager service returned malformed RFQ stage payload",
        )

    def _get_json(self, path: str, *, not_found_message: str) -> dict:
        if self._client is None and not self._base_url:
            record_upstream_error("manager", "not_configured")
            raise UpstreamServiceError("Manager service is not configured")

        request_headers = {"X-Correlation-ID": get_correlation_id()}

        try:
            if self._client is not None:
                response = self._client.get(path, headers=request_headers)
            else:
                with httpx.Client(
                    base_url=self._base_url,
                    timeout=self._timeout_seconds,
                ) as client:
                    response = client.get(path, headers=request_headers)
        except httpx.TimeoutException as exc:
            record_upstream_error("manager", "timeout")
            raise UpstreamTimeoutError("Manager service request timed out") from exc
        except httpx.RequestError as exc:
            record_upstream_error("manager", "request_error")
            raise UpstreamServiceError("Manager service request failed") from exc

        if response.status_code == 404:
            raise NotFoundError(not_found_message)
        if response.status_code >= 400:
            record_upstream_error("manager", f"http_{response.status_code}")
            logger.warning(
                "manager_request_failed status_code=%s path=%s",
                response.status_code,
                path,
                extra={"upstream_service": "manager", "status_code": response.status_code},
            )
            raise UpstreamServiceError(
                f"Manager service request failed with status {response.status_code}"
            )

        try:
            return response.json()
        except ValueError as exc:
            record_upstream_error("manager", "invalid_json")
            raise UpstreamServiceError("Manager service returned invalid JSON") from exc

    @staticmethod
    def _validate_payload(model, payload: dict, message: str):
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            record_upstream_error("manager", "payload_validation")
            raise UpstreamServiceError(message) from exc

    @staticmethod
    def _normalize_base_url(base_url: str, api_prefix: str) -> str:
        normalized = (base_url or "").strip().rstrip("/")
        if not normalized:
            return ""
        if normalized.endswith(api_prefix):
            return normalized
        return normalized + api_prefix
