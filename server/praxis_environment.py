"""
server.praxis_environment — Core environment logic.

This module implements the Environment interface expected by openenv-core.
It is loaded by server/app.py and mounted into the FastAPI application.

Command parsing is delegated to server.command_parser — this module never
does raw string parsing itself.

Flow:
    POST /reset  → praxis_environment.reset() → PraxisObservation
    POST /step   → praxis_environment.step()  → StepResult
    GET  /state  → praxis_environment.state() → PraxisState

The environment delegates all scenario-specific logic to the active
BaseScenario instance (loaded from the scenario registry on reset).

Design choices:
    - The environment is stateful: one active scenario per server instance
    - Thread safety: single-threaded sequential steps (not concurrent)
    - Episode ID: generated as "{task_name}_{count}" for deterministic tracing
"""

from __future__ import annotations

import logging
import math
import random
from typing import Any

from praxis_env.mission_plan import MissionPlan
from praxis_env.models import (
    PraxisAction,
    PraxisObservation,
    PraxisState,
    StepOutcome,
    ensure_ascii_text,
)
from praxis_env.memory import PraxisMemory
from praxis_env.scenarios import get_scenario, list_tasks
from praxis_env.scenarios.base import BaseScenario
from praxis_env.trajectory import Trajectory, TrajectoryEvent
from server.command_parser import parse_command
from server.reward import MAX_REWARD, MIN_REWARD, RewardEngine, compute_task_score


PLANNING_ACTION_TYPES: frozenset[str] = frozenset(
    {
        "create_plan",
        "revise_plan",
        "checkpoint",
        "submit_report",
        "request_clarification",
    }
)
CLARIFICATION_BUDGET: int = 1

logger = logging.getLogger(__name__)


TASK_NAME_ALIASES: dict[str, str] = {
    "easy": "single-service-alert",
    "medium": "ambiguous-incident",
    "hard": "cascading-failure",
}
PROCEDURAL_DIFFICULTIES = frozenset({"easy", "medium", "hard"})


