"""
tests.test_mission_plan - Unit + integration tests for Issue #36.

Covers:
  * The pure ``MissionPlan`` dataclass (create / revise / checkpoint).
  * The five new planning command handlers wired into PraxisEnvironment
    (`create_plan`, `revise_plan`, `checkpoint`, `submit_report`,
    `request_clarification`).
  * Reward-event tags that the rubric system reads from the trajectory.
  * Mission-aware fields exposed on PraxisObservation / PraxisState.
"""

from __future__ import annotations

import pytest

from praxis_env.mission_plan import MissionPlan
from praxis_env.models import PraxisAction
from server.praxis_environment import (
    CLARIFICATION_BUDGET,
    PLANNING_ACTION_TYPES,
    PraxisEnvironment,
)


# ── Pure MissionPlan ─────────────────────────────────────────────────────────


class TestMissionPlan:
    def test_create_initialises_milestones(self):
        plan = MissionPlan()
        assert plan.create(["triage", "diagnose", "remediate"]) is True
        assert plan.milestones == ["triage", "diagnose", "remediate"]
        assert plan.revisions == 0
        assert plan.checkpoints_completed == []

    def test_create_is_idempotent_after_initial_call(self):
        plan = MissionPlan()
        plan.create(["a", "b"])
        # Second create call must not stomp existing milestones.
        assert plan.create(["x", "y"]) is False
        assert plan.milestones == ["a", "b"]

    def test_create_rejects_empty_or_blank(self):
        plan = MissionPlan()
        assert plan.create([]) is False
        assert plan.create(["", "   "]) is False

    def test_revise_replace(self):
        plan = MissionPlan()
        plan.create(["triage", "diagnose"])
        assert plan.revise(replace="triage", with_="isolate") is True
        assert plan.milestones == ["isolate", "diagnose"]
        assert plan.revisions == 1

    def test_revise_add_appends_unique(self):
        plan = MissionPlan()
        plan.create(["a"])
        assert plan.revise(add="b") is True
        assert plan.milestones == ["a", "b"]
        # Duplicate add is a no-op.
        assert plan.revise(add="b") is False
        assert plan.revisions == 1

    def test_revise_remove(self):
        plan = MissionPlan()
        plan.create(["a", "b", "c"])
        assert plan.revise(remove="b") is True
        assert plan.milestones == ["a", "c"]
        assert plan.revisions == 1

    def test_revise_replace_clears_completed(self):
        plan = MissionPlan()
        plan.create(["triage", "diagnose"])
        plan.checkpoint("triage", world_state={})
        assert "triage" in plan.checkpoints_completed
        plan.revise(replace="triage", with_="isolate")
        assert "triage" not in plan.checkpoints_completed

    def test_checkpoint_only_accepts_known_milestones(self):
        plan = MissionPlan()
        plan.create(["triage"])
        assert plan.checkpoint("triage", world_state={}) is True
        # Re-checkpointing must not double-count.
        assert plan.checkpoint("triage", world_state={}) is False
        # Unknown milestone rejected.
        assert plan.checkpoint("unknown", world_state={}) is False

    def test_checkpoint_blocked_by_invalid_world_state(self):
        plan = MissionPlan()
        plan.create(["roll_back"])
        invalid = {"invalid_milestones": {"roll_back"}}
        assert plan.checkpoint("roll_back", world_state=invalid) is False

    def test_pending_objectives_reflects_checkpoints(self):
        plan = MissionPlan()
        plan.create(["a", "b", "c"])
        plan.checkpoint("a", world_state={})
        assert plan.pending_objectives == ["b", "c"]


# ── Environment integration ─────────────────────────────────────────────────


@pytest.fixture
def env() -> PraxisEnvironment:
    e = PraxisEnvironment()
    e.reset(task_name="single-service-alert", session_id="t-mission")
    return e


def _step(env: PraxisEnvironment, command: str) -> dict:
    return env.step(PraxisAction(command=command))


