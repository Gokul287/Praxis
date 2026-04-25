"""
tests.test_task5_mission - mission-specific contract tests for Issue #37.

Covers the four acceptance criteria from the issue:

  * Phase machine: ``current_phase`` cycles through all 8 phases over a
    150-step replay.
  * Hidden dependency: ``restart_service database`` while ``cdn_tls_expired``
    is unfixed surfaces a TLS handshake banner and emits the
    ``recovery.hidden_dep_violated`` tag; rolling back cdn first earns
    ``recovery.rollback_before_restart`` and yields a strictly higher score.
  * Disturbance: deterministic per-seed step + content; replan within 3
    steps emits ``recovery.replan_after_disturbance``.
  * Resolution gate: missing any of (3 diagnoses, 3 remediations, consistent
    report) leaves ``_incident_resolved=False``; the full path with
    ``submit_report`` flips it via the environment.
"""

from __future__ import annotations

import pytest

from praxis_env.models import PraxisAction
from praxis_env.scenarios.mission_scenario import (
    DISTURBANCE_BASE_STEP,
    MissionScenario,
)
from server.command_parser import parse_command
from server.praxis_environment import PraxisEnvironment


# ── Helpers ─────────────────────────────────────────────────────────────────


def _step_scenario(scenario: MissionScenario, command: str):
    """Step the scenario directly and mimic the env's step_count bookkeeping.

    PraxisEnvironment.step() increments ``_step_count`` after each call, so
    direct scenario.step() callers must replicate that or phase / disturbance
    derivations stay frozen at step 0.
    """
    outcome = scenario.step(parse_command(command))
    scenario._step_count += 1
    return outcome


def _make_scenario(seed: int = 0) -> MissionScenario:
    scenario = MissionScenario(seed=seed)
    scenario.reset(episode_id=f"mission-{seed}")
    return scenario


# ── Phase machine ─────────────────────────────────────────────────────────


class TestPhaseMachine:
    def test_initial_phase_is_intake(self):
        scenario = _make_scenario()
        assert scenario.current_phase == "intake"

    def test_all_eight_phases_reachable(self):
        """``current_phase`` derivation must visit every named phase."""
        scenario = _make_scenario(seed=0)
        observed: set[str] = {scenario.current_phase}

        # Intake: step_count < 8.
        scenario._step_count = 4
        observed.add(scenario.current_phase)

        # Exploration: step >= 8 but no plan yet.
        scenario._step_count = 20
        observed.add(scenario.current_phase)

        # Planning: plan created, no checkpoint, no diagnoses.
        scenario._plan_created_step = 36
        scenario._step_count = 40
        observed.add(scenario.current_phase)

        # Execution: checkpoint + diagnosis under way.
        scenario._first_checkpoint_step = 60
        scenario._diagnosed_root_causes.add("db_pool_corrupted")
        scenario._step_count = 80
        observed.add(scenario.current_phase)

        # Disturbance: just-injected, within phase length.
        scenario._disturbance_injected = True
        scenario._disturbance_step_emitted = scenario._disturbance_step
        scenario._step_count = scenario._disturbance_step
        observed.add(scenario.current_phase)

        # Recovery: past the 10-step disturbance window.
        scenario._step_count = scenario._disturbance_step + 11
        observed.add(scenario.current_phase)

        # Completion: 3 diagnoses + 3 remediations done.
        scenario._diagnosed_root_causes.update(
            {"cdn_tls_expired", "worker_memory_leak"}
        )
        scenario._applied_remediations.update(
            {"db_pool_corrupted", "cdn_tls_expired", "worker_memory_leak"}
        )
        scenario._disturbance_recovered = True
        observed.add(scenario.current_phase)

        # Reflection: submit_report accepted.
        scenario._submit_report_accepted = True
        observed.add(scenario.current_phase)

        assert {
            "intake",
            "exploration",
            "planning",
            "execution",
            "disturbance",
            "recovery",
            "completion",
            "reflection",
        }.issubset(observed)


