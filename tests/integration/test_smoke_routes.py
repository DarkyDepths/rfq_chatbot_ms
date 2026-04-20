from src.config.settings import get_settings


def test_health_route_returns_expected_payload(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "rfq_chatbot_ms"}


def test_health_route_echoes_incoming_correlation_id(client):
    response = client.get("/health", headers={"X-Correlation-ID": "corr-id-1234"})

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "corr-id-1234"


def test_metrics_route_returns_prometheus_payload(client):
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "turns_total" in response.text


def test_ready_route_returns_503_when_azure_not_configured(client, monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "")
    monkeypatch.setenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "")
    get_settings.cache_clear()

    try:
        response = client.get("/ready")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_ready_route_returns_200_when_dependencies_are_configured(client, monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example-resource.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-5-nano")
    get_settings.cache_clear()

    try:
        response = client.get("/ready")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_smoke_route_returns_expected_payload(client):
    response = client.get("/rfq-chatbot/v1/smoke")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "rfq_chatbot_ms",
        "phase": "phase-6",
    }
