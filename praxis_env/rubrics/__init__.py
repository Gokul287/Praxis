"""
praxis_env.rubrics - Composable rubric bundle.

Each rubric is a self-contained `Rubric` subclass that scores a `Trajectory`
into `[-1.0, 1.0]`. The bundle below sums to weight 1.0; `RewardEngine`
composes them weighted into `RewardBreakdown.total`. See
`idea/Plan/Architecture/RewardPolicy.md` Section 8 for the contract.
"""

from __future__ import annotations

from praxis_env.rubrics.base import Rubric, RubricResult
from praxis_env.rubrics.memory import MemoryRubric
from praxis_env.rubrics.planning import PlanningRubric
from praxis_env.rubrics.recovery import RecoveryRubric
from praxis_env.rubrics.terminal import TerminalRubric


def default_rubric_bundle() -> tuple[Rubric, ...]:
    """Spec-defined default bundle. Weights MUST sum to 1.0."""
    return (
        PlanningRubric(weight=0.20),
        MemoryRubric(weight=0.20),
        RecoveryRubric(weight=0.20),
        TerminalRubric(weight=0.40),
    )


__all__ = [
    "MemoryRubric",
    "PlanningRubric",
    "RecoveryRubric",
    "Rubric",
    "RubricResult",
    "TerminalRubric",
    "default_rubric_bundle",
]