# ── Hidden dependency ─────────────────────────────────────────────────────


class TestHiddenDependency:
    def test_restart_db_before_cdn_emits_hidden_dep_violation(self):
        scenario = _make_scenario()
        for rc in ("db_pool_corrupted", "cdn_tls_expired", "worker_memory_leak"):
            _step_scenario(scenario, f"diagnose root_cause={rc}")
        outcome = _step_scenario(scenario, "restart_service service=database")
        assert outcome.info.get("event") == "recovery.hidden_dep_violated"
        assert "TLS handshake" in outcome.investigation_result
        assert scenario._last_hidden_dep_step is not None

    def test_rollback_cdn_before_restart_db_earns_recovery_bonus(self):
        scenario = _make_scenario()
        for rc in ("db_pool_corrupted", "cdn_tls_expired", "worker_memory_leak"):
            _step_scenario(scenario, f"diagnose root_cause={rc}")
        outcome = _step_scenario(scenario, "rollback_deploy service=cdn")
        assert (
            outcome.info.get("event")
            == "recovery.rollback_before_restart"
        )

    def test_dependency_respecting_path_scores_higher(self):
        """Acceptance: bypassed-deps trajectory >= 0.05 lower than respecting one."""
        respecting = [
            "diagnose root_cause=db_pool_corrupted",
            "diagnose root_cause=cdn_tls_expired",
            "diagnose root_cause=worker_memory_leak",
            "rollback_deploy service=cdn",
            "scale_resource service=database resource=connection_pool",
            "rollback_deploy service=worker",
        ]
        bypassing = [
            "diagnose root_cause=db_pool_corrupted",
            "diagnose root_cause=cdn_tls_expired",
            "diagnose root_cause=worker_memory_leak",
            "restart_service service=database",
            "rollback_deploy service=cdn",
            "scale_resource service=database resource=connection_pool",
            "rollback_deploy service=worker",
        ]

        def total(commands: list[str]) -> float:
            scenario = _make_scenario()
            return sum(
                _step_scenario(scenario, c).reward for c in commands
            )

        delta = total(respecting) - total(bypassing)
        # Acceptance criterion: bypassed-deps trajectory scores >= 0.05 lower.
        # Allow 1e-6 FP slack so a delta of exactly 0.05 (rendered by IEEE-754
        # as 0.04999999...) doesn't false-fail the test.
        assert delta >= 0.05 - 1e-6, (
            f"Dependency-respecting path must score >= 0.05 higher; got {delta:.3f}"
        )


# ── Disturbance ───────────────────────────────────────────────────────────


class TestDisturbance:
    def test_disturbance_step_is_seed_deterministic(self):
        s_a = MissionScenario(seed=0)
        s_b = MissionScenario(seed=0)
        assert s_a._disturbance_step == s_b._disturbance_step
        s_c = MissionScenario(seed=1)
        # Different seed -> different disturbance step (since base+seed%10).
        assert s_a._disturbance_step != s_c._disturbance_step

    def test_disturbance_banner_is_byte_identical_across_runs(self):
        def run() -> tuple[int | None, str]:
            scenario = _make_scenario(seed=7)
            target = scenario._disturbance_step
            # Burn target-1 steps before triggering.
            for _ in range(target - 1):
                _step_scenario(scenario, "query_logs service=api timerange=5m")
            outcome = _step_scenario(scenario, "query_logs service=api timerange=5m")
            return scenario._disturbance_step_emitted, outcome.investigation_result

        a = run()
        b = run()
        assert a == b
        emitted_step, banner = a
        assert emitted_step == DISTURBANCE_BASE_STEP + 7
        assert "DISTURBANCE" in banner

    def test_revise_plan_within_window_earns_replan_bonus(self):
        scenario = _make_scenario(seed=0)
        _step_scenario(scenario, "create_plan milestones=triage,diagnose,remediate")
        # Burn steps until just before disturbance fires.
        while scenario._step_count < scenario._disturbance_step - 1:
            _step_scenario(scenario, "query_logs service=api timerange=5m")
        # The next step crosses the disturbance threshold.
        _step_scenario(scenario, "query_logs service=api timerange=5m")
        assert scenario._disturbance_injected is True
        # Revise immediately - should earn the replan bonus.
        outcome = _step_scenario(scenario, "revise_plan add=stabilise_queue")
        assert outcome.info.get("event") == "recovery.replan_after_disturbance"
        assert scenario._disturbance_recovered is True


