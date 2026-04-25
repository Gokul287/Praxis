"""
praxis_env.rubrics.base - Rubric ABC + RubricResult.

A rubric is a deterministic scorer over a Trajectory that returns a value in
``[-1.0, 1.0]`` with a stable name and a free-form notes payload. Rubrics
must NOT mutate the trajectory and MUST be safe to call multiple times mid-
episode (rubrics are scored on every /step so judges can see credit
attribution as the episode progresses).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from praxis_env.trajectory import Trajectory


def _clamp_unit(value: float) -> float:
    """Clamp a raw rubric score into the [-1.0, 1.0] contract range."""
    if value > 1.0:
        return 1.0
    if value < -1.0:
        return -1.0
    return float(value)


@dataclass(frozen=True)
class RubricResult:
    """One rubric's verdict on a Trajectory."""

    name: str
    value: float
    weight: float
    notes: dict[str, Any] = field(default_factory=dict)

    @property
    def weighted(self) -> float:
        return self.value * self.weight


class Rubric(ABC):
    """Abstract base. Subclasses must set NAME and implement _score."""

    NAME: str = "unnamed"

    def __init__(self, weight: float) -> None:
        if not 0.0 <= weight <= 1.0:
            raise ValueError(
                f"{self.NAME}: weight must be in [0.0, 1.0]; got {weight!r}"
            )
        self.weight = float(weight)

    def score(self, trajectory: Trajectory) -> RubricResult:
        raw, notes = self._score(trajectory)
        return RubricResult(
            name=self.NAME,
            value=_clamp_unit(raw),
            weight=self.weight,
            notes=notes,
        )

    @abstractmethod
    def _score(self, trajectory: Trajectory) -> tuple[float, dict[str, Any]]:
        """
        Return (raw_value, notes). raw_value will be clamped to [-1.0, 1.0]
        by the base ``score()`` wrapper before being assembled into a
        ``RubricResult``. Implementations MUST be deterministic given the
        same trajectory.
        """
        raise NotImplementedError