class PraxisEnvironment:
    """
    Stateful environment controller.

    Manages one active scenario at a time. The scenario tracks all
    episode state; this class is responsible for:
      - Parsing commands from PraxisAction
      - Routing commands to the active scenario
      - Serialising scenario outcomes back to OpenEnv types

    Usage (in server/app.py):
        env = PraxisEnvironment()
        obs = env.reset(task_name="single-service-alert")
        result = env.step(PraxisAction(command="query_logs service=auth timerange=5m"))
        state = env.state()
    """

    # mirrors openenv.core.env_server.interfaces.Environment.SUPPORTS_CONCURRENT_SESSIONS (S14)
    SUPPORTS_CONCURRENT_SESSIONS: bool = True
    REQUIRES_SINGLE_THREAD_EXECUTOR: bool = False

    def __init__(self) -> None:
        self._scenario: BaseScenario | None = None
        self._episode_count: int = 0
        self._last_reset_metadata: dict[str, Any] = {}
        self._memory = PraxisMemory()
        self._reward_engine = RewardEngine()
        self._investigation_history: list[str] = []
        self._session_id: str = ""
        self._trajectory: Trajectory | None = None
        self._mission_plan: MissionPlan = MissionPlan()
        self._clarifications_used: int = 0

    @staticmethod
    def resolve_task_name(task_name: str) -> str:
        """Resolve user-facing aliases to canonical scenario task names."""
        normalized = (task_name or "single-service-alert").strip().lower()
        if not normalized:
            normalized = "single-service-alert"
        return TASK_NAME_ALIASES.get(normalized, normalized)

    @staticmethod
    def resolve_task_request(task_name: str) -> tuple[str, str | None]:
        """Resolve canonical task name and optional procedural difficulty."""
        normalized = (task_name or "single-service-alert").strip().lower()
        if not normalized:
            normalized = "single-service-alert"

        if normalized.startswith("procedural-incident"):
            if normalized == "procedural-incident":
                return "procedural-incident", "medium"
            if ":" in normalized:
                _, _, suffix = normalized.partition(":")
                if suffix in PROCEDURAL_DIFFICULTIES:
                    return "procedural-incident", suffix
            if normalized.count("-") >= 2:
                suffix = normalized.rsplit("-", 1)[-1]
                if suffix in PROCEDURAL_DIFFICULTIES:
                    return "procedural-incident", suffix

        return TASK_NAME_ALIASES.get(normalized, normalized), None

    @property
    def last_reset_metadata(self) -> dict[str, Any]:
        return dict(self._last_reset_metadata)

    # ── Public API (called by FastAPI routes) ─────────────────────────────────

    def reset(
        self,
        task_name: str = "single-service-alert",
        seed: int | None = None,
        session_id: str = "",
    ) -> PraxisObservation:
        """
        Start a new episode with the named scenario.

        Args:
            task_name: Scenario to load (see list_tasks() for options).
            seed: Optional deterministic seed for procedural scenarios.

        Returns:
            Initial PraxisObservation with the incident alert and system status.

        Raises:
            ValueError: if task_name is not registered.
        """
        canonical_task_name, procedural_difficulty = self.resolve_task_request(
            task_name
        )
        resolved_seed = seed

        self._episode_count += 1
        episode_id = f"{canonical_task_name}_{self._episode_count}"

        logger.info(
            "reset() -> episode_id=%s task=%s requested_task=%s seed=%s",
            episode_id,
            canonical_task_name,
            task_name,
            resolved_seed,
        )

        if canonical_task_name == "procedural-incident":
            if resolved_seed is None:
                resolved_seed = random.randint(0, 2**31 - 1)
            self._scenario = get_scenario(
                canonical_task_name,
                seed=resolved_seed,
                difficulty=procedural_difficulty,
            )
        elif canonical_task_name == "cascading-platform-failure":
            # Mission scenarios accept an optional seed for deterministic
            # disturbance injection. Fall back to 0 so omitting `seed=`
            # gives the same trajectory across repeated /reset calls.
            self._scenario = get_scenario(
                canonical_task_name,
                seed=resolved_seed,
            )
        else:
            self._scenario = get_scenario(canonical_task_name)

        self._last_reset_metadata = {
            "seed": resolved_seed,
            "difficulty": (
                procedural_difficulty
                if canonical_task_name == "procedural-incident"
                else None
            ),
            "task_name": canonical_task_name,
        }
        cutoff = getattr(
            self._scenario,
            "MEMORY_CUTOFF_OVERRIDE",
            PraxisMemory.CONTEXT_CUTOFF_STEP,
        )
        self._memory.CONTEXT_CUTOFF_STEP = int(cutoff)
        self._memory.reset()
        self._investigation_history = []
        self._session_id = session_id
        self._scenario.reset(episode_id=episode_id)
        self._trajectory = Trajectory(
            task_name=canonical_task_name,
            max_steps=self._scenario.MAX_STEPS,
        )
        self._mission_plan = MissionPlan()
        self._clarifications_used = 0

        obs = self._scenario.get_observation()
        # Override investigation_result with scenario's initial text
        obs.investigation_result = ensure_ascii_text(
            self._scenario.get_initial_observation_text()
        )
        obs.memory_active = self._memory.is_active(self._scenario._step_count)
        obs.saved_findings_count = len(self._memory.saved_findings)
        self._populate_mission_obs(obs)
        return obs

    def step(self, action: PraxisAction) -> dict[str, Any]:
        """
        Execute one action and return the raw result dict.

        Args:
            action: PraxisAction with a command string.

        Returns:
            Dict with keys: observation, reward, done, info
            (serialisable to JSON for the FastAPI response).

        Raises:
            RuntimeError: if called before reset().
        """
        if self._scenario is None:
            raise RuntimeError("step() called before reset(). Call reset() first.")

        logger.debug("step() → command=%r", action.command)

        # The environment owns step_count and cumulative reward bookkeeping.
        # Scenarios return domain outcomes without mutating those counters.
        # Parse command string -> structured ParsedCommand
        parsed = parse_command(action.command)

        # Score-cap short-circuit: stop runaway reward farming. Planning
        # and terminal actions (submit_report, escalate, plan/checkpoint/
        # clarification) are flow-control rather than reward-farming
        # surfaces, and Mission scenarios *require* submit_report to
        # flip the resolution gate (Issue #37). Let those through even
        # at cap so the resolution logic can still fire.
        _flow_actions = PLANNING_ACTION_TYPES | {"escalate"}
        if (
            self._scenario.clamp_reward(self._scenario._cumulative_reward) >= MAX_REWARD
            and parsed.action_type not in _flow_actions
        ):
            obs = self._scenario.get_observation()
            obs.step_number = self._scenario._step_count
            return {
                "observation": self._obs_to_dict(obs),
                "reward": MIN_REWARD,
                "done": True,
                "info": {
                    "error": "episode_score_cap_reached",
                    "score_cap_reached": True,
                },
            }

        current_step = self._scenario._step_count
        reward_event: str | None = None

        if parsed.action_type in {"save_finding", "recall_memory"}:
            outcome, reward_event = self._handle_memory_action(
                parsed.action_type, parsed.params
            )
        elif parsed.action_type in PLANNING_ACTION_TYPES:
            outcome, reward_event = self._handle_planning_action(
                parsed.action_type, parsed.params
            )
        elif (
            parsed.action_type in {"query_logs", "check_logs"}
            and current_step >= self._memory.CONTEXT_CUTOFF_STEP
        ):
            reward_event = "memory.illegal_log_after_cutoff"
            result_text = (
                "Log access is disabled after context cutoff.\n"
                "[CONTEXT LIMIT] Use save_finding and recall_memory instead."
            )
            reward = self._score_memory_event(reward_event)
            outcome = StepOutcome(
                investigation_result=result_text,
                reward=reward,
                done=self._scenario.is_done(),
                incident_resolved=self._scenario._incident_resolved,
                root_cause_identified=self._scenario._root_cause_identified,
                info={"event": reward_event},
            )
        else:
            # Delegate to active scenario
            outcome = self._scenario.step(parsed)
        raw_step_reward = self._scenario.clamp_reward(outcome.reward)
        current_cumulative_reward = self._scenario.clamp_reward(
            self._scenario._cumulative_reward
        )

        # The environment is the final authority for emitted rewards: once the
        # episode budget is nearly exhausted, trim the outgoing reward so the
        # cumulative task score exposed to validators remains strictly < 1.0.
        remaining_budget = max(0.0, MAX_REWARD - current_cumulative_reward)
        step_reward = min(raw_step_reward, remaining_budget)
        # Guard against rounding-to-zero edge cases: if there's still some
        # remaining budget, always emit a strictly-positive reward.
        if 0.0 < remaining_budget and step_reward <= 0.0:
            step_reward = remaining_budget
        # Ensure emitted reward is strictly within (0, 1) even after any
        # downstream float formatting/serialization.
        if step_reward <= 0.0:
            step_reward = math.nextafter(0.0, 1.0)
        elif step_reward >= 1.0:
            step_reward = math.nextafter(1.0, 0.0)
        next_cumulative_reward = self._scenario.clamp_reward(
            current_cumulative_reward + step_reward
        )
        score_cap_reached = next_cumulative_reward >= MAX_REWARD

        # Update scenario's investigation result for next observation
        self._scenario._last_investigation_result = outcome.investigation_result
        self._investigation_history.append(outcome.investigation_result)
        self._scenario._step_count += 1
        self._scenario._cumulative_reward = next_cumulative_reward

        # Build the next observation
        obs = self._scenario.get_observation()
        # Override step_number to reflect the step just taken
        obs.step_number = self._scenario._step_count
        memory_active = self._memory.is_active(self._scenario._step_count)
        if memory_active:
            obs.investigation_result = self._memory.get_observation_context(
                self._investigation_history,
                self._scenario._step_count,
            )
        obs.memory_active = memory_active
        obs.saved_findings_count = len(self._memory.saved_findings)
        self._populate_mission_obs(obs)

        info = dict(outcome.info or {})
        if reward_event is not None:
            info["event"] = reward_event
        if score_cap_reached:
            info["score_cap_reached"] = True

        episode_done = outcome.done or self._scenario.is_done() or score_cap_reached

        if self._trajectory is not None:
            self._trajectory.append(
                TrajectoryEvent(
                    step_number=obs.step_number,
                    action_type=parsed.action_type,
                    params=dict(parsed.params),
                    event_tag=info.get("event") if isinstance(info, dict) else None,
                    reward=float(step_reward),
                    done=bool(episode_done),
                    incident_resolved=bool(self._scenario._incident_resolved),
                    root_cause_identified=bool(self._scenario._root_cause_identified),
                )
            )
            info["breakdown"] = self._reward_engine.score_trajectory(
                self._trajectory
            ).to_dict()

        logger.debug(
            "step() → reward=%.3f done=%s step=%d",
            step_reward,
            episode_done,
            obs.step_number,
        )

        result = {
            "observation": self._obs_to_dict(obs),
            "reward": step_reward,
            "done": episode_done,
            "info": info,
        }
        return result

    def state(self) -> PraxisState:
        """
        Return current episode metadata without the full observation.

        Returns:
            PraxisState snapshot.

        Raises:
            RuntimeError: if called before reset().
        """
        if self._scenario is None:
            raise RuntimeError("state() called before reset(). Call reset() first.")
        state = self._scenario.get_state()
        state.memory_active = self._memory.is_active(self._scenario._step_count)
        state.session_id = self._session_id
        state.plan = list(self._mission_plan.milestones)
        state.checkpoints_completed = list(self._mission_plan.checkpoints_completed)
        state.mission_id = getattr(self._scenario, "mission_id", None)
        state.phase = getattr(self._scenario, "current_phase", None)
        state.artifact_attribution = list(
            getattr(self._scenario, "artifact_attribution", [])
        )
        # Once the scenario is terminal we freeze the ADR-20 outcome x
        # efficiency score on the state snapshot so /state callers (the
        # baseline inference script + judges) see a stable final number.
        # Mid-episode it stays None so callers can distinguish "running"
        # from "lost" (which would otherwise both be clamped to 0.01).
        if self._scenario.is_done():
            state.final_score = compute_task_score(
                state, max_steps=self._scenario.MAX_STEPS
            )
        return state

    def list_tasks(self) -> list[str]:
        """Return all available task names."""
        return list_tasks()

    @staticmethod
    def _obs_to_dict(obs: PraxisObservation) -> dict[str, Any]:
        """Convert PraxisObservation to a JSON-serialisable dict."""
        return {
            "alert_summary": obs.alert_summary,
            "system_status": obs.system_status,
            "investigation_result": obs.investigation_result,
            "available_commands": obs.available_commands,
            "time_elapsed_minutes": obs.time_elapsed_minutes,
            "severity": obs.severity,
            "services_affected": obs.services_affected,
            "step_number": obs.step_number,
            "memory_active": obs.memory_active,
            "saved_findings_count": obs.saved_findings_count,
            "mission_id": obs.mission_id,
            "phase": obs.phase,
            "time_budget": obs.time_budget,
            "pending_objectives": list(obs.pending_objectives),
        }

    def _populate_mission_obs(self, obs: PraxisObservation) -> None:
        """Stamp planning fields onto an outbound observation.

        Mission-class scenarios expose ``mission_id`` / ``current_phase`` /
        ``time_budget`` attributes; legacy scenarios leave them as ``None``.
        ``pending_objectives`` always reflects the live MissionPlan so
        non-mission scenarios still surface what the agent has planned.
        """
        if self._scenario is None:
            return
        obs.mission_id = getattr(self._scenario, "mission_id", None)
        obs.phase = getattr(self._scenario, "current_phase", None)
        scenario_budget = getattr(self._scenario, "time_budget", None)
        obs.time_budget = int(scenario_budget) if scenario_budget is not None else None
        obs.pending_objectives = list(self._mission_plan.pending_objectives)

    def _score_memory_event(self, event: str) -> float:
        """Score memory event tags through the shared reward engine."""
        if self._scenario is None:
            raise RuntimeError("Cannot score memory event before reset().")
        result = self._reward_engine.score(
            task_name=self._scenario.NAME,
            event=event,
            step_number=self._scenario._step_count + 1,
            max_steps=self._scenario.MAX_STEPS,
            root_cause_identified=self._scenario._root_cause_identified,
        )
        return result.reward

    def _score_planning_event(self, event: str) -> float:
        """Score plan/checkpoint/submit_report/clarification events."""
        if self._scenario is None:
            raise RuntimeError("Cannot score planning event before reset().")
        result = self._reward_engine.score(
            task_name=self._scenario.NAME,
            event=event,
            step_number=self._scenario._step_count + 1,
            max_steps=self._scenario.MAX_STEPS,
            # Allow submit_report.* to surface even before diagnosis is
            # locked in — the consistency gate (matching world state) is
            # handled inside the planning handler.
            root_cause_identified=True,
        )
        return result.reward

    def _handle_planning_action(
        self,
        action_type: str,
        params: dict[str, str],
    ) -> tuple[StepOutcome, str]:
        """Execute a planning command and return outcome + reward event.

        Mission-class scenarios may further constrain validation by
        exposing ``mission_world_state()`` (a dict keyed for MissionPlan)
        and ``submit_report_consistent(report_root_causes)`` hooks. Legacy
        scenarios get a sensible scenario-agnostic default.
        """
        if self._scenario is None:
            raise RuntimeError("Cannot handle planning action before reset().")

        if action_type == "create_plan":
            return self._handle_create_plan(params)
        if action_type == "revise_plan":
            return self._handle_revise_plan(params)
        if action_type == "checkpoint":
            return self._handle_checkpoint(params)
        if action_type == "submit_report":
            return self._handle_submit_report(params)
        if action_type == "request_clarification":
            return self._handle_request_clarification(params)

        # Defensive guard — PLANNING_ACTION_TYPES is the source of truth.
        raise ValueError(f"Unhandled planning action: {action_type!r}")

    def _handle_create_plan(self, params: dict[str, str]) -> tuple[StepOutcome, str]:
        assert self._scenario is not None
        raw_milestones = params.get("milestones", "")
        milestones = [m.strip() for m in raw_milestones.split(",") if m.strip()]
        if not milestones:
            event = "plan.created_invalid"
            result_text = (
                "Invalid create_plan command.\n"
                "Expected: create_plan milestones=<m1,m2,m3,...>"
            )
        elif self._mission_plan.milestones:
            # Plan already exists - tell the agent to use revise_plan.
            event = "plan.created_invalid"
            result_text = (
                "Plan already exists.\n"
                f"Current milestones: {', '.join(self._mission_plan.milestones)}\n"
                "Use revise_plan add=<new>, replace=<old> with=<new>, or remove=<old>."
            )
        else:
            self._mission_plan.create(milestones)
            cutoff = self._memory.CONTEXT_CUTOFF_STEP
            if (self._scenario._step_count + 1) <= cutoff:
                event = "plan.created_pre_cutoff"
            else:
                event = "plan.created_post_cutoff"
            result_text = (
                "Plan created with "
                f"{len(self._mission_plan.milestones)} milestones: "
                f"{', '.join(self._mission_plan.milestones)}"
            )
        reward = self._score_planning_event(event)
        outcome = StepOutcome(
            investigation_result=result_text,
            reward=reward,
            done=self._scenario.is_done(),
            incident_resolved=self._scenario._incident_resolved,
            root_cause_identified=self._scenario._root_cause_identified,
            info={"event": event},
        )
        return outcome, event

    def _handle_revise_plan(self, params: dict[str, str]) -> tuple[StepOutcome, str]:
        assert self._scenario is not None
        had_evidence = self._has_investigation_evidence()
        if not self._mission_plan.milestones:
            event = "plan.revise_no_op"
            result_text = "No plan to revise. Use create_plan first."
        else:
            applied = self._mission_plan.revise(
                replace=params.get("replace"),
                with_=params.get("with"),
                add=params.get("add"),
                remove=params.get("remove"),
            )
            if not applied:
                event = "plan.revise_no_op"
                result_text = (
                    "Revision had no effect.\n"
                    "Expected one of: revise_plan add=<new>, "
                    "revise_plan remove=<old>, "
                    "revise_plan replace=<old> with=<new>."
                )
            elif had_evidence:
                event = "plan.revised_after_evidence"
                result_text = (
                    f"Plan revised. Current milestones: "
                    f"{', '.join(self._mission_plan.milestones)}"
                )
            else:
                event = "plan.revised_no_evidence"
                result_text = (
                    "Plan revised before any investigation evidence. "
                    f"Current milestones: "
                    f"{', '.join(self._mission_plan.milestones)}"
                )
        reward = self._score_planning_event(event)
        outcome = StepOutcome(
            investigation_result=result_text,
            reward=reward,
            done=self._scenario.is_done(),
            incident_resolved=self._scenario._incident_resolved,
            root_cause_identified=self._scenario._root_cause_identified,
            info={"event": event},
        )
        return outcome, event

    def _handle_checkpoint(self, params: dict[str, str]) -> tuple[StepOutcome, str]:
        assert self._scenario is not None
        milestone = (params.get("milestone") or "").strip()
        world_state = self._mission_world_state()
        accepted = self._mission_plan.checkpoint(milestone, world_state)
        if accepted:
            event = "checkpoint.consistent"
            result_text = f"Checkpoint accepted: {milestone}"
        else:
            event = "checkpoint.invalid"
            if not milestone:
                result_text = (
                    "Invalid checkpoint command.\nExpected: checkpoint milestone=<name>"
                )
            elif milestone not in self._mission_plan.milestones:
                result_text = (
                    f"Milestone {milestone!r} is not part of the current plan."
                )
            else:
                result_text = (
                    f"Milestone {milestone!r} could not be checkpointed "
                    "given the current world state."
                )
        reward = self._score_planning_event(event)
        outcome = StepOutcome(
            investigation_result=result_text,
            reward=reward,
            done=self._scenario.is_done(),
            incident_resolved=self._scenario._incident_resolved,
            root_cause_identified=self._scenario._root_cause_identified,
            info={"event": event},
        )
        return outcome, event

    def _handle_submit_report(self, params: dict[str, str]) -> tuple[StepOutcome, str]:
        assert self._scenario is not None
        raw_root_causes = params.get("root_causes", "")
        report_causes = [c.strip() for c in raw_root_causes.split(",") if c.strip()]
        resolution = (params.get("resolution") or "").strip()
        if not report_causes:
            event = "submit_report.inconsistent_with_world_state"
            result_text = (
                "Invalid submit_report command.\n"
                "Expected: submit_report root_causes=<c1,c2> resolution=<text>"
            )
        elif self._submit_report_consistent(report_causes, resolution):
            event = "submit_report.consistent_with_world_state"
            result_text = f"Report accepted. Root causes: {', '.join(report_causes)}"
        elif not self._scenario._root_cause_identified:
            event = "submit_report.no_diagnosis"
            result_text = (
                "Report rejected: root cause has not yet been confirmed via diagnose."
            )
        else:
            event = "submit_report.inconsistent_with_world_state"
            result_text = (
                "Report rejected: claimed root causes are inconsistent "
                "with observed world state."
            )
        reward = self._score_planning_event(event)
        outcome = StepOutcome(
            investigation_result=result_text,
            reward=reward,
            done=self._scenario.is_done(),
            incident_resolved=self._scenario._incident_resolved,
            root_cause_identified=self._scenario._root_cause_identified,
            info={"event": event},
        )
        return outcome, event

    def _handle_request_clarification(
        self, params: dict[str, str]
    ) -> tuple[StepOutcome, str]:
        assert self._scenario is not None
        topic = (params.get("topic") or "next").strip().lower()
        if self._clarifications_used >= CLARIFICATION_BUDGET:
            event = "clarification.exhausted"
            result_text = (
                "Clarification budget exhausted for this episode "
                f"(limit={CLARIFICATION_BUDGET})."
            )
        else:
            self._clarifications_used += 1
            event = "clarification.served"
            result_text = self._format_clarification(topic)
        reward = self._score_planning_event(event)
        outcome = StepOutcome(
            investigation_result=result_text,
            reward=reward,
            done=self._scenario.is_done(),
            incident_resolved=self._scenario._incident_resolved,
            root_cause_identified=self._scenario._root_cause_identified,
            info={"event": event, "clarifications_used": self._clarifications_used},
        )
        return outcome, event

    _INVESTIGATION_ACTION_TYPES: frozenset[str] = frozenset(
        {
            "query_logs",
            "check_metrics",
            "check_deps",
            "check_config",
            "check_runbook",
            "diagnose",
            "recall_memory",
        }
    )

    def _has_investigation_evidence(self) -> bool:
        """True iff the agent has executed at least one investigation action.

        ``revise_plan`` semantically rewards revisions that reflect new
        evidence; pure planning -> revise toggles must not earn that
        credit. We check the trajectory rather than ``_investigation_history``
        (which fills on every step, including planning ones).
        """
        if self._trajectory is None:
            return False
        for event in self._trajectory.events:
            if event.action_type in self._INVESTIGATION_ACTION_TYPES:
                return True
            tag = event.event_tag or ""
            if tag.startswith(("investigation.", "memory.")):
                return True
        return False

    def _mission_world_state(self) -> dict[str, Any]:
        """Snapshot of the live scenario state used by MissionPlan checks."""
        if self._scenario is None:
            return {}
        if hasattr(self._scenario, "mission_world_state"):
            try:
                return dict(self._scenario.mission_world_state())  # type: ignore[attr-defined]
            except Exception:
                logger.exception("scenario.mission_world_state() failed")
        return {}

    def _submit_report_consistent(
        self, root_causes: list[str], resolution: str
    ) -> bool:
        """Default consistency check for submit_report.

        Mission-class scenarios may override via ``submit_report_consistent``;
        the default rule is "scenario has flagged the root cause as
        identified", which preserves baseline-friendly behaviour without
        leaking ground truth into legacy scenarios.
        """
        if self._scenario is None:
            return False
        check = getattr(self._scenario, "submit_report_consistent", None)
        if callable(check):
            try:
                return bool(check(root_causes=root_causes, resolution=resolution))
            except Exception:
                logger.exception("scenario.submit_report_consistent() failed")
                return False
        return bool(self._scenario._root_cause_identified)

    def _format_clarification(self, topic: str) -> str:
        """Produce a small clarification payload tied to scenario state."""
        if self._scenario is None:
            return ""
        affected = list(getattr(self._scenario, "INITIAL_AFFECTED_SERVICES", []))
        if topic == "service" and affected:
            return f"Affected services: {', '.join(affected)}"
        if topic == "artifact":
            attribution = getattr(self._scenario, "artifact_attribution", []) or []
            if attribution:
                return f"Artifact sources: {', '.join(attribution)}"
            return "No vendored artifacts referenced for this scenario."
        # 'next' / unknown -> hint at the next pending milestone.
        pending = self._mission_plan.pending_objectives
        if pending:
            return f"Next pending milestone: {pending[0]}"
        return "No pending objectives. Run create_plan or finish remediation."

    def _handle_memory_action(
        self,
        action_type: str,
        params: dict[str, str],
    ) -> tuple[StepOutcome, str]:
        """Execute a memory command and return deterministic outcome + event tag."""
        if self._scenario is None:
            raise RuntimeError("Cannot handle memory action before reset().")

        cutoff_state = (
            "after_cutoff"
            if self._memory.is_active(self._scenario._step_count)
            else "before_cutoff"
        )

        if action_type == "save_finding":
            key = params.get("key", "").strip()
            value = params.get("value", "").strip()
            if not key or not value:
                event = "invalid_input"
                result_text = (
                    "Invalid save_finding command.\n"
                    "Expected: save_finding key=<key> value=<finding>"
                )
                reward = self._score_memory_event(event)
            else:
                event = f"memory.save_finding.{cutoff_state}"
                result_text = self._memory.save_finding(key, value)
                reward = self._score_memory_event(event)
        else:
            key = params.get("key")
            has_findings = bool(self._memory.saved_findings)
            if cutoff_state == "after_cutoff" and not has_findings:
                event = "memory.empty_recall_after_cutoff"
            else:
                event = f"memory.recall_memory.{cutoff_state}"
            result_text = self._memory.recall_memory(key=key)
            reward = self._score_memory_event(event)

        outcome = StepOutcome(
            investigation_result=result_text,
            reward=reward,
            done=self._scenario.is_done(),
            incident_resolved=self._scenario._incident_resolved,
            root_cause_identified=self._scenario._root_cause_identified,
            info={"event": event},
        )
        return outcome, event