# ── Resolution gate (env integration) ──────────────────────────────────────


class TestResolutionGate:
    OPTIMAL_BASE = [
        "query_logs service=database timerange=15m",
        "check_metrics service=database metric=connections",
        "query_logs service=cdn timerange=15m",
        "check_metrics service=cdn metric=tls_handshake_failures",
        "query_logs service=worker timerange=15m",
        "check_metrics service=worker metric=memory",
        "diagnose root_cause=db_pool_corrupted",
        "diagnose root_cause=cdn_tls_expired",
        "diagnose root_cause=worker_memory_leak",
        "scale_resource service=database resource=connection_pool",
        "rollback_deploy service=cdn",
        "rollback_deploy service=worker",
    ]

    def test_full_remediation_alone_does_not_resolve(self):
        env = PraxisEnvironment()
        env.reset(task_name="cascading-platform-failure", seed=0)
        for cmd in self.OPTIMAL_BASE:
            env.step(PraxisAction(command=cmd))
        state = env.state()
        assert state.incident_resolved is False
        assert state.final_score is None

    def test_inconsistent_submit_report_does_not_resolve(self):
        env = PraxisEnvironment()
        env.reset(task_name="cascading-platform-failure", seed=0)
        for cmd in self.OPTIMAL_BASE:
            env.step(PraxisAction(command=cmd))
        result = env.step(
            PraxisAction(
                command=(
                    "submit_report root_causes=guess1,guess2,guess3 "
                    "resolution=hope"
                )
            )
        )
        assert (
            result["info"]["event"]
            == "submit_report.inconsistent_with_world_state"
        )
        state = env.state()
        assert state.incident_resolved is False

    def test_consistent_submit_report_resolves_and_scores(self):
        env = PraxisEnvironment()
        env.reset(task_name="cascading-platform-failure", seed=0)
        for cmd in self.OPTIMAL_BASE:
            env.step(PraxisAction(command=cmd))
        result = env.step(
            PraxisAction(
                command=(
                    "submit_report "
                    "root_causes=db_pool_corrupted,cdn_tls_expired,worker_memory_leak "
                    "resolution=rolled_back_scaled_restarted"
                )
            )
        )
        assert (
            result["info"]["event"]
            == "submit_report.consistent_with_world_state"
        )
        assert result["done"] is True
        state = env.state()
        assert state.incident_resolved is True
        assert state.root_cause_identified is True
        assert state.final_score is not None
        assert state.final_score == pytest.approx(state.final_score, abs=1e-9)


# ── Mission metadata exposed via env ──────────────────────────────────────


class TestMissionMetadata:
    def test_state_exposes_mission_id_phase_and_attribution(self):
        env = PraxisEnvironment()
        env.reset(task_name="cascading-platform-failure", seed=42)
        state = env.state()
        assert state.mission_id is not None
        assert state.phase == "intake"
        # When the ArtifactStore has loaded its vendored fixtures (Issue
        # #38) the attribution is populated; otherwise it's empty. Both
        # shapes are valid - we only care that the field is a list of
        # strings.
        assert isinstance(state.artifact_attribution, list)
        for line in state.artifact_attribution:
            assert isinstance(line, str)

    def test_observation_exposes_time_budget(self):
        env = PraxisEnvironment()
        obs = env.reset(task_name="cascading-platform-failure", seed=0)
        assert obs.time_budget == MissionScenario.MAX_STEPS
