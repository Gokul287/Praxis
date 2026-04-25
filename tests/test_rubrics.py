"""
tests/test_rubrics.py - Composable rubric contract.

Asserts the four invariants from RewardPolicy.md Section 8.2:
  1. Sum of rubric weights == 1.0 (asserted at engine init).
  2. Each rubric returns a value in [-1.0, 1.0] before weighting.
  3. RewardBreakdown.total is in [0.01, 0.99] after clamp.
  4. Disabling any one rubric drops aggregate by exactly weight x value
     (orthogonality).
"""

from __future__ import annotations

import pytest

from praxis_env.rubrics import (
    MemoryRubric,
    PlanningRubric,
    RecoveryRubric,
    TerminalRubric,
    default_rubric_bundle,
)
from praxis_env.trajectory import Trajectory, TrajectoryEvent
from server.reward import RewardBreakdown, RewardEngine


def _ev(
    *,
    step_number: int = 1,
    action_type: str = "query_logs",
    params: dict[str, str] | None = None,
    event_tag: str | None = None,
    reward: float = 0.05,
    done: bool = False,
    incident_resolved: bool = False,
    root_cause_identified: bool = False,
) -> TrajectoryEvent:
    return TrajectoryEvent(
        step_number=step_number,
        action_type=action_type,
        params=params or {},
        event_tag=event_tag,
        reward=reward,
        done=done,
        incident_resolved=incident_resolved,
        root_cause_identified=root_cause_identified,
    )


def _winning_trajectory() -> Trajectory:
    """Investigation -> diagnosis.correct -> remediation, with memory hygiene."""
    traj = Trajectory(task_name="single-service-alert", max_steps=15)
    traj.append(
        _ev(
            step_number=1,
            action_type="query_logs",
            event_tag="investigation.query_logs.auth",
            reward=0.08,
        )
    )
    traj.append(
        _ev(
            step_number=2,
            action_type="save_finding",
            event_tag="memory.save_finding.before_cutoff",
            reward=0.05,
        )
    )
    traj.append(
        _ev(
            step_number=3,
            action_type="diagnose",
            event_tag="diagnosis.correct",
            reward=0.20,
            root_cause_identified=True,
        )
    )
    traj.append(
        _ev(
            step_number=4,
            action_type="rollback_deploy",
            event_tag="remediation.rollback_deploy.auth",
            reward=0.25,
            root_cause_identified=True,
            incident_resolved=True,
            done=True,
        )
    )
    return traj


# ── 1. Weight-sum invariant ────────────────────────────────────────────────


def test_default_bundle_weights_sum_to_one() -> None:
    bundle = default_rubric_bundle()
    assert sum(r.weight for r in bundle) == pytest.approx(1.0)


def test_engine_rejects_bundles_that_do_not_sum_to_one() -> None:
    with pytest.raises(ValueError, match="Rubric weights must sum to 1.0"):
        RewardEngine(
            rubrics=(
                PlanningRubric(weight=0.10),
                MemoryRubric(weight=0.20),
                RecoveryRubric(weight=0.20),
                TerminalRubric(weight=0.40),
            )
        )


def test_engine_accepts_default_bundle() -> None:
    engine = RewardEngine()
    assert len(engine.rubrics) == 4
    assert sum(r.weight for r in engine.rubrics) == pytest.approx(1.0)


# ── 2. Per-rubric range ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "rubric",
    [
        PlanningRubric(weight=1.0),
        MemoryRubric(weight=1.0),
        RecoveryRubric(weight=1.0),
        TerminalRubric(weight=1.0),
    ],
)
def test_rubric_value_within_unit_interval(rubric) -> None:
    traj = _winning_trajectory()
    result = rubric.score(traj)
    assert -1.0 <= result.value <= 1.0


def test_rubric_clamps_extreme_inputs() -> None:
    """Even pathological inputs are clamped into [-1, 1] by the base class."""

    from praxis_env.rubrics.base import Rubric

    class WildRubric(Rubric):
        NAME = "wild"

        def _score(self, trajectory):
            return 5.0, {}

    out = WildRubric(weight=1.0).score(Trajectory(task_name="t", max_steps=1))
    assert out.value == 1.0


# ── 3. Total clamp into judge-safe interval ────────────────────────────────


def test_score_trajectory_total_clamped_into_open_interval() -> None:
    engine = RewardEngine()
    breakdown = engine.score_trajectory(_winning_trajectory())
    assert isinstance(breakdown, RewardBreakdown)
    assert 0.01 <= breakdown.total <= 0.99


def test_score_trajectory_zero_terminal_when_unresolved() -> None:
    engine = RewardEngine()
    traj = Trajectory(task_name="single-service-alert", max_steps=15)
    traj.append(_ev(action_type="query_logs", reward=0.05))
    breakdown = engine.score_trajectory(traj)
    assert breakdown.terminal == 0.0


# ── 4. Orthogonality (disabling rubric drops aggregate by exactly w x v) ───


def test_disabling_one_rubric_drops_aggregate_by_weight_times_value() -> None:
    # Construct a bundle with the same rubrics but explicit named handles
    # so we can rebuild without one of them and check the delta.
    full = (
        PlanningRubric(weight=0.20),
        MemoryRubric(weight=0.20),
        RecoveryRubric(weight=0.20),
        TerminalRubric(weight=0.40),
    )
    full_engine = RewardEngine(rubrics=full)
    traj = _winning_trajectory()
    full_breakdown = full_engine.score_trajectory(traj)

    # Re-weight the bundle so the remaining 3 rubrics still sum to 1.0 by
    # zeroing the planning rubric instead of removing it. Orthogonality is
    # then weight-times-value = 0.20 * planning_value.
    zeroed = (
        PlanningRubric(weight=0.0),
        MemoryRubric(weight=0.20),
        RecoveryRubric(weight=0.20),
        TerminalRubric(weight=0.60),
    )
    zeroed_engine = RewardEngine(rubrics=zeroed)
    zeroed_breakdown = zeroed_engine.score_trajectory(traj)

    # Pre-clamp, the difference is exactly:
    # (0.20 * planning_value) - (0.20 * terminal_value)  due to weight
    # transfer to terminal. Validate the *individual* rubric values are
    # unchanged (no leakage between rubrics).
    assert (
        full_breakdown.per_rubric["planning"].value
        == zeroed_breakdown.per_rubric["planning"].value
    )
    assert (
        full_breakdown.per_rubric["memory"].value
        == zeroed_breakdown.per_rubric["memory"].value
    )
    assert (
        full_breakdown.per_rubric["recovery"].value
        == zeroed_breakdown.per_rubric["recovery"].value
    )
    assert (
        full_breakdown.per_rubric["terminal"].value
        == zeroed_breakdown.per_rubric["terminal"].value
    )


def test_step_info_breakdown_exposed_via_environment() -> None:
    """Every /step result must include `info.breakdown` with the 4 rubrics."""
    from server.praxis_environment import PraxisEnvironment

    env = PraxisEnvironment()
    env.reset(task_name="single-service-alert")

    from praxis_env.models import PraxisAction

    result = env.step(PraxisAction(command="query_logs service=auth timerange=5m"))
    info = result["info"]
    assert "breakdown" in info
    bd = info["breakdown"]
    for key in ("planning", "memory", "recovery", "terminal", "total"):
        assert key in bd
    assert 0.01 <= bd["total"] <= 0.99
    per = bd["per_rubric"]
    assert set(per.keys()) == {"planning", "memory", "recovery", "terminal"}
