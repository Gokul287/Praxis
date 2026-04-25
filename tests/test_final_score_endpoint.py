"""
tests/test_final_score_endpoint.py - /state returns ADR-20 final_score after done.

Drives a full single-service-alert episode through the optimal path so the
scenario reports incident_resolved + root_cause_identified, then verifies
that the /state response now exposes a non-None final_score equal to the
formula `cumulative_reward * (1 - step_count/max_steps)`, clamped.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from praxis_env.models import PraxisState
from server.app import app
from server.reward import compute_task_score


client = TestClient(app)


OPTIMAL_SINGLE_SERVICE_ALERT = [
    "query_logs service=auth timerange=5m",
    "check_config service=auth",
    "diagnose root_cause=bad_config",
    "rollback_deploy service=auth",
]


def _state_dict_from_response(payload: dict) -> dict:
    return payload


def test_state_final_score_is_none_until_episode_done() -> None:
    reset_response = client.post("/reset", json={"task_name": "single-service-alert"})
    assert reset_response.status_code == 200
    session_id = reset_response.json()["session_id"]
    headers = {"X-Session-Id": session_id}

    state = client.get("/state", headers=headers).json()
    assert state["final_score"] is None


def test_state_endpoint_exposes_mission_metadata() -> None:
    reset_response = client.post(
        "/reset", json={"task_name": "cascading-platform-failure", "seed": 42}
    )
    assert reset_response.status_code == 200
    session_id = reset_response.json()["session_id"]
    headers = {"X-Session-Id": session_id}

    state = client.get("/state", headers=headers).json()
    assert state["mission_id"] == "mission-0000002a"
    assert state["phase"] == "intake"
    assert state["plan"] == []
    assert state["checkpoints_completed"] == []
    assert state["artifact_attribution"]
    assert any("praxis:fixtures" in line for line in state["artifact_attribution"])


def test_state_final_score_uses_outcome_times_efficiency() -> None:
    reset_response = client.post("/reset", json={"task_name": "single-service-alert"})
    assert reset_response.status_code == 200
    session_id = reset_response.json()["session_id"]
    headers = {"X-Session-Id": session_id}

    done = False
    for command in OPTIMAL_SINGLE_SERVICE_ALERT:
        step_response = client.post("/step", json={"command": command}, headers=headers)
        assert step_response.status_code == 200
        body = step_response.json()
        done = bool(body["done"])

    assert done is True

    state = client.get("/state", headers=headers).json()
    assert state["incident_resolved"] is True
    assert state["root_cause_identified"] is True
    assert state["final_score"] is not None
    assert 0.01 <= state["final_score"] <= 0.99

    # Independent recomputation using the same formula must match exactly.
    snapshot = PraxisState(
        episode_id=state["episode_id"],
        step_count=state["step_count"],
        task_name=state["task_name"],
        incident_resolved=state["incident_resolved"],
        root_cause_identified=state["root_cause_identified"],
        cumulative_reward=state["cumulative_reward"],
    )
    expected = compute_task_score(snapshot, max_steps=15)
    assert state["final_score"] == pytest.approx(expected, abs=1e-9)
