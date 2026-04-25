"""
praxis_env.trajectory - Per-episode action trace consumed by composable rubrics.

`Trajectory` is the contract between `PraxisEnvironment.step()` and the rubric
system in `praxis_env/rubrics/`. The environment owns one `Trajectory` per
episode and appends a `TrajectoryEvent` after each command resolves. Rubrics
consume the immutable trace plus the latest `PraxisState` snapshot.

Design notes:
  * No randomness, no I/O - pure data so rubrics stay deterministic.
  * Free-form `event_tag` mirrors the canonical reward event keys used by
    `RewardEngine.score(...)` (e.g. `diagnosis.correct`,
    `memory.save_finding.before_cutoff`). New rubrics can subset/intersect
    by string prefix without needing a richer schema.
  * `params` is intentionally `dict[str, str]` to mirror the parsed command
    surface; callers should not mutate the passed dict after appending.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class TrajectoryEvent:
    """One step in an episode, post-resolution."""

    step_number: int
    action_type: str
    params: dict[str, str]
    event_tag: str | None
    reward: float
    done: bool
    incident_resolved: bool
    root_cause_identified: bool


@dataclass
class Trajectory:
    """Append-only record of an entire episode."""

    task_name: str
    max_steps: int
    events: list[TrajectoryEvent] = field(default_factory=list)

    def append(self, event: TrajectoryEvent) -> None:
        self.events.append(event)

    def reset(self) -> None:
        self.events.clear()

    def by_action_type(self, action_type: str) -> list[TrajectoryEvent]:
        return [e for e in self.events if e.action_type == action_type]

    def by_event_prefix(self, prefix: str) -> list[TrajectoryEvent]:
        return [
            e for e in self.events if e.event_tag and e.event_tag.startswith(prefix)
        ]

    def matching_event_tags(self, tags: Iterable[str]) -> list[TrajectoryEvent]:
        wanted = set(tags)
        return [e for e in self.events if e.event_tag in wanted]

    @property
    def step_count(self) -> int:
        return len(self.events)

    @property
    def cumulative_reward(self) -> float:
        return sum(e.reward for e in self.events)
