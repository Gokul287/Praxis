"""
tests/test_task5_mega_incident.py - Task 5 scenario tests.

Issue #37 replaced the legacy 120-step Mega-incident scenario with the
mission-shaped ``MissionScenario`` (MAX_STEPS=150, submit_report gate).
The historical class name ``MegaIncidentScenario`` now points at
``MissionScenario`` for back-compat; these tests pin the new contract.
"""

import pytest

from server.command_parser import parse_command
from praxis_env.scenarios.mega_incident import MegaIncidentScenario


def make_scenario() -> MegaIncidentScenario:
    scenario = MegaIncidentScenario()
    scenario.reset(episode_id="task-5-test")
    return scenario


def step_cmd(scenario: MegaIncidentScenario, cmd_str: str):
    return scenario.step(parse_command(cmd_str))


class TestTaskMetadata:
    def test_metadata_matches_issue_contract(self):
        assert MegaIncidentScenario.NAME == "cascading-platform-failure"
        assert MegaIncidentScenario.SEVERITY == "P1"
        # Mission shape (Issue #37, ScenarioCatalog.md S3.1).
        assert MegaIncidentScenario.MAX_STEPS == 150
        assert MegaIncidentScenario.MEMORY_CUTOFF_OVERRIDE == 30
        assert len(MegaIncidentScenario.INITIAL_AFFECTED_SERVICES) == 8


class TestResolutionRules:
    OPTIMAL_COMMANDS = [
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

    def test_optimal_path_score_threshold_and_does_not_self_resolve(self):
        # Issue #37 resolution gate: 3 RCs + 3 remediations alone are not
        # enough - submit_report must close the loop. The scenario-level
        # gate fires only via the environment's _handle_submit_report so
        # at the scenario layer ``_incident_resolved`` stays False.
        scenario = make_scenario()
        rewards = [step_cmd(scenario, cmd).reward for cmd in self.OPTIMAL_COMMANDS]
        assert sum(rewards) >= 0.55
        assert scenario._incident_resolved is False

    def test_submit_report_consistent_resolves_incident(self):
        scenario = make_scenario()
        for cmd in self.OPTIMAL_COMMANDS:
            step_cmd(scenario, cmd)
        accepted = scenario.submit_report_consistent(
            root_causes=[
                "db_pool_corrupted",
                "cdn_tls_expired",
                "worker_memory_leak",
            ],
            resolution="rolled back, scaled, restarted",
        )
        assert accepted is True
        assert scenario._incident_resolved is True

    def test_submit_report_rejected_without_full_remediation(self):
        scenario = make_scenario()
        # Only 2 of 3 root causes diagnosed and remediated.
        partial = self.OPTIMAL_COMMANDS[:8] + [
            "scale_resource service=database resource=connection_pool",
            "rollback_deploy service=cdn",
        ]
        for cmd in partial:
            step_cmd(scenario, cmd)
        accepted = scenario.submit_report_consistent(
            root_causes=["db_pool_corrupted", "cdn_tls_expired"],
            resolution="partial",
        )
        assert accepted is False
        assert scenario._incident_resolved is False

    def test_wrong_diagnosis_path_scores_low(self):
        scenario = make_scenario()
        wrong_commands = [
            "query_logs service=api timerange=10m",
            "diagnose root_cause=api_deploy",
            "restart_service service=auth",
            "escalate reason=unclear",
        ]
        rewards = [step_cmd(scenario, cmd).reward for cmd in wrong_commands]
        assert sum(rewards) <= 0.10

    def test_escalation_requires_diagnosis_and_six_investigations(self):
        scenario = make_scenario()
        for cmd in [
            "query_logs service=database timerange=10m",
            "check_metrics service=database metric=connections",
            "query_logs service=cdn timerange=10m",
            "check_metrics service=cdn metric=tls_handshake_failures",
            "query_logs service=worker timerange=10m",
            "check_metrics service=worker metric=memory",
        ]:
            step_cmd(scenario, cmd)

        rejected = step_cmd(scenario, "escalate reason=need help")
        assert rejected.incident_resolved is False

        step_cmd(scenario, "diagnose root_cause=db_pool_corrupted")
        accepted = step_cmd(scenario, "escalate reason=evidence-backed handoff")
        assert accepted.incident_resolved is True
        assert accepted.done is True


class TestDeterminism:
    COMMANDS = [
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

    def _run_once(self) -> list[float]:
        scenario = make_scenario()
        rewards: list[float] = []
        for cmd in self.COMMANDS:
            rewards.append(step_cmd(scenario, cmd).reward)
        return rewards

    def test_three_runs_produce_identical_reward_vectors(self):
        run_1 = self._run_once()
        run_2 = self._run_once()
        run_3 = self._run_once()
        assert run_1 == run_2 == run_3


def test_remediation_before_diagnosis_scores_zero():
    scenario = make_scenario()
    outcome = step_cmd(
        scenario,
        "scale_resource service=database resource=connection_pool",
    )
    assert outcome.reward == pytest.approx(0.01, abs=1e-6)
    assert scenario._incident_resolved is False
