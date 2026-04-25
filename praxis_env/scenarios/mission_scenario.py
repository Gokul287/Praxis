"""
praxis_env.scenarios.mission_scenario - Task 5 mission incident (ADR-16).

Replaces the legacy `MegaIncidentScenario` with the full MissionOps shape:

  * 8-phase machine (Intake -> Exploration -> Planning -> Execution ->
    Disturbance -> Recovery -> Completion -> Reflection)
  * `MAX_STEPS = 150`, `MEMORY_CUTOFF_OVERRIDE = 30`
  * Hidden dependency: `restart_service database` while ``cdn_tls_expired``
    is unfixed surfaces a TLS handshake error and tags the trajectory.
  * Deterministic disturbance injection in steps 96-105 (seeded) that
    invalidates a milestone; revising the plan within 3 steps earns the
    `recovery.replan_after_disturbance` bonus.
  * Resolution gate: incident is only resolved when (3 RCs diagnosed) +
    (3 remediations applied) + ``submit_report`` is consistent with the
    world state. The ``submit_report_consistent`` hook is what
    ``server.praxis_environment._handle_submit_report`` calls into.

Back-compat: the historical class name ``MegaIncidentScenario`` is
re-exported from `praxis_env.scenarios.mega_incident` so existing imports
keep working.
"""

from __future__ import annotations

from praxis_env.artifacts import ArtifactStore, load_default_store
from praxis_env.models import StepOutcome
from praxis_env.scenarios.base import ParsedCommand, get_service_param
from praxis_env.scenarios.mega_incident_legacy import MegaIncidentScenarioLegacy


# ── Phase machine -----------------------------------------------------------
INTAKE_END = 8
EXPLORATION_END = 35
PLANNING_END = 55
EXECUTION_END = 95
REFLECTION_START = 146

# ── Disturbance / hidden-dep windows ---------------------------------------
DISTURBANCE_BASE_STEP = 96
DISTURBANCE_SEED_RANGE = 10  # 96-105 inclusive
DISTURBANCE_PHASE_LENGTH = 10
RECOVERY_WINDOW_STEPS = 3

# ── Mission canonicals -----------------------------------------------------
CANONICAL_ROOT_CAUSES: frozenset[str] = frozenset(
    {"db_pool_corrupted", "cdn_tls_expired", "worker_memory_leak"}
)


_HIDDEN_DEP_BANNER = (
    "\n\n[HIDDEN DEPENDENCY DETECTED]\n"
    "TLS handshake failure on database connection: cdn_tls_expired must be "
    "remediated before restarting the database.\n"
    "Suggested next action: rollback_deploy service=cdn, then retry."
)

_DISTURBANCE_BANNER_TEMPLATE = (
    "\n\n[DISTURBANCE: queue backlog spike at step {step}]\n"
    "Queue depth jumped to 480k jobs and saturated worker capacity.\n"
    "One milestone is now inconsistent with world state - revise the plan."
)