class TestPlanningActions:
    def test_planning_action_types_advertised(self):
        # Sanity: the action type set is what we expect.
        assert PLANNING_ACTION_TYPES == frozenset(
            {
                "create_plan",
                "revise_plan",
                "checkpoint",
                "submit_report",
                "request_clarification",
            }
        )

    def test_create_plan_emits_pre_cutoff_event(self, env: PraxisEnvironment):
        result = _step(env, "create_plan milestones=triage,diagnose,remediate")
        assert result["info"]["event"] == "plan.created_pre_cutoff"
        assert result["reward"] > 0.0
        assert result["observation"]["pending_objectives"] == [
            "triage",
            "diagnose",
            "remediate",
        ]

    def test_create_plan_idempotent(self, env: PraxisEnvironment):
        _step(env, "create_plan milestones=triage,diagnose")
        result = _step(env, "create_plan milestones=other,thing")
        assert result["info"]["event"] == "plan.created_invalid"

    def test_revise_plan_after_evidence(self, env: PraxisEnvironment):
        _step(env, "create_plan milestones=triage,diagnose")
        _step(env, "query_logs service=auth timerange=5m")
        result = _step(env, "revise_plan add=isolate")
        assert result["info"]["event"] == "plan.revised_after_evidence"
        assert "isolate" in result["observation"]["pending_objectives"]

    def test_revise_plan_without_evidence(self, env: PraxisEnvironment):
        _step(env, "create_plan milestones=triage,diagnose")
        result = _step(env, "revise_plan add=isolate")
        assert result["info"]["event"] == "plan.revised_no_evidence"

    def test_revise_plan_no_op_without_plan(self, env: PraxisEnvironment):
        result = _step(env, "revise_plan add=isolate")
        assert result["info"]["event"] == "plan.revise_no_op"

    def test_checkpoint_consistent(self, env: PraxisEnvironment):
        _step(env, "create_plan milestones=triage,diagnose")
        result = _step(env, "checkpoint milestone=triage")
        assert result["info"]["event"] == "checkpoint.consistent"

    def test_checkpoint_invalid_for_unknown_milestone(
        self, env: PraxisEnvironment
    ):
        _step(env, "create_plan milestones=triage,diagnose")
        result = _step(env, "checkpoint milestone=unknown")
        assert result["info"]["event"] == "checkpoint.invalid"

    def test_submit_report_requires_diagnosis(self, env: PraxisEnvironment):
        result = _step(env, "submit_report root_causes=guess resolution=hope")
        assert result["info"]["event"] == "submit_report.no_diagnosis"

    def test_submit_report_consistent_after_correct_diagnosis(
        self, env: PraxisEnvironment
    ):
        # Simulate a correct diagnosis without depending on scenario internals.
        env._scenario._root_cause_identified = True  # type: ignore[union-attr]
        result = _step(
            env,
            "submit_report root_causes=auth_typo resolution=rollback_deploy auth",
        )
        assert (
            result["info"]["event"]
            == "submit_report.consistent_with_world_state"
        )
        assert result["reward"] > 0.0

    def test_request_clarification_rate_limited(self, env: PraxisEnvironment):
        first = _step(env, "request_clarification topic=next")
        assert first["info"]["event"] == "clarification.served"
        # After the budget is spent, subsequent calls must report exhaustion.
        for _ in range(CLARIFICATION_BUDGET):
            pass
        second = _step(env, "request_clarification topic=next")
        assert second["info"]["event"] == "clarification.exhausted"

    def test_observation_exposes_mission_fields(self, env: PraxisEnvironment):
        _step(env, "create_plan milestones=a,b,c")
        result = _step(env, "checkpoint milestone=a")
        obs = result["observation"]
        assert "pending_objectives" in obs
        assert obs["pending_objectives"] == ["b", "c"]
        assert "phase" in obs
        assert "time_budget" in obs

    def test_state_exposes_plan_and_checkpoints(self, env: PraxisEnvironment):
        _step(env, "create_plan milestones=a,b,c")
        _step(env, "checkpoint milestone=a")
        state = env.state()
        assert state.plan == ["a", "b", "c"]
        assert state.checkpoints_completed == ["a"]
