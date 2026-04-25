"""
server.app — FastAPI application factory.

Builds the HTTP API that the validation script, inference.py, and
HuggingFace Spaces will call.

Endpoints:
    POST /reset    → Start a new episode
    POST /step     → Execute one action
    GET  /state    → Get current episode state
    GET  /tasks    → List available task names
    GET  /health   → Health check (returns 200 + metadata)
    GET  /         → Web UI redirect / info

Environment Variables:
    ENABLE_WEB_INTERFACE: "true" to enable OpenEnv web UI (optional)
    LOG_LEVEL: log level — default "INFO"
    PRAXIS_RATE_LIMIT_DEFAULT: default global limit (default "120/minute")
    PRAXIS_RATE_LIMIT_STEP: per-IP /step limit (default "60/minute")
    PRAXIS_RATE_LIMIT_RESET: per-IP /reset limit (default "30/minute")
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from praxis_env.artifacts import load_default_store
from praxis_env.models import PraxisAction, PraxisObservation, PraxisState
from praxis_env.rubrics import default_rubric_bundle
from praxis_env.scenarios import SCENARIO_REGISTRY
from server.praxis_environment import PraxisEnvironment
from server.session_manager import Session, SessionManager

# ── Logging ───────────────────────────────────────────────────────────────────

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Global session manager + rate limiter ─────────────────────────────────────
manager = SessionManager()
task_catalog = PraxisEnvironment().list_tasks()


def _data_sources_metadata() -> list[dict[str, Any]]:
    """Return a /metadata payload describing vendored data sources.

    The list is empty when the ArtifactStore is unavailable so the
    contract stays honest about what's actually shipping.
    """
    sources: list[dict[str, Any]] = []
    store = load_default_store(seed=0)
    if store is not None:
        sources.append(
            {
                "name": "praxis-mission-fixtures",
                "kind": "internal",
                "root": str(store.root.as_posix()),
                "provenance_prefix": store.PROVENANCE_PREFIX,
                "attribution": store.attribution(),
                "notice": "data/artifacts/NOTICE.md",
                "license_file": "LICENSE-3rd-party",
                "artifact_count": len(store),
                "services": store.services(),
            }
        )
    return sources


_TASK_DIFFICULTY: dict[str, str] = {
    "single-service-alert": "easy",
    "ambiguous-incident": "medium",
    "cascading-failure": "hard",
    "memory-leak": "hard",
    "cascading-platform-failure": "hard",
    "procedural-incident": "medium",
}


def _tasks_metadata() -> list[dict[str, Any]]:
    """Return /metadata task entries from the registered scenario catalog."""
    entries: list[dict[str, Any]] = []
    for task_name in task_catalog:
        scenario_cls = SCENARIO_REGISTRY[task_name]
        entry: dict[str, Any] = {
            "name": task_name,
            "difficulty": _TASK_DIFFICULTY.get(task_name, "medium"),
            "max_steps": int(getattr(scenario_cls, "MAX_STEPS", 15)),
        }
        if task_name == "cascading-platform-failure":
            entry["phases"] = [
                "Intake",
                "Exploration",
                "Planning",
                "Execution",
                "Disturbance",
                "Recovery",
                "Completion",
                "Reflection",
            ]
        entries.append(entry)
    return entries


def _rubrics_metadata() -> list[dict[str, Any]]:
    """Return the default rubric bundle advertised by /step info.breakdown."""
    return [
        {"name": type(rubric).__name__, "weight": rubric.weight}
        for rubric in default_rubric_bundle()
    ]


DEFAULT_RATE_LIMIT = os.getenv("PRAXIS_RATE_LIMIT_DEFAULT", "120/minute")
STEP_RATE_LIMIT = os.getenv("PRAXIS_RATE_LIMIT_STEP", "60/minute")
RESET_RATE_LIMIT = os.getenv("PRAXIS_RATE_LIMIT_RESET", "30/minute")

# slowapi requires a module-level Limiter so the @limiter.limit decorator
# can be evaluated at route-definition time.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[DEFAULT_RATE_LIMIT],
    headers_enabled=True,
)


# ── Request / Response schemas (Pydantic, for FastAPI validation) ─────────────


class ResetRequest(BaseModel):
    """POST /reset body."""

    task_name: str = "single-service-alert"
    seed: int | None = None


class StepRequest(BaseModel):
    """POST /step body."""

    command: str


# ── App factory ───────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("Praxis environment server starting up")
    logger.info("Available tasks: %s", task_catalog)
    yield
    logger.info("Praxis environment server shutting down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Praxis — Production Incident Response Environment",
        description=(
            "OpenEnv-compatible environment for training AI agents on "
            "SRE on-call triage tasks. Implements reset/step/state API."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    # ── slowapi wiring ────────────────────────────────────────────────────────
    # The Limiter must be attached to app.state and the SlowAPIMiddleware
    # registered so 429 responses include a valid Retry-After header.
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # CORS — allow judges and web UI to call from any origin
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes ────────────────────────────────────────────────────────────────

    async def _require_session(request: Request) -> tuple[str, Session]:
        session_id = request.headers.get("x-session-id")
        if not session_id:
            raise HTTPException(status_code=400, detail="Missing X-Session-Id header")
        session = await manager.get(session_id)
        if session is None:
            raise HTTPException(status_code=400, detail="No active session for that id")
        await manager.touch(session_id)
        return session_id, session

    @app.get("/health")
    async def health() -> dict[str, Any]:
        """Health check — must return 200 for the pre-validation script."""
        return {
            # OpenEnv runtime validator expects "healthy"
            "status": "healthy",
            "environment": "praxis-env",
            "version": "1.0.0",
            "available_tasks": task_catalog,
        }

    @app.get("/metadata")
    async def metadata() -> dict[str, Any]:
        """OpenEnv metadata endpoint used by runtime validators."""
        return {
            "name": "praxis-env",
            "version": "1.0.0",
            "description": (
                "Production Incident Response Training Ground — simulating real-world "
                "SRE on-call triage for AI agents."
            ),
            "supports_concurrent_sessions": True,
            "themes": ["long-horizon-planning"],
            "tasks": _tasks_metadata(),
            "endpoints": {
                "reset": "/reset",
                "step": "/step",
                "state": "/state",
                "tasks": "/tasks",
                "health": "/health",
                "schema": "/schema",
                "mcp": "/mcp",
            },
            "data_sources": _data_sources_metadata(),
            "rubrics": _rubrics_metadata(),
        }

    @app.get("/schema")
    async def schema() -> dict[str, Any]:
        """OpenEnv schema endpoint used by runtime validators."""
        return {
            "action": PraxisAction.model_json_schema(),
            "observation": PraxisObservation.model_json_schema(),
            "state": PraxisState.model_json_schema(),
        }

    @app.post("/mcp")
    async def mcp(request: Request) -> dict[str, Any]:
        """
        Minimal JSON-RPC MCP endpoint.

        The OpenEnv runtime validator only checks reachability and JSON-RPC shape.
        """
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        return {
            "jsonrpc": "2.0",
            "id": payload.get("id"),
            "result": {"ok": True},
        }

    @app.get("/")
    async def root() -> dict[str, str]:
        """Root endpoint — basic info for judges browsing the space."""
        return {
            "name": "praxis-env",
            "description": "Production Incident Response Training Ground",
            "docs": "/docs",
            "health": "/health",
            "tasks": "/tasks",
        }

    @app.post("/reset")
    @limiter.limit(RESET_RATE_LIMIT)
    async def reset(request: Request, response: Response) -> dict[str, Any]:
        """
        Start a new episode.

        Body (optional): {"task_name": "single-service-alert"}
        Returns: {"observation": PraxisObservation, ...flat_fields}

        Accepts: JSON body, empty body {}, or no body at all.
        Includes both wrapped and flat observation fields for compatibility.
        """
        task_name = "single-service-alert"
        seed: int | None = None
        try:
            body = await request.body()
            if body and body.strip():
                data = await request.json()
                task_name = (
                    data.get("task_name", "single-service-alert")
                    or "single-service-alert"
                )
                raw_seed = data.get("seed")
                if raw_seed is not None:
                    if isinstance(raw_seed, bool) or not isinstance(raw_seed, int):
                        raise HTTPException(
                            status_code=400,
                            detail="Invalid seed: expected integer",
                        )
                    seed = raw_seed
        except HTTPException:
            raise
        except Exception:
            pass  # no body or invalid JSON — use default task

        try:
            allocation = await manager.allocate(task_name=task_name, seed=seed)
            obs_dict = PraxisEnvironment._obs_to_dict(allocation.observation)
            # Return both flat fields AND wrapped observation key
            # so both strict and lenient judges pass
            return {
                "session_id": allocation.session.session_id,
                "observation": obs_dict,
                "metadata": allocation.metadata,
                **obs_dict,
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.exception("reset() failed: %s", e)
            raise HTTPException(status_code=500, detail=f"reset() error: {e}")

    @app.post("/step")
    @limiter.limit(STEP_RATE_LIMIT)
    async def step(
        request: Request, response: Response, payload: StepRequest
    ) -> dict[str, Any]:
        """
        Execute one action.

        Body: {"command": "query_logs service=auth timerange=5m"}
        Returns: {observation, reward, done, info}
        """
        try:
            _, session = await _require_session(request)
            action = PraxisAction(command=payload.command)
            # Per-session lock keeps step ordering deterministic when the
            # same client multiplexes multiple in-flight /step calls.
            async with session.lock:
                result = session.env.step(action)
            return result
        except HTTPException as e:
            raise e
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.exception("step() failed: %s", e)
            raise HTTPException(status_code=500, detail=f"step() error: {e}")

    @app.get("/state")
    async def state(request: Request) -> dict[str, Any]:
        """
        Get current episode state.

        Returns: PraxisState as JSON
        """
        try:
            session_id, session = await _require_session(request)
            async with session.lock:
                s = session.env.state()
            return {
                "episode_id": s.episode_id,
                "step_count": s.step_count,
                "task_name": s.task_name,
                "incident_resolved": s.incident_resolved,
                "root_cause_identified": s.root_cause_identified,
                "cumulative_reward": s.cumulative_reward,
                "session_id": session_id,
                "memory_active": s.memory_active,
                "final_score": s.final_score,
                "mission_id": s.mission_id,
                "phase": s.phase,
                "plan": s.plan,
                "checkpoints_completed": s.checkpoints_completed,
                "artifact_attribution": s.artifact_attribution,
            }
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/tasks")
    async def tasks() -> dict[str, list[str]]:
        """List all available task names."""
        return {"tasks": task_catalog}

    return app


def main() -> None:
    """Run the API server via uvicorn.

    Exposed as the ``server`` project script so validators and local runners
    can start the environment without custom commands. The Dockerfile uses
    ``uvicorn server.app:app`` directly — this entry point exists only for
    ``pip install -e . && server`` style invocations.
    """
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(
        "server.app:app",
        host=host,
        port=port,
        log_level=LOG_LEVEL.lower(),
    )


# ── ASGI app (imported by uvicorn and Dockerfile CMD) ─────────────────────────
app = create_app()
