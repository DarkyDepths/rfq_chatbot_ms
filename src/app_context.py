"""Minimal application context for Phase-0 bootstrap wiring."""


def get_smoke_payload() -> dict[str, str]:
    """Return a static smoke payload for bootstrap verification."""

    return {
        "status": "ok",
        "service": "rfq_chatbot_ms",
        "phase": "phase-0",
    }
