import uuid

from src.models.session import ChatbotSession


def test_create_rfq_bound_session(client, db_session):
    response = client.post(
        "/rfq-chatbot/v1/sessions",
        json={
            "mode": "rfq",
            "rfq_id": "IF-25144",
            "user_id": "u1",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["user_id"] == "u1"
    assert payload["rfq_id"] == "IF-25144"
    assert payload["mode"] == "rfq_bound"
    assert payload["role"] == "estimation_dept_lead"

    persisted = db_session.query(ChatbotSession).filter_by(id=uuid.UUID(payload["id"])).first()
    assert persisted is not None
    assert persisted.mode.value == "rfq_bound"


def test_create_global_session(client):
    response = client.post(
        "/rfq-chatbot/v1/sessions",
        json={
            "mode": "global",
            "user_id": "u1",
        },
    )

    assert response.status_code == 201
    assert response.json()["rfq_id"] is None
    assert response.json()["mode"] == "portfolio"


def test_get_session_by_id(client):
    create_response = client.post(
        "/rfq-chatbot/v1/sessions",
        json={
            "mode": "global",
            "user_id": "reader",
        },
    )
    session_id = create_response.json()["id"]

    response = client.get(f"/rfq-chatbot/v1/sessions/{session_id}")

    assert response.status_code == 200
    assert response.json()["id"] == session_id
    assert response.json()["mode"] == "portfolio"


def test_pivot_portfolio_session_to_rfq_bound(client, db_session):
    create_response = client.post(
        "/rfq-chatbot/v1/sessions",
        json={
            "mode": "global",
            "user_id": "pivot-user",
        },
    )
    session_id = create_response.json()["id"]

    bind_response = client.post(
        f"/rfq-chatbot/v1/sessions/{session_id}/bind-rfq",
        json={"rfq_id": "IF-25144"},
    )

    assert bind_response.status_code == 200
    payload = bind_response.json()
    assert payload["mode"] == "rfq_bound"
    assert payload["rfq_id"] == "IF-25144"

    persisted = db_session.query(ChatbotSession).filter_by(id=uuid.UUID(session_id)).first()
    assert persisted is not None
    assert persisted.mode.value == "rfq_bound"
    assert persisted.rfq_id == "IF-25144"


def test_create_rfq_session_requires_rfq_id(client):
    response = client.post(
        "/rfq-chatbot/v1/sessions",
        json={
            "mode": "rfq",
            "user_id": "u1",
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "rfq_id is required when mode is 'rfq'"}


def test_session_creation_persists_round_trip(client, db_session):
    response = client.post(
        "/rfq-chatbot/v1/sessions",
        json={
            "mode": "global",
            "user_id": "round-trip-user",
        },
    )
    payload = response.json()

    persisted = db_session.query(ChatbotSession).filter_by(id=uuid.UUID(payload["id"])).first()

    assert response.status_code == 201
    assert persisted is not None
    assert persisted.user_id == "round-trip-user"
    assert persisted.rfq_id is None
    assert persisted.role == payload["role"]
