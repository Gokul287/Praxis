"""
server.reward - Centralized reward engine for Praxis scenarios.

Phase 6 introduces a single scoring module so scenario classes only emit
semantic reward events (investigation, diagnosis, remediation, escalation)
instead of carrying duplicated numeric constants.

All returned rewards are clamped to a judge-safe open interval [0.01, 0.99].

Calibration rationale (updated for difficulty-curve fix):
  - Easy (single-service-alert):
      Target optimal: ~0.63. Investigation rewards are generous so even
      a 4-step agent scores well.  This is the "on-ramp" task.
  - Medium (ambiguous-incident):
      Target optimal: ~0.71 deterministic path. The agent must correlate
      signals across app and infra before diagnosis is rewarded.
  - Hard (cascading-failure, memory-leak):
      Target optimal: ~0.46 to ~0.48. Investigation is still rewarded,
      but stronger step pressure and lower remediation margins penalize
      wandering and reward disciplined triage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Mapping, Sequence


if TYPE_CHECKING:  # pragma: no cover - typing only
    from praxis_env.models import PraxisState
    from praxis_env.rubrics.base import Rubric, RubricResult
    from praxis_env.trajectory import Trajectory


MIN_REWARD = 0.01
MAX_REWARD = 0.99


def clamp_reward(value: float) -> float:
    """Clamp score to the judge-safe open interval [0.01, 0.99]."""
    return max(MIN_REWARD, min(MAX_REWARD, float(value)))


def compute_task_score(state: "PraxisState", *, max_steps: int) -> float:
    """
    ADR-20 / Issue #34 - outcome x efficiency final episode score.

    The agent only earns credit when both the incident is resolved AND the
    root cause has been correctly diagnosed. Final score is the cumulative
    in-episode reward attenuated by an efficiency factor that linearly
    decays as the agent burns more of its step budget. Pure-noise rollouts
    that wander to ``max_steps`` therefore score the clamped floor of 0.01,
    while a 4-step targeted solve on a 20-step task earns the full
    cumulative reward * 0.80.

    Args:
        state: The episode state snapshot from PraxisEnvironment.state().
        max_steps: The scenario's MAX_STEPS budget (must be > 0).

    Returns:
        Clamped final score in the judge-safe interval [0.01, 0.99].
    """
    safe_max_steps = max(1, int(max_steps))
    outcome_quality = (
        float(state.cumulative_reward)
        if (state.incident_resolved and state.root_cause_identified)
        else 0.0
    )
    efficiency_factor = max(0.0, 1.0 - (state.step_count / safe_max_steps))
    return clamp_reward(outcome_quality * efficiency_factor)


@dataclass(frozen=True)
class RewardComponents:
    """Per-component score contribution for one agent action.

    Renamed from ``RewardBreakdown`` in Issue #35 so the name is freed for the
    new 5-field rubric breakdown defined below. Field shape and semantics are
    unchanged so callers reading ``RewardResult.breakdown.<field>`` continue
    to work.
    """

    investigation_reward: float = 0.0
    redundancy_penalty: float = 0.0
    diagnosis_reward: float = 0.0
    diagnosis_penalty: float = 0.0
    remediation_reward: float = 0.0
    destructive_penalty: float = 0.0
    efficiency_bonus: float = 0.0
    escalation_reward: float = 0.0
    premature_penalty: float = 0.0
    time_pressure_cost: float = 0.0
    total_unclamped: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "investigation_reward": self.investigation_reward,
            "redundancy_penalty": self.redundancy_penalty,
            "diagnosis_reward": self.diagnosis_reward,
            "diagnosis_penalty": self.diagnosis_penalty,
            "remediation_reward": self.remediation_reward,
            "destructive_penalty": self.destructive_penalty,
            "efficiency_bonus": self.efficiency_bonus,
            "escalation_reward": self.escalation_reward,
            "premature_penalty": self.premature_penalty,
            "time_pressure_cost": self.time_pressure_cost,
            "total_unclamped": self.total_unclamped,
        }


@dataclass(frozen=True)
class RewardBreakdown:
    """4-rubric weighted breakdown surfaced via /step ``info.breakdown``.

    Implements the contract from RewardPolicy.md Section 8.2: weighted sum of
    four composable rubrics (planning + memory + recovery + terminal) clamped
    into the judge-safe open interval ``[0.01, 0.99]``. ``per_rubric`` carries
    each rubric's name -> ``RubricResult`` so judges and the GRPO loss
    visualisation can attribute credit at the rubric level.
    """

    planning: float
    memory: float
    recovery: float
    terminal: float
    total: float
    per_rubric: dict[str, "RubricResult"] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "planning": self.planning,
            "memory": self.memory,
            "recovery": self.recovery,
            "terminal": self.terminal,
            "total": self.total,
            "per_rubric": {
                name: {
                    "value": r.value,
                    "weight": r.weight,
                    "weighted": r.weighted,
                    "notes": r.notes,
                }
                for name, r in self.per_rubric.items()
            },
        }


@dataclass(frozen=True)
class RewardResult:
    """Final clamped reward and detailed component accounting."""

    reward: float
    breakdown: RewardComponents


@dataclass(frozen=True)
class RewardPolicy:
    """Task-level reward policy and tuning knobs."""

    event_values: Mapping[str, float]
    redundancy_penalty: float = -0.02
    premature_penalty: float = -0.05
    destructive_penalty: float = -0.15
    efficiency_bonus_max: float = 0.0
    time_pressure_cost_per_step: float = 0.0


_MEMORY_EVENTS: Mapping[str, float] = {
    "memory.save_finding.before_cutoff": 0.05,
    "memory.save_finding.after_cutoff": 0.02,
    "memory.recall_memory.before_cutoff": 0.01,
    "memory.recall_memory.after_cutoff": 0.08,
    "memory.illegal_log_after_cutoff": -0.05,
    "memory.empty_recall_after_cutoff": -0.02,
}


# Planning-surface events emitted by the create_plan / revise_plan /
# checkpoint / submit_report / request_clarification handlers (Issue #36).
# Values match RewardPolicy.md Section 3.6.
_PLANNING_EVENTS: Mapping[str, float] = {
    "plan.created_pre_cutoff": 0.05,
    "plan.created_post_cutoff": 0.0,
    "plan.created_invalid": 0.0,
    "plan.covers_all_root_causes": 0.10,
    "plan.revised_after_evidence": 0.04,
    "plan.revised_no_evidence": 0.0,
    "plan.revise_no_op": 0.0,
    "checkpoint.consistent": 0.02,
    "checkpoint.invalid": 0.0,
    "submit_report.consistent_with_world_state": 0.20,
    "submit_report.inconsistent_with_world_state": 0.0,
    "submit_report.no_diagnosis": 0.0,
    "clarification.served": 0.0,
    "clarification.exhausted": 0.0,
}

# Recovery-surface events emitted by MissionScenario hidden-dependency and
# disturbance-injection hooks (Issue #37). Values match RewardPolicy.md §3.6.
_RECOVERY_EVENTS: Mapping[str, float] = {
    "recovery.detected_disturbance_within_3_steps": 0.10,
    "recovery.rollback_before_restart": 0.06,
    "recovery.replan_after_disturbance": 0.05,
    "recovery.hidden_dep_violated": 0.0,
    "recovery.disturbance_ignored": 0.0,
}


def _with_memory_events(events: Mapping[str, float]) -> dict[str, float]:
    """Return a new event-value mapping with cross-task event rows."""
    merged = dict(events)
    merged.update(_MEMORY_EVENTS)
    merged.update(_PLANNING_EVENTS)
    merged.update(_RECOVERY_EVENTS)
    return merged


# ── Reward Calibration ──────────────────────────────────────────────────────
#
# Each value is chosen to produce a target difficulty curve:
#   easy  >  medium  >  hard   (when scored by a frontier model)
#
# Key design decisions:
#   - Investigation rewards scale with diagnostic value: checking the
#     service closest to the root cause gives more signal.
#   - Diagnosis is worth 0.15-0.20 depending on difficulty — enough to
#     matter but not so much that a lucky guess dominates.
#   - Remediation is the largest single reward to incentivize taking
#     correct action, not just identifying the problem.
#   - check_runbook rewards institutional-knowledge usage (real on-call
#     engineers consult runbooks before guessing).
#   - Step cost is 0 for easy (no pressure), mild for medium/hard
#     (discourages aimless exploration).
# ────────────────────────────────────────────────────────────────────────────

DEFAULT_REWARD_POLICIES: dict[str, RewardPolicy] = {
    # ── EASY: single-service-alert ──────────────────────────────────────
    # Target optimal path: ~0.63 in 4 steps.
    # Generous investigation rewards so partial investigation is well-rewarded.
    # No step cost — the easy task is forgiving by design.
    "single-service-alert": RewardPolicy(
        event_values=_with_memory_events(
            {
                # Investigation — generous for the easy task
                "investigation.query_logs.auth": 0.08,  # key service
                "investigation.query_logs.default": 0.05,  # exploring is okay
                "investigation.check_metrics.connections": 0.08,
                "investigation.check_metrics.default": 0.05,
                "investigation.check_deps.default": 0.05,
                "investigation.check_config.auth": 0.10,  # high-value: reveals the config typo
                "investigation.check_config.default": 0.03,
                "investigation.check_runbook.default": 0.05,  # consulting runbook is rewarded
                # Diagnosis
                "diagnosis.correct": 0.20,
                "diagnosis.wrong": 0.0,
                # Remediation
                "remediation.rollback_deploy.auth": 0.25,  # correct fix = highest single reward
                "remediation.wrong": 0.0,
                # Escalation
                "escalation.with_evidence": 0.15,
                "escalation.no_evidence": 0.0,
                # Error handling
                "unknown_command": 0.0,
                "invalid_input": 0.0,
            }
        ),
        # Easy task: no step cost, mild penalties
        time_pressure_cost_per_step=0.0,
    ),
    # ── HARD: cascading-failure ─────────────────────────────────────────
    # Target optimal path: ~0.46 in 7 steps.
    # Investigation rewards are lower — must follow the dependency chain.
    # Stronger step cost penalizes wandering through red herrings.
    "cascading-failure": RewardPolicy(
        event_values=_with_memory_events(
            {
                # Investigation — lower rewards, must multi-hop to find root cause
                "investigation.query_logs.api": 0.03,  # symptom service, low value
                "investigation.query_logs.database": 0.05,  # closer to root cause
                "investigation.query_logs.analytics": 0.05,  # reveals the runaway query
                "investigation.query_logs.default": 0.02,  # exploring other services
                "investigation.check_metrics.database.connections": 0.08,  # key metric
                "investigation.check_metrics.default": 0.02,
                "investigation.check_deps.core": 0.03,  # reveals db dependency
                "investigation.check_deps.default": 0.02,
                "investigation.check_config.database": 0.03,
                "investigation.check_config.analytics": 0.03,
                "investigation.check_config.default": 0.02,
                "investigation.check_runbook.default": 0.03,
                # Diagnosis — moderate, must earn it through investigation
                "diagnosis.correct": 0.14,
                "diagnosis.wrong": 0.0,
                # Remediation — both needed for full resolution
                "remediation.kill_query.database": 0.09,  # stop the bleeding
                "remediation.scale_resource.database.connection_pool": 0.08,  # prevent recurrence
                "remediation.wrong": 0.0,
                # Escalation
                "escalation.with_evidence": 0.09,
                "escalation.no_evidence": 0.0,
                # Error handling
                "unknown_command": 0.0,
                "invalid_input": 0.0,
            }
        ),
        # Hard task: stronger step cost discourages aimless exploration
        time_pressure_cost_per_step=0.006,
    ),
    # ── MEDIUM: ambiguous-incident ──────────────────────────────────────
    # Target optimal path: ~0.71 deterministic, requiring cross-service
    # evidence correlation but with less harsh remediation pressure than
    # the hard tasks.
    "ambiguous-incident": RewardPolicy(
        event_values=_with_memory_events(
            {
                # Investigation — must check 3+ app services + infra
                "investigation.query_logs.app": 0.048,
                "investigation.query_logs.dns-resolver": 0.095,
                "investigation.query_logs.default": 0.028,
                "investigation.check_metrics.dns-resolver.resolution_failures": 0.095,
                "investigation.check_metrics.app": 0.028,
                "investigation.check_metrics.load-balancer": 0.018,
                "investigation.check_metrics.default": 0.018,
                "investigation.check_deps.default": 0.028,
                "investigation.check_config.dns-resolver": 0.045,
                "investigation.check_config.app": 0.018,
                "investigation.check_config.default": 0.01,
                "investigation.check_runbook.default": 0.028,
                # Diagnosis
                "diagnosis.correct": 0.19,
                "diagnosis.wrong": 0.0,
                # Remediation
                "remediation.restart_service.dns-resolver": 0.14,
                "remediation.wrong": 0.0,
                # Escalation
                "escalation.with_evidence": 0.14,
                "escalation.no_evidence": 0.0,
                # Error handling
                "unknown_command": 0.0,
                "invalid_input": 0.0,
            }
        ),
        # Medium task: mild step cost
        time_pressure_cost_per_step=0.003,
    ),
    # ── HARD: memory-leak ───────────────────────────────────────────────
    # Requires checking memory metrics and config to find the OOM cause.
    # Target optimal path: ~0.48 in 5 steps.
    "memory-leak": RewardPolicy(
        event_values=_with_memory_events(
            {
                # Investigation
                "investigation.query_logs.worker": 0.04,
                "investigation.query_logs.default": 0.02,
                "investigation.check_metrics.worker.memory": 0.09,
                "investigation.check_metrics.default": 0.02,
                "investigation.check_deps.default": 0.02,
                "investigation.check_config.worker": 0.04,
                "investigation.check_config.default": 0.02,
                "investigation.check_runbook.default": 0.03,
                # Diagnosis
                "diagnosis.correct": 0.14,
                "diagnosis.wrong": 0.0,
                # Remediation
                "remediation.rollback_deploy.worker": 0.19,
                "remediation.scale_resource.worker.memory": 0.19,
                "remediation.wrong": 0.0,
                # Escalation
                "escalation.with_evidence": 0.10,
                "escalation.no_evidence": 0.0,
                # Error handling
                "unknown_command": 0.0,
                "invalid_input": 0.0,
            }
        ),
        time_pressure_cost_per_step=0.005,
    ),
    # ── HARD+: cascading-platform-failure (mega incident) ─────────────────
    # Target optimal path: >=0.55 while requiring multiple correlated
    # investigations, three diagnoses, and three remediations.
    "cascading-platform-failure": RewardPolicy(
        event_values=_with_memory_events(
            {
                # Investigation
                "investigation.query_logs.database": 0.055,
                "investigation.query_logs.cdn": 0.055,
                "investigation.query_logs.worker": 0.055,
                "investigation.query_logs.default": 0.02,
                "investigation.check_metrics.database.connections": 0.07,
                "investigation.check_metrics.cdn.tls_handshake_failures": 0.07,
                "investigation.check_metrics.worker.memory": 0.07,
                "investigation.check_metrics.default": 0.02,
                "investigation.check_deps.default": 0.02,
                "investigation.check_config.database": 0.04,
                "investigation.check_config.cdn": 0.04,
                "investigation.check_config.worker": 0.04,
                "investigation.check_config.default": 0.02,
                "investigation.check_runbook.default": 0.025,
                # Diagnosis
                "diagnosis.correct": 0.08,
                "diagnosis.wrong": 0.0,
                # Remediation
                "remediation.scale_resource.database.connection_pool": 0.10,
                "remediation.rollback_deploy.cdn": 0.10,
                "remediation.rollback_deploy.worker": 0.10,
                "remediation.wrong": 0.0,
                # Escalation
                "escalation.with_evidence": 0.12,
                "escalation.no_evidence": 0.0,
                # Error handling
                "unknown_command": 0.0,
                "invalid_input": 0.0,
            }
        ),
        # MissionOps step cost (Issue #37, RewardPolicy.md §3.6). Lowered
        # from 0.004 -> 0.002 to keep the 150-step horizon survivable.
        time_pressure_cost_per_step=0.002,
    ),
}


class RewardEngine:
    """Deterministic event-based reward calculator shared by all scenarios.

    The engine has two scoring surfaces:
      * ``score(task_name, event=...)``           -> ``RewardResult`` (per step)
      * ``score_trajectory(trajectory)``           -> ``RewardBreakdown`` (rubric)

    The rubric bundle MUST sum to weight 1.0 (asserted at init time, see
    `RewardPolicy.md` Section 8.2). Passing ``rubrics=None`` loads the
    spec-default 4-rubric bundle from ``praxis_env.rubrics``.
    """

    def __init__(
        self,
        policies: Mapping[str, RewardPolicy] | None = None,
        *,
        rubrics: Sequence["Rubric"] | None = None,
    ) -> None:
        self._policies = dict(policies or DEFAULT_REWARD_POLICIES)

        if rubrics is None:
            from praxis_env.rubrics import default_rubric_bundle

            rubrics = default_rubric_bundle()

        if not rubrics:
            raise ValueError("RewardEngine requires at least one rubric")

        weight_sum = sum(r.weight for r in rubrics)
        # 1e-6 accommodates float drift from spec-defined weight literals.
        if abs(weight_sum - 1.0) > 1e-6:
            names = ", ".join(f"{r.NAME}={r.weight:.3f}" for r in rubrics)
            raise ValueError(
                f"Rubric weights must sum to 1.0; got {weight_sum:.6f} "
                f"({names})"
            )
        self._rubrics: tuple["Rubric", ...] = tuple(rubrics)

    def register_policy(self, task_name: str, policy: RewardPolicy) -> None:
        """Register or replace a task-level reward policy at runtime."""
        self._policies[task_name] = policy

    @property
    def rubrics(self) -> tuple["Rubric", ...]:
        return self._rubrics

    def score_trajectory(self, trajectory: "Trajectory") -> RewardBreakdown:
        """Score a `Trajectory` with the configured composable rubrics."""
        per_rubric: dict[str, "RubricResult"] = {}
        weighted_total = 0.0
        for rubric in self._rubrics:
            result = rubric.score(trajectory)
            per_rubric[result.name] = result
            weighted_total += result.weighted

        return RewardBreakdown(
            planning=per_rubric.get("planning").value
            if "planning" in per_rubric
            else 0.0,
            memory=per_rubric.get("memory").value if "memory" in per_rubric else 0.0,
            recovery=per_rubric.get("recovery").value
            if "recovery" in per_rubric
            else 0.0,
            terminal=per_rubric.get("terminal").value
            if "terminal" in per_rubric
            else 0.0,
            total=clamp_reward(weighted_total),
            per_rubric=per_rubric,
        )

    def score(
        self,
        *,
        task_name: str,
        event: str,
        duplicate: bool = False,
        premature: bool = False,
        destructive: bool = False,
        root_cause_identified: bool = True,
        resolved: bool = False,
        step_number: int = 1,
        max_steps: int = 1,
    ) -> RewardResult:
        """
        Score a single scenario event.

        Args:
            task_name: Scenario/task identifier.
            event: Canonical event key, e.g. "diagnosis.correct".
            duplicate: True if this action repeats already-seen evidence.
            premature: True if action happened before evidence threshold.
            destructive: True for materially harmful wrong remediations.
            root_cause_identified: Whether root cause was diagnosed already.
            resolved: True when this action resolves or ends the incident.
            step_number: 1-based action index for optional timing bonuses.
            max_steps: Episode step limit.
        """
        policy = self._policies.get(task_name)
        if policy is None:
            available = ", ".join(sorted(self._policies.keys()))
            raise ValueError(
                f"Unknown reward policy for task '{task_name}'. "
                f"Available policies: [{available}]"
            )

        if event.startswith("remediation.") and not root_cause_identified:
            components = RewardComponents(total_unclamped=0.0)
            return RewardResult(
                reward=clamp_reward(components.total_unclamped),
                breakdown=components,
            )

        event_value = policy.event_values.get(event, 0.0)
        effective_value = 0.0 if duplicate else event_value

        investigation_reward = 0.0
        diagnosis_reward = 0.0
        diagnosis_penalty = 0.0
        remediation_reward = 0.0
        escalation_reward = 0.0

        if event.startswith("investigation."):
            investigation_reward = effective_value
        elif event.startswith("memory."):
            investigation_reward = effective_value
        elif event == "diagnosis.correct":
            diagnosis_reward = effective_value
        elif event.startswith("diagnosis."):
            diagnosis_penalty = effective_value
        elif event.startswith("remediation."):
            remediation_reward = effective_value
        elif event.startswith("escalation."):
            escalation_reward = effective_value
        elif event.startswith(("plan.", "checkpoint.", "clarification.")):
            # Planning surface events (Issue #36) — credit to the
            # investigation bucket so they appear in step.info.breakdown.
            investigation_reward = effective_value
        elif event.startswith("submit_report."):
            # Submitting a consistent report is the planning equivalent of
            # remediation — fold it in there so terminal-rubric callers can
            # still see the credit on the per-step breakdown.
            remediation_reward = effective_value
        elif event.startswith("recovery."):
            # Mission recovery surface (Issue #37). Positive bonuses fall
            # into investigation_reward; negative tags (penalty for
            # bypassing a hidden dependency) into destructive_penalty so
            # they survive the per-step floor.
            if effective_value >= 0:
                investigation_reward = effective_value
            else:
                destructive_penalty = effective_value

        redundancy_penalty = policy.redundancy_penalty if duplicate else 0.0
        premature_penalty = policy.premature_penalty if premature else 0.0
        destructive_penalty = policy.destructive_penalty if destructive else 0.0

        # Step cost: mild per-step penalty that discourages aimless exploration
        time_pressure_cost = (
            -policy.time_pressure_cost_per_step
            if policy.time_pressure_cost_per_step > 0.0
            else 0.0
        )

        efficiency_bonus = 0.0
        if resolved and policy.efficiency_bonus_max > 0.0 and max_steps > 0:
            bounded_step = min(max(step_number, 1), max_steps)
            progress = bounded_step / max_steps
            efficiency_bonus = policy.efficiency_bonus_max * (1.0 - progress)

        total_unclamped = (
            investigation_reward
            + redundancy_penalty
            + diagnosis_reward
            + diagnosis_penalty
            + remediation_reward
            + destructive_penalty
            + efficiency_bonus
            + escalation_reward
            + premature_penalty
            + time_pressure_cost
        )

        components = RewardComponents(
            investigation_reward=investigation_reward,
            redundancy_penalty=redundancy_penalty,
            diagnosis_reward=diagnosis_reward,
            diagnosis_penalty=diagnosis_penalty,
            remediation_reward=remediation_reward,
            destructive_penalty=destructive_penalty,
            efficiency_bonus=efficiency_bonus,
            escalation_reward=escalation_reward,
            premature_penalty=premature_penalty,
            time_pressure_cost=time_pressure_cost,
            total_unclamped=total_unclamped,
        )

        return RewardResult(
            reward=clamp_reward(total_unclamped),
            breakdown=components,
        )
