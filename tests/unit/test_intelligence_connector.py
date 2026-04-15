import uuid

import httpx
import pytest

from src.connectors.intelligence_connector import IntelligenceConnector
from src.config.settings import get_settings
from src.utils.errors import NotFoundError, UpstreamServiceError, UpstreamTimeoutError


def test_intelligence_connector_parses_snapshot_response():
    rfq_id = uuid.uuid4()

    def handler(request):
        assert request.url.path.endswith(f"/rfqs/{rfq_id}/snapshot")
        return httpx.Response(
            200,
            json={
                "id": str(uuid.uuid4()),
                "rfq_id": str(rfq_id),
                "artifact_type": "rfq_intelligence_snapshot",
                "version": 1,
                "status": "partial",
                "is_current": True,
                "content": {
                    "artifact_meta": {
                        "artifact_type": "rfq_intelligence_snapshot",
                        "generated_at": "2026-04-10T10:00:00Z",
                    },
                    "rfq_summary": {
                        "rfq_id": str(rfq_id),
                        "rfq_code": "IF-25144",
                        "project_title": "Boiler Upgrade",
                        "client_name": "Acme Industrial",
                    },
                    "availability_matrix": {"intelligence_briefing": "available"},
                    "intake_panel_summary": {"status": "available"},
                    "briefing_panel_summary": {
                        "status": "available",
                        "executive_summary": "Known summary",
                    },
                    "workbook_panel": {"status": "not_ready"},
                    "review_panel": {"status": "not_ready", "active_findings_count": 0},
                    "analytical_status_summary": {
                        "status": "not_ready",
                        "historical_readiness": False,
                        "notes": [],
                    },
                    "outcome_summary": {"status": "not_recorded"},
                    "consumer_hints": {"ui_recommended_tabs": ["snapshot"]},
                    "requires_human_review": True,
                    "overall_status": "partial",
                },
                "schema_version": "1.0",
                "created_at": "2026-04-10T10:00:00Z",
                "updated_at": "2026-04-10T10:00:00Z",
            },
        )

    client = httpx.Client(
        base_url="http://intelligence.test/intelligence/v1",
        transport=httpx.MockTransport(handler),
    )
    connector = IntelligenceConnector(client=client)

    result = connector.get_snapshot(rfq_id)

    assert result.rfq_id == rfq_id
    assert result.content.rfq_summary.rfq_code == "IF-25144"
    assert result.content.overall_status == "partial"


def test_intelligence_connector_maps_not_found():
    rfq_id = uuid.uuid4()

    def handler(request):
        return httpx.Response(404, json={"detail": "missing"})

    client = httpx.Client(
        base_url="http://intelligence.test/intelligence/v1",
        transport=httpx.MockTransport(handler),
    )
    connector = IntelligenceConnector(client=client)

    with pytest.raises(NotFoundError) as exc:
        connector.get_snapshot(rfq_id)

    assert (
        str(exc.value)
        == f"Intelligence snapshot for RFQ '{rfq_id}' not found in intelligence service"
    )


def test_intelligence_connector_maps_timeout():
    def handler(request):
        raise httpx.ReadTimeout("boom", request=request)

    client = httpx.Client(
        base_url="http://intelligence.test/intelligence/v1",
        transport=httpx.MockTransport(handler),
    )
    connector = IntelligenceConnector(client=client)

    with pytest.raises(UpstreamTimeoutError) as exc:
        connector.get_snapshot(uuid.uuid4())

    assert str(exc.value) == "Intelligence service request timed out"


def test_intelligence_connector_maps_generic_failure():
    def handler(request):
        return httpx.Response(500, json={"detail": "boom"})

    client = httpx.Client(
        base_url="http://intelligence.test/intelligence/v1",
        transport=httpx.MockTransport(handler),
    )
    connector = IntelligenceConnector(client=client)

    with pytest.raises(UpstreamServiceError) as exc:
        connector.get_snapshot(uuid.uuid4())

    assert str(exc.value) == "Intelligence service request failed with status 500"


def test_intelligence_connector_maps_malformed_payload():
    rfq_id = uuid.uuid4()

    def handler(request):
        return httpx.Response(
            200,
            json={
                "id": str(uuid.uuid4()),
                "rfq_id": str(rfq_id),
                "artifact_type": "rfq_intelligence_snapshot",
            },
        )

    client = httpx.Client(
        base_url="http://intelligence.test/intelligence/v1",
        transport=httpx.MockTransport(handler),
    )
    connector = IntelligenceConnector(client=client)

    with pytest.raises(UpstreamServiceError) as exc:
        connector.get_snapshot(rfq_id)

    assert str(exc.value) == "Intelligence service returned malformed snapshot payload"


def test_intelligence_connector_uses_injected_client_without_base_url(monkeypatch):
    rfq_id = uuid.uuid4()

    def handler(request):
        return httpx.Response(
            200,
            json={
                "id": str(uuid.uuid4()),
                "rfq_id": str(rfq_id),
                "artifact_type": "rfq_intelligence_snapshot",
                "version": 1,
                "status": "partial",
                "is_current": True,
                "content": {
                    "artifact_meta": {
                        "artifact_type": "rfq_intelligence_snapshot",
                    },
                    "rfq_summary": {},
                    "intake_panel_summary": {"status": "available"},
                    "briefing_panel_summary": {"status": "available"},
                    "workbook_panel": {"status": "not_ready"},
                    "review_panel": {"status": "not_ready"},
                    "analytical_status_summary": {"status": "not_ready"},
                    "outcome_summary": {"status": "not_recorded"},
                    "consumer_hints": {},
                    "overall_status": "partial",
                },
                "schema_version": "1.0",
                "created_at": "2026-04-10T10:00:00Z",
            },
        )

    monkeypatch.delenv("INTELLIGENCE_BASE_URL", raising=False)
    get_settings.cache_clear()
    client = httpx.Client(
        base_url="http://intelligence.test/intelligence/v1",
        transport=httpx.MockTransport(handler),
    )

    try:
        connector = IntelligenceConnector(client=client)
        result = connector.get_snapshot(rfq_id)
    finally:
        get_settings.cache_clear()

    assert result.rfq_id == rfq_id
