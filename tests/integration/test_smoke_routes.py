def test_health_route_returns_expected_payload(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "rfq_chatbot_ms"}


def test_smoke_route_returns_expected_payload(client):
    response = client.get("/rfq-chatbot/v1/smoke")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "rfq_chatbot_ms",
        "phase": "phase-2",
    }
