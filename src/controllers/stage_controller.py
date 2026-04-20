"""Stage resolution controller for Phase 5 Mode A."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from src.config.stage_profiles import DEFAULT_STAGE_PROFILE, STAGE_PROFILES, StageProfile
from src.connectors.manager_connector import ManagerConnector, ManagerRfqDetail
from src.models.session import ChatbotSession, SessionMode
from src.utils.errors import NotFoundError, UpstreamServiceError, UpstreamTimeoutError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StageResolution:
    """Internal stage-resolution result used by the turn pipeline."""

    profile: StageProfile
    rfq_detail: ManagerRfqDetail | None
    stage_id: uuid.UUID | None


class StageController:
    """Resolves a stage profile from the current RFQ-bound session."""

    def __init__(self, manager_connector: ManagerConnector):
        self.manager_connector = manager_connector

    def resolve_stage(
        self,
        session: ChatbotSession,
        preloaded_rfq_detail: ManagerRfqDetail | None = None,
    ) -> StageResolution:
        """Resolve stage profile with graceful degradation on upstream failures."""

        if session.mode != SessionMode.RFQ_BOUND:
            return self._default_resolution("skipped_non_rfq_session")

        rfq_id = self._parse_rfq_uuid(session.rfq_id)
        if rfq_id is None:
            return self._default_resolution("invalid_rfq_id_format")

        if preloaded_rfq_detail is not None:
            rfq_detail = preloaded_rfq_detail
        else:
            try:
                rfq_detail = self.manager_connector.get_rfq(rfq_id)
            except UpstreamTimeoutError:
                return self._default_resolution("upstream_timeout")
            except UpstreamServiceError:
                return self._default_resolution("upstream_service_error")
            except NotFoundError:
                return self._default_resolution("rfq_not_found")

        stage_id = rfq_detail.current_stage_id
        if stage_id in STAGE_PROFILES:
            self._log_stage_resolution("success")
            return StageResolution(
                profile=STAGE_PROFILES[stage_id],
                rfq_detail=rfq_detail,
                stage_id=stage_id,
            )

        self._log_stage_resolution("default_profile_applied")
        return StageResolution(
            profile=DEFAULT_STAGE_PROFILE,
            rfq_detail=rfq_detail,
            stage_id=stage_id,
        )

    @staticmethod
    def _parse_rfq_uuid(rfq_id: str | None) -> uuid.UUID | None:
        if not rfq_id:
            return None
        try:
            return uuid.UUID(str(rfq_id))
        except ValueError:
            return None

    def _default_resolution(self, reason: str) -> StageResolution:
        self._log_stage_resolution(reason)
        return StageResolution(
            profile=DEFAULT_STAGE_PROFILE,
            rfq_detail=None,
            stage_id=None,
        )

    @staticmethod
    def _log_stage_resolution(value: str) -> None:
        logger.info(
            "phase5.stage_resolved=%s",
            value,
            extra={"phase5.stage_resolved": value},
        )
