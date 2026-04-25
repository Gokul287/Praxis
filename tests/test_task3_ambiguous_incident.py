"""
tests/test_task3_ambiguous_incident.py - Task 3 scenario tests.

Coverage mirrors the other scenarios:
  1. Optimal path and total reward
  2. Evidence gates for diagnosis and escalation
  3. Red-herring penalties
  4. Determinism across repeated runs
  5. Reward bounds and crash safety
  6. Scenario registration
"""

import pytest

from server.command_parser import parse_command
from praxis_env.scenarios.ambiguous_incident import AmbiguousIncidentScenario


def make_scenario() -> AmbiguousIncidentScenario:
    scenario = AmbiguousIncidentScenario()
    scenario.reset(episode_id="test-3")
    return scenario


def step_cmd(scenario: AmbiguousIncidentScenario, cmd_str: str):
    return scenario.step(parse_command(cmd_str))


class TestOptimalPath:
    OPTIMAL_COMMANDS = [
        "query_logs service=frontend timerange=10m",
        "query_logs service=api timerange=10m",
        "query_logs service=auth timerange=10m",
        "check_deps service=frontend",
        "check_metrics service=dns-resolver metric=resolution_failures",
        "query_logs service=dns-resolver timerange=30m",
        "check_config service=dns-resolver",
        "diagnose root_cause=dns_misconfiguration",
        "restart_service service=dns-resolver",
    ]
    EXPECTED_REWARDS = [0.045, 0.045, 0.045, 0.025, 0.092, 0.092, 0.042, 0.187, 0.137]

    def test_optimal_path_rewards(self):
        scenario = make_scenario()
        for cmd, expected in zip(self.OPTIMAL_COMMANDS, self.EXPECTED_REWARDS):
            outcome = step_cmd(scenario, cmd)
            assert outcome.reward == pytest.approx(expected, abs=1e-6)

    def test_optimal_path_total_score(self):
        scenario = make_scenario()
        total = sum(step_cmd(scenario, cmd).reward for cmd in self.OPTIMAL_COMMANDS)
        assert total == pytest.approx(0.71, abs=1e-6)

    def test_optimal_path_done_at_end(self):
        scenario = make_scenario()
        for cmd in self.OPTIMAL_COMMANDS:
            outcome = step_cmd(scenario, cmd)
        assert outcome.done is True
        assert outcome.incident_resolved is True


class TestEvidenceRules:
    def test_diagnose_after_one_investigation_is_penalized(self):
        scenario = make_scenario()
        step_cmd(scenario, "query_logs service=frontend timerange=10m")
        outcome = step_cmd(scenario, "diagnose root_cause=dns_misconfiguration")
        assert outcome.reward == pytest.approx(0.01)
        assert outcome.root_cause_identified is False

    def test_two_app_services_plus_infra_is_still_insufficient(self):
        scenario = make_scenario()
        step_cmd(scenario, "query_logs service=frontend timerange=10m")
        step_cmd(scenario, "query_logs service=api timerange=10m")
        step_cmd(
            scenario, "check_metrics service=dns-resolver metric=resolution_failures"
        )
        outcome = step_cmd(scenario, "diagnose root_cause=dns_misconfiguration")
        assert outcome.reward == pytest.approx(0.01)
        assert outcome.root_cause_identified is False

    def test_escalate_without_enough_evidence_is_penalized(self):
        scenario = make_scenario()
        outcome = step_cmd(scenario, "escalate reason=need help")
        assert outcome.reward == pytest.approx(0.01)
        assert outcome.done is True
        assert outcome.incident_resolved is False

    def test_escalate_with_evidence_ends_episode(self):
        scenario = make_scenario()
        step_cmd(scenario, "query_logs service=frontend timerange=10m")
        step_cmd(scenario, "query_logs service=api timerange=10m")
        step_cmd(scenario, "query_logs service=auth timerange=10m")
        step_cmd(
            scenario, "check_metrics service=dns-resolver metric=resolution_failures"
        )
        outcome = step_cmd(
            scenario, "escalate reason=dns failures across frontend api and auth"
        )
        assert outcome.reward == pytest.approx(0.137)
        assert outcome.done is True
        assert outcome.incident_resolved is True


