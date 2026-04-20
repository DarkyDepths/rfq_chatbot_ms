from __future__ import annotations

import re
from pathlib import Path


OPENAPI_DOC_PATH = Path(__file__).resolve().parents[2] / "docs" / "rfq_chatbot_ms_openapi_current.yaml"


def _load_documented_openapi_text() -> str:
    return OPENAPI_DOC_PATH.read_text(encoding="utf-8")


def _documented_openapi_version(doc_text: str) -> str:
    match = re.search(r"^openapi:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$", doc_text, flags=re.MULTILINE)
    assert match is not None
    return match.group(1)


def test_live_openapi_contract_paths_are_documented(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    live_openapi = response.json()
    live_paths = set(live_openapi.get("paths", {}).keys())

    assert "/rfq-chatbot/v1/sessions/{session_id}/turn" in live_paths
    assert "/rfq-chatbot/v1/conversations/{conversation_id}" in live_paths

    documented = _load_documented_openapi_text()

    assert "/rfq-chatbot/v1/sessions/{session_id}/turn:" in documented
    assert "/rfq-chatbot/v1/conversations/{conversation_id}/turn:" not in documented

    for path in live_paths:
        assert f"{path}:" in documented


def test_documented_openapi_version_matches_live_schema(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200

    live_openapi = response.json()
    live_version = str(live_openapi.get("openapi", ""))
    documented_version = _documented_openapi_version(_load_documented_openapi_text())

    assert documented_version == live_version
