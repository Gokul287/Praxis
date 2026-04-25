"""
praxis_env.rubrics.recovery - Mistake recovery scorer.

A wrong diagnosis (`diagnosis.wrong`) or wrong remediation (`remediation.wrong`)
counts as a mistake. The rubric awards +1 per mistake that is followed by a
correct counterpart (`diagnosis.correct` / any `remediation.<svc>.<resource>`
positive event) within `RECOVERY_WINDOW` steps, and -1 for any mistake left
unrecovered. Episodes with no mistakes contribute neutrally (0.0) so this
rubric never penalises clean rollouts.
"""

from __future__ import annotations

from typing import Any

from praxis_env.rubrics.base import Rubric
from praxis_env.trajectory import Trajectory


RECOVERY_WINDOW = 3


def _is_mistake(event_tag: str | None) -> bool:
    if not event_tag:
        return False
    return event_tag in {"diagnosis.wrong", "remediation.wrong"}


def _is_recovery(event_tag: str | None, mistake_kind: str) -> bool:
    if not event_tag:
        return False
    if mistake_kind == "diagnosis.wrong":
        return event_tag == "diagnosis.correct"
    if mistake_kind == "remediation.wrong":
        return event_tag.startswith("remediation.") and event_tag != "remediation.wrong"
    return False


class RecoveryRubric(Rubric):
    NAME = "recovery"

    def _score(self, trajectory: Trajectory) -> tuple[float, dict[str, Any]]:
        mistakes_recovered = 0
        mistakes_total = 0
        events = trajectory.events
        for i, event in enumerate(events):
            if not _is_mistake(event.event_tag):
                continue
            mistakes_total += 1
            window_end = min(len(events), i + 1 + RECOVERY_WINDOW)
            recovered = any(
                _is_recovery(other.event_tag, event.event_tag or "")
                for other in events[i + 1 : window_end]
            )
            if recovered:
                mistakes_recovered += 1

        if mistakes_total == 0:
            return 0.0, {"reason": "no_mistakes"}

        # Map (recovered / total - unrecovered / total) into [-1, 1].
        unrecovered = mistakes_total - mistakes_recovered
        raw = (mistakes_recovered - unrecovered) / mistakes_total
        return raw, {
            "mistakes": mistakes_total,
            "recovered": mistakes_recovered,
            "unrecovered": unrecovered,
            "window": RECOVERY_WINDOW,
        }
