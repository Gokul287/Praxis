"""
praxis_env.mission_plan - MissionPlan dataclass for the planning command surface.

`MissionPlan` is the agent-controlled artifact produced by `create_plan`,
`revise_plan`, and `checkpoint` (Issue #36). It is intentionally small and
scenario-agnostic - mission-class scenarios use it directly; legacy scenarios
keep an empty plan that round-trips fine through the API.

See `idea/Plan/Architecture/APIContract.md` Section 2.4 and
`idea/Plan/Architecture/ScenarioCatalog.md` Section 3.6.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MissionPlan:
    """
    Append/revise/checkpoint store of mission milestones.

    Determinism: ``MissionPlan`` is pure state - same operations applied in
    the same order produce the same milestone list / revision count / set
    of completed checkpoints.
    """

    milestones: list[str] = field(default_factory=list)
    revisions: int = 0
    checkpoints_completed: list[str] = field(default_factory=list)

    # ── Mutators ─────────────────────────────────────────────────────────────

    def create(self, milestones: list[str]) -> bool:
        """
        Initialise the plan with `milestones`.

        Returns True when the plan was created (first call), False when the
        plan already exists. Subsequent ``create()`` calls are no-ops; agents
        must use ``revise()`` once a plan is in place.
        """
        cleaned = [m.strip() for m in milestones if m and m.strip()]
        if self.milestones:
            return False
        if not cleaned:
            return False
        self.milestones = cleaned
        return True

    def revise(
        self,
        *,
        replace: str | None = None,
        with_: str | None = None,
        add: str | None = None,
        remove: str | None = None,
    ) -> bool:
        """
        Apply a single revision operation.

        Exactly one of (replace, add, remove) must be specified:
          * ``replace=<old>, with_=<new>`` swaps an existing milestone.
          * ``add=<new>`` appends a new milestone.
          * ``remove=<old>`` deletes an existing milestone.

        Returns True when the underlying milestone list actually changed
        (which advances ``revisions``), False otherwise.
        """
        if replace is not None and with_ is not None:
            return self._replace(replace, with_)
        if add is not None:
            return self._add(add)
        if remove is not None:
            return self._remove(remove)
        return False

    def checkpoint(self, milestone: str, world_state: dict) -> bool:
        """
        Mark `milestone` as completed if it exists in the plan and the
        provided ``world_state`` validates it. ``world_state`` is the live
        scenario state dict; a milestone is "consistent" when no key in
        the world_state contradicts it. Scenarios that do not need world-
        state validation can pass ``{}``.

        Returns True when the milestone was newly completed (consistent
        and not already checkpointed), False otherwise.
        """
        m = (milestone or "").strip()
        if not m:
            return False
        if m not in self.milestones:
            return False
        if m in self.checkpoints_completed:
            return False
        if not self._world_state_supports(m, world_state):
            return False
        self.checkpoints_completed.append(m)
        return True

    # ── Read-only helpers ────────────────────────────────────────────────────

    @property
    def pending_objectives(self) -> list[str]:
        """Milestones not yet checkpointed, in plan order."""
        completed = set(self.checkpoints_completed)
        return [m for m in self.milestones if m not in completed]

    def is_empty(self) -> bool:
        return not self.milestones

    # ── Internal mutators ────────────────────────────────────────────────────

    def _replace(self, old: str, new: str) -> bool:
        old_s = (old or "").strip()
        new_s = (new or "").strip()
        if not old_s or not new_s:
            return False
        try:
            idx = self.milestones.index(old_s)
        except ValueError:
            return False
        if old_s == new_s:
            return False
        self.milestones[idx] = new_s
        if old_s in self.checkpoints_completed:
            self.checkpoints_completed.remove(old_s)
        self.revisions += 1
        return True

    def _add(self, new: str) -> bool:
        new_s = (new or "").strip()
        if not new_s or new_s in self.milestones:
            return False
        self.milestones.append(new_s)
        self.revisions += 1
        return True

    def _remove(self, old: str) -> bool:
        old_s = (old or "").strip()
        if not old_s or old_s not in self.milestones:
            return False
        self.milestones.remove(old_s)
        if old_s in self.checkpoints_completed:
            self.checkpoints_completed.remove(old_s)
        self.revisions += 1
        return True

    @staticmethod
    def _world_state_supports(milestone: str, world_state: dict) -> bool:
        """
        Default consistency check: a milestone is consistent unless the
        world_state explicitly invalidates it via an
        ``invalid_milestones: set[str]`` key. Mission-class scenarios may
        pass a richer ``world_state`` to short-circuit checkpoints that
        contradict observed evidence.
        """
        invalid = world_state.get("invalid_milestones", set()) if world_state else set()
        return milestone not in invalid
