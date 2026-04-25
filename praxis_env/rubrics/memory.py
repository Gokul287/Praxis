"""
praxis_env.rubrics.memory - Working-memory hygiene scorer.

Reads the same canonical memory event tags emitted by
`PraxisEnvironment._handle_memory_action` and `RewardEngine`. Positive signals
are saving findings before the cutoff and recalling memory after the cutoff;
negatives are accessing logs after the cutoff (illegal) and recalling against
an empty memory store after the cutoff.
"""

from __future__ import annotations

from typing import Any

from praxis_env.rubrics.base import Rubric
from praxis_env.trajectory import Trajectory


_POSITIVE_MEMORY_TAGS = frozenset(
    {
        "memory.save_finding.before_cutoff",
        "memory.save_finding.after_cutoff",
        "memory.recall_memory.before_cutoff",
        "memory.recall_memory.after_cutoff",
    }
)
_NEGATIVE_MEMORY_TAGS = frozenset(
    {
        "memory.illegal_log_after_cutoff",
        "memory.empty_recall_after_cutoff",
    }
)


class MemoryRubric(Rubric):
    NAME = "memory"

    def _score(self, trajectory: Trajectory) -> tuple[float, dict[str, Any]]:
        positives = len(trajectory.matching_event_tags(_POSITIVE_MEMORY_TAGS))
        negatives = len(trajectory.matching_event_tags(_NEGATIVE_MEMORY_TAGS))
        total = positives + negatives
        if total == 0:
            return 0.0, {"reason": "no_memory_events"}
        raw = (positives - negatives) / total
        return raw, {
            "positives": positives,
            "negatives": negatives,
            "total": total,
        }
