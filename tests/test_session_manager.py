"""tests/test_session_manager.py - Session allocation behavior (async)."""

from __future__ import annotations

import asyncio

import pytest

from server.session_manager import SessionManager


pytestmark = pytest.mark.asyncio


async def test_allocate_passes_session_id_into_environment_state() -> None:
    manager = SessionManager(max_sessions=4)
    allocation = await manager.allocate(task_name="single-service-alert")
    state = allocation.session.env.state()
    assert state.session_id == allocation.session.session_id


async def test_lru_eviction_drops_oldest() -> None:
    manager = SessionManager(max_sessions=2)
    a = await manager.allocate(task_name="single-service-alert")
    b = await manager.allocate(task_name="single-service-alert")
    c = await manager.allocate(task_name="single-service-alert")
    assert await manager.get(a.session.session_id) is None
    assert await manager.get(b.session.session_id) is not None
    assert await manager.get(c.session.session_id) is not None


async def test_ttl_eviction_uses_session_timeout() -> None:
    manager = SessionManager(max_sessions=4, session_timeout_s=0.05)
    allocation = await manager.allocate(task_name="single-service-alert")
    # Sleep past the TTL window then trigger eviction via get().
    await asyncio.sleep(0.1)
    assert await manager.get(allocation.session.session_id) is None


async def test_touch_updates_lru_ordering() -> None:
    manager = SessionManager(max_sessions=2)
    a = await manager.allocate(task_name="single-service-alert")
    b = await manager.allocate(task_name="single-service-alert")
    # Refresh `a` so it becomes the most-recently-used; allocating a third
    # session should now evict `b`.
    await manager.touch(a.session.session_id)
    c = await manager.allocate(task_name="single-service-alert")
    assert await manager.get(a.session.session_id) is not None
    assert await manager.get(b.session.session_id) is None
    assert await manager.get(c.session.session_id) is not None