class TestRedHerrings:
    def test_api_deployment_diagnosis_gets_wrong_diagnosis_penalty(self):
        scenario = make_scenario()
        outcome = step_cmd(scenario, "diagnose root_cause=api_deployment")
        assert outcome.reward == pytest.approx(0.01)
        assert "deploy" in outcome.investigation_result.lower()

    def test_auth_memory_diagnosis_gets_wrong_diagnosis_penalty(self):
        scenario = make_scenario()
        outcome = step_cmd(scenario, "diagnose root_cause=auth_memory")
        assert outcome.reward == pytest.approx(0.01)
        assert "memory" in outcome.investigation_result.lower()

    def test_search_bug_diagnosis_gets_wrong_diagnosis_penalty(self):
        scenario = make_scenario()
        outcome = step_cmd(scenario, "diagnose root_cause=search_bug")
        assert outcome.reward == pytest.approx(0.01)
        assert "search" in outcome.investigation_result.lower()

    def test_restarting_wrong_service_does_not_resolve(self):
        scenario = make_scenario()
        outcome = step_cmd(scenario, "restart_service service=api")
        assert outcome.reward == pytest.approx(0.01)
        assert outcome.incident_resolved is False


class TestDeterminism:
    COMMANDS = [
        "query_logs service=frontend timerange=10m",
        "query_logs service=api timerange=10m",
        "query_logs service=auth timerange=10m",
        "check_deps service=frontend",
        "check_metrics service=dns-resolver metric=resolution_failures",
        "query_logs service=dns-resolver timerange=30m",
        "check_config service=dns-resolver",
        "diagnose root_cause=dns_misconfiguration",
        "restart_service service=dns-resolver",
    ]

    def _run_once(self) -> list[float]:
        scenario = make_scenario()
        rewards = []
        for cmd in self.COMMANDS:
            outcome = step_cmd(scenario, cmd)
            rewards.append(outcome.reward)
        return rewards

    def test_three_runs_identical(self):
        run_1 = self._run_once()
        run_2 = self._run_once()
        run_3 = self._run_once()
        assert run_1 == run_2 == run_3

    def test_investigation_result_is_ascii_safe(self):
        scenario = make_scenario()
        outcome = step_cmd(scenario, "query_logs service=frontend timerange=10m")
        assert outcome.investigation_result.isascii()


class TestRewardBounds:
    REPRESENTATIVE_COMMANDS = [
        "query_logs service=frontend timerange=10m",
        "query_logs service=api timerange=10m",
        "query_logs service=auth timerange=10m",
        "query_logs service=search timerange=10m",
        "query_logs service=dns-resolver timerange=30m",
        "check_metrics service=api metric=error_rate",
        "check_metrics service=auth metric=memory",
        "check_metrics service=dns-resolver metric=resolution_failures",
        "check_metrics service=load-balancer metric=latency_p95",
        "check_deps service=frontend",
        "check_config service=dns-resolver",
        "diagnose root_cause=dns_misconfiguration",
        "diagnose root_cause=api_deployment",
        "diagnose root_cause=auth_memory",
        "restart_service service=dns-resolver",
        "restart_service service=api",
        "escalate reason=need help",
        "",
        "unknown command",
    ]

    @pytest.mark.parametrize("cmd", REPRESENTATIVE_COMMANDS)
    def test_reward_in_bounds(self, cmd):
        scenario = make_scenario()
        outcome = step_cmd(scenario, cmd)
        assert 0.01 <= outcome.reward <= 0.99

    @pytest.mark.parametrize("cmd", REPRESENTATIVE_COMMANDS)
    def test_never_raises(self, cmd):
        scenario = make_scenario()
        try:
            step_cmd(scenario, cmd)
        except Exception as exc:  # pragma: no cover - explicit failure message
            pytest.fail(f"step() raised {type(exc).__name__} for cmd={cmd!r}: {exc}")


class TestRegistration:
    def test_task_is_registered(self):
        from praxis_env.scenarios import list_tasks

        assert "ambiguous-incident" in list_tasks()

    def test_get_scenario_returns_correct_type(self):
        from praxis_env.scenarios import get_scenario

        scenario = get_scenario("ambiguous-incident")
        assert isinstance(scenario, AmbiguousIncidentScenario)

    def test_scenario_metadata_is_correct(self):
        assert AmbiguousIncidentScenario.NAME == "ambiguous-incident"
        assert AmbiguousIncidentScenario.SEVERITY == "P2"