class MissionScenario(MegaIncidentScenarioLegacy):
    """Task 5: full MissionOps incident (replaces ``MegaIncidentScenario``)."""

    NAME = "cascading-platform-failure"
    SEVERITY = "P1"
    MAX_STEPS = 150
    MEMORY_CUTOFF_OVERRIDE = 30

    def __init__(
        self,
        seed: int | None = None,
        *,
        artifact_store: ArtifactStore | None = None,
    ) -> None:
        super().__init__()
        self._seed = int(seed) if seed is not None else 0
        # Disturbance step is deterministic per (seed). We hash the seed so
        # adjacent seeds don't all land on step 96.
        self._disturbance_step = DISTURBANCE_BASE_STEP + (
            self._seed % DISTURBANCE_SEED_RANGE
        )
        self._mission_id = f"mission-{self._seed:08x}"
        # ArtifactStore is optional - missing fixtures degrade to the
        # legacy in-memory tables so the env still runs in stripped-down
        # deployments. When present, it's used to surface real production
        # excerpts on query_logs / check_runbook / Intake.
        if artifact_store is not None:
            self._artifact_store: ArtifactStore | None = artifact_store
        else:
            self._artifact_store = load_default_store(seed=self._seed)

    # ── Reset ─────────────────────────────────────────────────────────────

    def _reset_scenario_state(self) -> None:
        super()._reset_scenario_state()
        self._plan_created_step: int | None = None
        self._first_checkpoint_step: int | None = None
        self._disturbance_injected: bool = False
        self._disturbance_step_emitted: int | None = None
        self._disturbance_recovered: bool = False
        self._submit_report_accepted: bool = False
        self._hidden_dep_violations: list[int] = []
        self._last_hidden_dep_step: int | None = None
        # Track whether the agent's first remediation candidate for the
        # database (`restart_service database`) was preceded by a cdn
        # rollback. Used to credit `recovery.rollback_before_restart`.
        self._cdn_rolled_back_before_db_restart_attempt: bool = False
        self._db_restart_attempted: bool = False

    # ── Mission-aware properties read by PraxisEnvironment ────────────────

    @property
    def mission_id(self) -> str:
        return self._mission_id

    @property
    def time_budget(self) -> int:
        return max(0, self.MAX_STEPS - self._step_count)

    @property
    def current_phase(self) -> str:
        """Derive the active phase from step count + agent-event flags.

        Order of checks follows the canonical lifecycle so transient
        states (Disturbance, Recovery) take precedence over coarse step
        ranges. Reflection wins once submit_report is accepted.
        """
        s = self._step_count
        if self._submit_report_accepted or s >= REFLECTION_START:
            return "reflection"
        if self._disturbance_injected and not self._disturbance_recovered:
            assert self._disturbance_step_emitted is not None
            within_window = (
                s < self._disturbance_step_emitted + DISTURBANCE_PHASE_LENGTH
            )
            return "disturbance" if within_window else "recovery"
        if (
            len(self._diagnosed_root_causes) == 3
            and len(self._applied_remediations) == 3
        ):
            return "completion"
        if s < INTAKE_END:
            return "intake"
        if self._plan_created_step is None:
            return "exploration"
        if self._first_checkpoint_step is None and not self._diagnosed_root_causes:
            return "planning"
        return "execution"

    # ── Hooks consumed by server.praxis_environment ───────────────────────

    @property
    def artifact_attribution(self) -> list[str]:
        """Vendored-data attribution surfaced via /state and /metadata.

        Each entry is a self-contained provenance line; consumers can
        render them verbatim. When the ArtifactStore is unavailable
        (e.g. in stripped-down deployments) the list is empty.
        """
        if self._artifact_store is None:
            return []
        return [self._artifact_store.attribution()]

    @property
    def artifact_store(self) -> ArtifactStore | None:
        """Public accessor used by ``server.app`` `/metadata`."""
        return self._artifact_store

    # ── ArtifactStore-backed observation hooks ────────────────────────────

    def _artifact_excerpt(self, kind: str, service: str, *, banner: str) -> str:
        """Return a banner+body excerpt from the ArtifactStore, or "".

        ``banner`` is rendered above the excerpt so the agent can tell at
        a glance which fixture was surfaced. We always emit the
        ``Source: <provenance>`` line so the agent can cite the exact
        excerpt in plans / submit_report bodies.
        """
        if self._artifact_store is None:
            return ""
        artifacts = self._artifact_store.draw(kind, service, n=1)
        if not artifacts:
            return ""
        a = artifacts[0]
        return f"\n\n{banner}\nSource: {a.source}\n---\n{a.body}\n---"

    def get_initial_observation_text(self) -> str:
        # Intake observation includes one on-call note from the most
        # impactful service so the agent has prior context that mirrors
        # what real on-call engineers see when paged.
        base = super().get_initial_observation_text()
        if self._artifact_store is None:
            return base
        # Service is picked deterministically per seed so replays match.
        candidates = ["database", "cdn", "worker"]
        idx = self._seed % len(candidates)
        excerpt = self._artifact_excerpt(
            "note",
            candidates[idx],
            banner="[INTAKE: most-recent on-call note for the impacted service]",
        )
        return base + excerpt

    # ── Action overrides that surface real excerpts ───────────────────────

    def _handle_query_logs(self, command: ParsedCommand) -> StepOutcome:
        outcome = super()._handle_query_logs(command)
        if self._artifact_store is None:
            return outcome
        service = get_service_param(command.params, default="api")
        excerpt = self._artifact_excerpt(
            "log",
            service,
            banner=f"[VENDORED LOG EXCERPT: {service}]",
        )
        if not excerpt:
            return outcome
        return StepOutcome(
            investigation_result=outcome.investigation_result + excerpt,
            reward=outcome.reward,
            done=outcome.done,
            incident_resolved=outcome.incident_resolved,
            root_cause_identified=outcome.root_cause_identified,
            info=outcome.info,
        )

    def _handle_check_runbook(self, command: ParsedCommand) -> StepOutcome:
        outcome = super()._handle_check_runbook(command)
        if self._artifact_store is None:
            return outcome
        service = get_service_param(command.params, default="database")
        kind = (command.params.get("kind") or "runbook").lower().strip()
        if kind not in {"runbook", "ticket"}:
            kind = "runbook"
        banner = (
            f"[VENDORED RUNBOOK EXCERPT: {service}]"
            if kind == "runbook"
            else f"[PRIOR TICKET EXCERPT: {service}]"
        )
        excerpt = self._artifact_excerpt(kind, service, banner=banner)
        if not excerpt:
            return outcome
        return StepOutcome(
            investigation_result=outcome.investigation_result + excerpt,
            reward=outcome.reward,
            done=outcome.done,
            incident_resolved=outcome.incident_resolved,
            root_cause_identified=outcome.root_cause_identified,
            info=outcome.info,
        )

    def mission_world_state(self) -> dict[str, object]:
        """Snapshot of mission state used by MissionPlan.checkpoint().

        ``invalid_milestones`` is the set of plan items that the live
        scenario state contradicts (e.g. an "expand worker pool"
        milestone after the disturbance invalidated it).
        """
        invalid: set[str] = set()
        if self._disturbance_injected and not self._disturbance_recovered:
            # Coarse heuristic: anything mentioning "queue" or "backlog"
            # is invalid until the agent revises the plan.
            invalid.update({"queue", "backlog", "expand_worker_pool"})
        return {"invalid_milestones": invalid}

    def submit_report_consistent(
        self, *, root_causes: list[str], resolution: str
    ) -> bool:
        """Side-effecting consistency gate for ``submit_report``.

        Returns True (and flips ``_incident_resolved=True``) only when:
          1. Three root causes have been correctly diagnosed.
          2. Three corresponding remediations have been applied.
          3. The submitted report covers all canonical root causes.

        Anything less leaves ``_incident_resolved=False`` so the ADR-20
        ``compute_task_score`` returns the clamp floor.
        """
        if (
            len(self._diagnosed_root_causes) != 3
            or len(self._applied_remediations) != 3
        ):
            return False
        normalized: set[str] = set()
        for rc in root_causes:
            key = (rc or "").strip().lower().replace("-", "_").replace(" ", "_")
            mapped = self.ROOT_CAUSE_ALIASES.get(key)
            if mapped is not None:
                normalized.add(mapped)
        if not CANONICAL_ROOT_CAUSES.issubset(normalized):
            return False
        self._incident_resolved = True
        self._submit_report_accepted = True
        self._current_system_status = {
            service: "healthy" for service in self._current_system_status
        }
        return True

    # ── Step pipeline ────────────────────────────────────────────────────

    def step(self, command: ParsedCommand) -> StepOutcome:
        # 1-indexed step number about to execute. `_step_count` is the
        # pre-step count; PraxisEnvironment increments it after we return.
        pre_step = self._step_count + 1

        # Track the planning-machine flags used by `current_phase`.
        if command.action_type == "create_plan" and self._plan_created_step is None:
            self._plan_created_step = pre_step
        elif (
            command.action_type == "checkpoint" and self._first_checkpoint_step is None
        ):
            self._first_checkpoint_step = pre_step

        # Hidden-dep precondition (kept here so super().step still returns
        # the canonical wrong-remediation outcome we override below).
        is_hidden_dep_violation = (
            command.action_type == "restart_service"
            and (command.params.get("service") or "").lower() == "database"
            and "cdn_tls_expired" not in self._applied_remediations
        )

        # Track ordering for the rollback-before-restart bonus. The bonus
        # only fires when the agent rolls back cdn BEFORE attempting any
        # database restart (i.e., respects the hidden dependency).
        rollback_first_credit_eligible = (
            command.action_type == "rollback_deploy"
            and (command.params.get("service") or "").lower() == "cdn"
            and not self._db_restart_attempted
        )

        # Disturbance trigger (deterministic per seed).
        will_inject_disturbance = (
            not self._disturbance_injected and pre_step >= self._disturbance_step
        )

        outcome = super().step(command)

        # Apply post-step hooks in order: hidden_dep -> disturbance ->
        # recovery bonuses. Each hook returns a new StepOutcome.
        if command.action_type == "restart_service" and (
            (command.params.get("service") or "").lower() == "database"
        ):
            self._db_restart_attempted = True

        if is_hidden_dep_violation:
            outcome = self._stamp_hidden_dep(outcome, pre_step)

        if will_inject_disturbance:
            self._disturbance_injected = True
            self._disturbance_step_emitted = pre_step
            outcome = self._stamp_disturbance(outcome, pre_step)

        bonus_event = self._detect_recovery_bonus(
            command,
            pre_step,
            rollback_first_credit_eligible=rollback_first_credit_eligible,
        )
        if bonus_event is not None:
            outcome = self._apply_recovery_bonus(outcome, bonus_event)

        return outcome

    # ── Hidden dep / disturbance stamps ──────────────────────────────────

    def _stamp_hidden_dep(self, outcome: StepOutcome, pre_step: int) -> StepOutcome:
        self._last_hidden_dep_step = pre_step
        self._hidden_dep_violations.append(pre_step)
        info = dict(outcome.info or {})
        info["event"] = "recovery.hidden_dep_violated"
        info["hidden_dep_violation_step"] = pre_step
        return StepOutcome(
            investigation_result=outcome.investigation_result + _HIDDEN_DEP_BANNER,
            reward=outcome.reward,
            done=outcome.done,
            incident_resolved=outcome.incident_resolved,
            root_cause_identified=outcome.root_cause_identified,
            info=info,
        )

    def _stamp_disturbance(self, outcome: StepOutcome, pre_step: int) -> StepOutcome:
        info = dict(outcome.info or {})
        info["event"] = info.get("event") or "recovery.disturbance_injected"
        info["disturbance_step"] = pre_step
        info["disturbance_seed"] = self._seed
        return StepOutcome(
            investigation_result=outcome.investigation_result
            + _DISTURBANCE_BANNER_TEMPLATE.format(step=pre_step),
            reward=outcome.reward,
            done=outcome.done,
            incident_resolved=outcome.incident_resolved,
            root_cause_identified=outcome.root_cause_identified,
            info=info,
        )

    # ── Recovery bonus detection ─────────────────────────────────────────

    def _detect_recovery_bonus(
        self,
        command: ParsedCommand,
        pre_step: int,
        *,
        rollback_first_credit_eligible: bool,
    ) -> str | None:
        # Replan-after-disturbance (window = RECOVERY_WINDOW_STEPS).
        if (
            command.action_type == "revise_plan"
            and self._disturbance_step_emitted is not None
            and not self._disturbance_recovered
            and (pre_step - self._disturbance_step_emitted) <= RECOVERY_WINDOW_STEPS
        ):
            self._disturbance_recovered = True
            return "recovery.replan_after_disturbance"

        # Rollback-before-restart (respects the hidden dependency). This is
        # the *only* hidden-dep recovery bonus - awarding a bonus to a
        # rollback that arrives *after* the violation would invert the
        # acceptance criterion ("bypassed-deps trajectory scores strictly
        # lower"), so we deliberately do not credit hidden_dep_violated ->
        # rollback transitions here.
        if rollback_first_credit_eligible:
            return "recovery.rollback_before_restart"

        # Detected-disturbance-within-3-steps bonus is reserved for the
        # disturbance phase. Any rollback / revise_plan / scale within the
        # recovery window of an injected disturbance qualifies.
        if (
            self._disturbance_step_emitted is not None
            and not self._disturbance_recovered
            and (pre_step - self._disturbance_step_emitted) <= RECOVERY_WINDOW_STEPS
            and command.action_type in {"rollback_deploy", "scale_resource"}
        ):
            return "recovery.detected_disturbance_within_3_steps"

        return None

    def _apply_recovery_bonus(self, outcome: StepOutcome, event: str) -> StepOutcome:
        bonus = self._score_event(event)
        # ``bonus.breakdown.total_unclamped`` already deducts a per-step
        # time-pressure cost; the underlying action's ``outcome.reward``
        # has done the same. Recover the raw event value (without the
        # extra time-pressure charge) by reading the dedicated bucket on
        # the breakdown - investigation_reward for positive recovery
        # tags, destructive_penalty for negative ones.
        b = bonus.breakdown
        bonus_value = (
            b.investigation_reward
            if b.investigation_reward != 0.0
            else b.destructive_penalty
        )
        new_reward = self.clamp_reward(outcome.reward + bonus_value)
        info = dict(outcome.info or {})
        info["event"] = event
        info["recovery_bonus_value"] = bonus_value
        return StepOutcome(
            investigation_result=outcome.investigation_result,
            reward=new_reward,
            done=outcome.done,
            incident_resolved=outcome.incident_resolved,
            root_cause_identified=outcome.root_cause_identified,
            info=info,
        )

    # ── Resolution gate override ─────────────────────────────────────────

    def _all_causes_and_remediations_complete(self) -> bool:
        """Mission resolution requires submit_report to flip the bit.

        The base scenario flipped ``_incident_resolved`` whenever the
        agent finished diagnoses + remediations. The mission scenario
        keeps the diagnosis/remediation count gate but defers the actual
        flip to ``submit_report_consistent`` (called by the
        environment's ``_handle_submit_report``).
        """
        return False
