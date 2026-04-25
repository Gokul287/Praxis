"""
tests/test_api_reset.py - HTTP contract tests for POST /reset.

Guards the judge-critical behavior where /reset must accept:
- no request body
- an empty JSON body
- an explicit task_name
"""

from fastapi.testclient import TestClient
from uuid import UUID

from server.app import app


client = TestClient(app)


def test_reset_accepts_no_body_and_uses_default_task():
    response = client.post("/reset")
    assert response.status_code == 200

    payload = response.json()
    assert UUID(payload["session_id"]).version == 4
    assert "observation" in payload
    assert payload["step_number"] == 0
    assert payload["severity"] == "P2"


def test_reset_accepts_empty_json_body_and_uses_default_task():
    response = client.post("/reset", json={})
    assert response.status_code == 200

    payload = response.json()
    assert UUID(payload["session_id"]).version == 4
    assert "observation" in payload
    assert payload["step_number"] == 0
    assert payload["severity"] == "P2"


def test_reset_accepts_explicit_task_name():
    response = client.post("/reset", json={"task_name": "cascading-failure"})
    assert response.status_code == 200

    payload = response.json()
    assert UUID(payload["session_id"]).version == 4
    assert "observation" in payload
    assert payload["step_number"] == 0
    assert payload["severity"] == "P1"


def test_reset_accepts_easy_alias_task_name():
    response = client.post("/reset", json={"task_name": "easy"})
    assert response.status_code == 200

    payload = response.json()
    assert UUID(payload["session_id"]).version == 4
    assert "observation" in payload
    assert payload["step_number"] == 0
    assert payload["severity"] == "P2"


def test_reset_accepts_medium_alias_task_name():
    response = client.post("/reset", json={"task_name": "medium"})
    assert response.status_code == 200

    payload = response.json()
    assert UUID(payload["session_id"]).version == 4
    assert "observation" in payload
    assert payload["step_number"] == 0
    assert payload["severity"] == "P2"


def test_reset_accepts_hard_alias_task_name():
    response = client.post("/reset", json={"task_name": "hard"})
    assert response.status_code == 200

    payload = response.json()
    assert UUID(payload["session_id"]).version == 4
    assert "observation" in payload
    assert payload["step_number"] == 0
    assert payload["severity"] == "P1"


def test_reset_rejects_unknown_task_name():
    response = client.post("/reset", json={"task_name": "no-such-task"})
    assert response.status_code == 400

    payload = response.json()
    assert "detail" in payload
    assert "Unknown task" in payload["detail"]
