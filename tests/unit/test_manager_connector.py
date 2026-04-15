import uuid

import httpx
import pytest

from src.connectors.manager_connector import ManagerConnector
from src.utils.errors import NotFoundError, UpstreamServiceError, UpstreamTimeoutError


def test_manager_connector_parses_rfq_detail_response():
    rfq_id = uuid.uuid4()

    def handler(request):
        assert request.url.path.endswith(f"/rfqs/{rfq_id}")
        return httpx.Response(
            200,
            json={
                "id": str(rfq_id),
                "rfq_code": "IF-25144",
                "name": "Boiler Upgrade",
                "client": "Acme Industrial",
                "status": "open",
                "progress": 35,
                "deadline": "2026-05-01",
                "current_stage_name": "Review",
                "workflow_name": "Industrial RFQ",
                "industry": "Oil & Gas",
                "country": "SA",
                "priority": "critical",
                "owner": "Sarah",
                "workflow_id": str(uuid.uuid4()),
                "source_package_available": True,
                "workbook_available": False,
                "created_at": "2026-04-01T10:00:00Z",
                "updated_at": "2026-04-10T10:00:00Z",
            },
        )

    client = httpx.Client(
        base_url="http://manager.test/rfq-manager/v1",
        transport=httpx.MockTransport(handler),
    )
    connector = ManagerConnector(client=client)

    result = connector.get_rfq(rfq_id)

    assert result.id == rfq_id
    assert result.owner == "Sarah"
    assert result.deadline.isoformat() == "2026-05-01"


def test_manager_connector_maps_not_found():
    rfq_id = uuid.uuid4()

    def handler(request):
        return httpx.Response(404, json={"detail": "missing"})

    client = httpx.Client(
        base_url="http://manager.test/rfq-manager/v1",
        transport=httpx.MockTransport(handler),
    )
    connector = ManagerConnector(client=client)

    with pytest.raises(NotFoundError) as exc:
        connector.get_rfq(rfq_id)

    assert str(exc.value) == f"RFQ '{rfq_id}' not found in manager service"


def test_manager_connector_maps_timeout():
    def handler(request):
        raise httpx.ReadTimeout("boom", request=request)

    client = httpx.Client(
        base_url="http://manager.test/rfq-manager/v1",
        transport=httpx.MockTransport(handler),
    )
    connector = ManagerConnector(client=client)

    with pytest.raises(UpstreamTimeoutError) as exc:
        connector.get_rfq(uuid.uuid4())

    assert str(exc.value) == "Manager service request timed out"


def test_manager_connector_maps_generic_failure():
    def handler(request):
        return httpx.Response(500, json={"detail": "boom"})

    client = httpx.Client(
        base_url="http://manager.test/rfq-manager/v1",
        transport=httpx.MockTransport(handler),
    )
    connector = ManagerConnector(client=client)

    with pytest.raises(UpstreamServiceError) as exc:
        connector.get_rfq_stages(uuid.uuid4())

    assert str(exc.value) == "Manager service request failed with status 500"


def test_manager_connector_maps_malformed_payload():
    rfq_id = uuid.uuid4()

    def handler(request):
        return httpx.Response(
            200,
            json={
                "id": str(rfq_id),
                "name": "Boiler Upgrade",
            },
        )

    client = httpx.Client(
        base_url="http://manager.test/rfq-manager/v1",
        transport=httpx.MockTransport(handler),
    )
    connector = ManagerConnector(client=client)

    with pytest.raises(UpstreamServiceError) as exc:
        connector.get_rfq(rfq_id)

    assert str(exc.value) == "Manager service returned malformed RFQ detail payload"
