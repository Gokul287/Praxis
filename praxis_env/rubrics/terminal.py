"""
praxis_env.rubrics.terminal - Terminal-state scorer.

Rewards exactly the same outcome gate used by `compute_task_score` (Issue #34):
both `incident_resolved` AND `root_cause_identified` must be True OR the
rubric returns 0.0. When the gate is satisfied the rubric maps the
trajectory's cumulative reward into [0.0, 1.0] using the scenario's
`MAX_REWARD = 0.99` ceiling, which keeps the rubric fully deterministic and
spec-compliant.
"""

from __future__ import annotations

from typing import Any

from praxis_env.rubrics.base import Rubric
from praxis_env.trajectory import Trajectory
from server.reward import MAX_REWARD


class TerminalRubric(Rubric):
    NAME = "terminal"

    def _score(self, trajectory: Trajectory) -> tuple[float, dict[str, Any]]:
        events = trajectory.events
        if not events:
            return 0.0, {"reason": "empty_trajectory"}

        last = events[-1]
        if not (last.incident_resolved and last.root_cause_identified):
            return 0.0, {
                "incident_resolved": last.incident_resolved,
                "root_cause_identified": last.root_cause_identified,
            }

        cumulative = trajectory.cumulative_reward
        normalised = max(0.0, min(1.0, cumulative / MAX_REWARD))
        return normalised, {
            "incident_resolved": True,
            "root_cause_identified": True,
            "cumulative_reward": cumulative,
        }
