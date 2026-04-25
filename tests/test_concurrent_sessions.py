"""
tests/test_concurrent_sessions.py - Concurrency + rate-limit smokes.

These exercise the safety-net stack added in Issue #33:
  * SessionManager isolates per-session state under concurrent /reset+/step
    calls and never leaks observations across sessions.
  * SlowAPI rate limiting on /step kicks in well before unsafe rates and
    returns a 429 (with Retry-After) instead of melting the event loop.
"""

from __future__ import annotations

import asyncio
import importlib
import os

import pytest
from httpx import ASGITransport, AsyncClient

from server.session_manager import SessionManager


pytestmark = pytest.mark.asyncio


async def _reset(client: AsyncClient, task: str = "single-service-alert") -> str:
    response = await client.post("/reset", json={"task_name": task})
    assert response.status_code == 200
    return response.json()["session_id"]


async def test_session_manager_supports_parallel_allocation() -> None:
    manager = SessionManager(max_sessions=64)
    allocations = await asyncio.gather(
        *[manager.allocate(task_name="single-service-alert") for _ in range(16)]
    )
    session_ids = {a.session.session_id for a in allocations}
    assert len(session_ids) == 16


async def test_concurrent_step_calls_isolate_state_per_session() -> None:
    """
    Two clients running /reset + /step simultaneously must observe their own
    step_count, not the other session's.
    """
    from server.app import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sid_a, sid_b = await asyncio.gather(_reset(client), _reset(client))

        async def take_step(sid: str, command: str) -> dict:
            r = await client.post(
                "/step",
                json={"command": command},
                headers={"X-Session-Id": sid},
            )
            assert r.status_code == 200
            return r.json()

        a_first, b_first = await asyncio.gather(
            take_step(sid_a, "query_logs service=auth timerange=5m"),
            take_step(sid_b, "query_logs service=database timerange=10m"),
        )
        assert a_first["observation"]["step_number"] == 1
        assert b_first["observation"]["step_number"] == 1

        a_second = await take_step(sid_a, "check_metrics service=auth metric=latency")
        assert a_second["observation"]["step_number"] == 2

        # session_b should still be at step_number == 1 because nothing has
        # been stepped on it again.
        state_b = await client.get("/state", headers={"X-Session-Id": sid_b})
        assert state_b.status_code == 200
        assert state_b.json()["step_count"] == 1


async def test_step_rate_limit_returns_429() -> None:
    """
    Configure a tight rate limit, then hammer /step until SlowAPI rejects.
    """
    os.environ["PRAXIS_RATE_LIMIT_STEP"] = "5/minute"
    os.environ["PRAXIS_RATE_LIMIT_RESET"] = "30/minute"
    os.environ["PRAXIS_RATE_LIMIT_DEFAULT"] = "120/minute"

    import server.app as app_module

    importlib.reload(app_module)
    app = app_module.app

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            sid = await _reset(client)
            statuses: list[int] = []
            for _ in range(8):
                r = await client.post(
                    "/step",
                    json={"command": "query_logs service=auth timerange=5m"},
                    headers={"X-Session-Id": sid},
                )
                statuses.append(r.status_code)
            assert 429 in statuses, f"Expected 429 in {statuses!r}"
    finally:
        for env_var in (
            "PRAXIS_RATE_LIMIT_STEP",
            "PRAXIS_RATE_LIMIT_RESET",
            "PRAXIS_RATE_LIMIT_DEFAULT",
        ):
            os.environ.pop(env_var, None)
        importlib.reload(app_module)
