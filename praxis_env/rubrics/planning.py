"""
praxis_env.rubrics.planning - Rewards investigation-before-diagnosis ordering.

This rubric is the structural-planning signal: did the agent gather evidence
before committing to a diagnosis, and did it diagnose before remediating? It
also rewards explicit planning actions (`create_plan`, `revise_plan`,
`checkpoint`) once they exist on the action surface.

Scoring (raw, pre-clamp into [-1, 1]):
  +1.0  per phase boundary respected (investigation -> diagnosis -> remediation)
  -1.0  per phase boundary violated (e.g. diagnose before any investigation)
  +0.25 per planning action (capped at +0.5 contribution)
  /N    averaged across signals so a clean run lands at +1.0 and pure violators
        at -1.0.
"""

from __future__ import annotations

from typing import Any

from praxis_env.rubrics.base import Rubric
from praxis_env.trajectory import Trajectory


_PLANNING_ACTIONS = frozenset(
    {"create_plan", "revise_plan", "checkpoint", "submit_report"}
)
_INVESTIGATION_ACTIONS = frozenset(
    {
        "query_logs",
        "check_logs",
        "check_metrics",
        "check_deps",
        "check_config",
        "check_runbook",
    }
)
_DIAGNOSIS_ACTIONS = frozenset({"diagnose"})
_REMEDIATION_ACTIONS = frozenset(
    {
        "rollback_deploy",
        "restart_service",
        "scale_resource",
        "kill_query",
    }
)


class PlanningRubric(Rubric):
    NAME = "planning"

    def _score(self, trajectory: Trajectory) -> tuple[float, dict[str, Any]]:
        events = trajectory.events
        if not events:
            return 0.0, {"reason": "empty_trajectory"}

        first_investigation = next(
            (
                i
                for i, e in enumerate(events)
                if e.action_type in _INVESTIGATION_ACTIONS
            ),
            None,
        )
        first_diagnosis = next(
            (i for i, e in enumerate(events) if e.action_type in _DIAGNOSIS_ACTIONS),
            None,
        )
        first_remediation = next(
            (i for i, e in enumerate(events) if e.action_type in _REMEDIATION_ACTIONS),
            None,
        )

        signals: list[float] = []

        if first_diagnosis is not None:
            if (
                first_investigation is not None
                and first_investigation < first_diagnosis
            ):
                signals.append(1.0)
            else:
                signals.append(-1.0)

        if first_remediation is not None:
            if first_diagnosis is not None and first_diagnosis < first_remediation:
                signals.append(1.0)
            else:
                signals.append(-1.0)

        planning_count = sum(1 for e in events if e.action_type in _PLANNING_ACTIONS)
        # Each explicit planning action adds a +0.25 bump, capped at +0.5
        # so planning alone cannot dominate the structural ordering signal.
        planning_bonus = min(0.5, 0.25 * planning_count) if planning_count else 0.0
        if planning_bonus:
            signals.append(planning_bonus)

        if not signals:
            return 0.0, {"reason": "no_planning_signal", "events": len(events)}

        average = sum(signals) / len(signals)
        return average, {
            "first_investigation": first_investigation,
            "first_diagnosis": first_diagnosis,
            "first_remediation": first_remediation,
            "planning_actions": planning_count,
        }
