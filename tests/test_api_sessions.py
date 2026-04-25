"""
tests/test_api_sessions.py - Session header contract tests.
"""

from fastapi.testclient import TestClient

from server.app import app


client = TestClient(app)


def _reset_session(task_name: str = "single-service-alert") -> str:
    response = client.post("/reset", json={"task_name": task_name})
    assert response.status_code == 200
    return response.json()["session_id"]


def test_step_requires_session_header():
    response = client.post(
        "/step", json={"command": "query_logs service=auth timerange=5m"}
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Missing X-Session-Id header"}


def test_step_rejects_unknown_session_header():
    response = client.post(
        "/step",
        json={"command": "query_logs service=auth timerange=5m"},
        headers={"X-Session-Id": "no-such-session"},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "No active session for that id"}


def test_state_requires_session_header():
    response = client.get("/state")
    assert response.status_code == 400
    assert response.json() == {"detail": "Missing X-Session-Id header"}


def test_state_rejects_unknown_session_header():
    response = client.get("/state", headers={"X-Session-Id": "no-such-session"})
    assert response.status_code == 400
    assert response.json() == {"detail": "No active session for that id"}


def test_step_and_state_use_session_id():
    session_id = _reset_session()

    step_response = client.post(
        "/step",
        json={"command": "query_logs service=auth timerange=5m"},
        headers={"X-Session-Id": session_id},
    )
    assert step_response.status_code == 200
    payload = step_response.json()
    assert "observation" in payload
    assert "reward" in payload
    assert "done" in payload

    state_response = client.get("/state", headers={"X-Session-Id": session_id})
    assert state_response.status_code == 200
    state_payload = state_response.json()
    assert state_payload["session_id"] == session_id
    assert state_payload["step_count"] >= 1
