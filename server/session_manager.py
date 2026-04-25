"""
server.session_manager - Async session allocation and lookup for FastAPI routes.

Each session owns an isolated PraxisEnvironment instance so concurrent clients
do not share mutable scenario state. The manager is async-first: GRPO parallel
rollouts (TRL ``num_generations=8``) hit ``/reset`` + ``/step`` concurrently and
must not block the FastAPI event loop. See
``idea/Plan/Architecture/ConcurrencyModel.md`` Section 2 + Section 4.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from uuid import uuid4

from praxis_env.models import PraxisObservation
from server.praxis_environment import PraxisEnvironment

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """In-memory session record."""

    session_id: str
    env: PraxisEnvironment
    task_name: str
    created_at: float
    last_activity_at: float
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass(frozen=True)
class SessionAllocation:
    """Return type for allocate(): created session + initial observation."""

    session: Session
    observation: PraxisObservation
    metadata: dict[str, int | str | None] = field(default_factory=dict)


class SessionManager:
    """Async in-memory session registry with LRU eviction + TTL expiry."""

    def __init__(
        self,
        max_sessions: int | None = None,
        session_timeout_s: float | None = None,
    ) -> None:
        resolved_max_sessions = max_sessions
        if resolved_max_sessions is None:
            resolved_max_sessions = int(os.getenv("PRAXIS_MAX_SESSIONS", "128"))
        self.max_sessions = max(1, resolved_max_sessions)

        resolved_timeout = session_timeout_s
        if resolved_timeout is None:
            resolved_timeout = float(os.getenv("PRAXIS_SESSION_TIMEOUT_S", "900"))
        # Non-positive value disables TTL eviction entirely.
        self.session_timeout_s = resolved_timeout

        self._sessions: OrderedDict[str, Session] = OrderedDict()
        self._lock = asyncio.Lock()

    async def allocate(
        self, task_name: str, seed: int | None = None
    ) -> SessionAllocation:
        """
        Create a fresh session and initialise its environment via reset().

        ``seed`` is accepted for API compatibility; deterministic scenarios may
        ignore it until procedural tasks are introduced.
        """
        session_id = str(uuid4())
        env = PraxisEnvironment()
        # env.reset() is CPU-bound but bounded; running it inline keeps the
        # session id deterministically tied to the environment state without
        # introducing executor hand-off latency.
        observation = env.reset(task_name=task_name, seed=seed, session_id=session_id)
        now = time.time()
        session = Session(
            session_id=session_id,
            env=env,
            task_name=task_name,
            created_at=now,
            last_activity_at=now,
        )

        async with self._lock:
            self._evict_expired_unlocked()
            if len(self._sessions) >= self.max_sessions:
                evicted_session_id, evicted_session = self._sessions.popitem(last=False)
                logger.warning(
                    "Evicted session=%s task=%s reason=lru",
                    evicted_session_id,
                    evicted_session.task_name,
                )
            self._sessions[session_id] = session
        return SessionAllocation(
            session=session,
            observation=observation,
            metadata=env.last_reset_metadata,
        )

    async def get(self, session_id: str) -> Session | None:
        """Return session by id without mutating LRU order."""
        async with self._lock:
            self._evict_expired_unlocked()
            return self._sessions.get(session_id)

    async def touch(self, session_id: str) -> bool:
        """Mark session as recently used for LRU ordering."""
        async with self._lock:
            self._evict_expired_unlocked()
            session = self._sessions.get(session_id)
            if session is None:
                return False
            session.last_activity_at = time.time()
            self._sessions.move_to_end(session_id)
            return True

    async def close(self, session_id: str) -> bool:
        """Remove a session if present."""
        async with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def _evict_expired_unlocked(self) -> None:
        """
        Drop sessions whose last activity exceeds ``session_timeout_s``.

        Caller MUST hold ``self._lock``. ``OrderedDict`` iteration is in
        insertion / move-to-end order, so the oldest entries are at the front.
        """
        if self.session_timeout_s <= 0.0:
            return
        cutoff = time.time() - self.session_timeout_s
        expired_ids: list[str] = []
        for sid, session in self._sessions.items():
            if session.last_activity_at < cutoff:
                expired_ids.append(sid)
            else:
                # OrderedDict ensures everything after this is fresher; safe
                # to stop scanning early once we hit a non-expired record.
                break
        for sid in expired_ids:
            evicted = self._sessions.pop(sid, None)
            if evicted is not None:
                logger.info(
                    "Evicted session=%s task=%s reason=ttl_expired",
                    sid,
                    evicted.task_name,
                )
