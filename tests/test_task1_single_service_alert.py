"""
tests/test_task1_single_service_alert.py — Task 1 scenario tests.

Three mandatory patterns for every scenario:
  1. Optimal path — expected score, done=True at end
  2. Determinism — same actions produce same rewards every run (3x)
  3. Reward bounds — every possible command returns reward in [0.01, 0.99]

Plus: full lifecycle via HTTP (reset → step → step → done).
"""

import pytest
from server.command_parser import parse_command
from praxis_env.scenarios.single_service_alert import SingleServiceAlertScenario


def make_scenario() -> SingleServiceAlertScenario:
    s = SingleServiceAlertScenario()
    s.reset(episode_id="test-1")
    return s


def step_cmd(scenario: SingleServiceAlertScenario, cmd_str: str):
    """Helper: parse and step, returns outcome."""
    return scenario.step(parse_command(cmd_str))


# ── 1. Optimal path ───────────────────────────────────────────────────────────


class TestOptimalPath:
    """
    Optimal sequence:
      query_logs auth       -> 0.08
      check_config auth     -> 0.10
      diagnose bad_config   -> 0.20
      rollback_deploy auth  -> 0.25
      Total: 0.63  (done=True after rollback)
    """

    OPTIMAL_COMMANDS = [
        "query_logs service=auth timerange=5m",
        "check_config service=auth",
        "diagnose root_cause=bad_config",
        "rollback_deploy service=auth",
    ]
    EXPECTED_REWARDS = [0.08, 0.10, 0.20, 0.25]

    def test_optimal_path_rewards(self):
        s = make_scenario()
        for cmd, expected in zip(self.OPTIMAL_COMMANDS, self.EXPECTED_REWARDS):
            outcome = step_cmd(s, cmd)
            assert outcome.reward == pytest.approx(expected, abs=1e-6), (
                f"cmd={cmd!r} expected={expected} got={outcome.reward}"
            )

    def test_optimal_path_done_at_end(self):
        s = make_scenario()
        done = False
        for cmd in self.OPTIMAL_COMMANDS:
            outcome = step_cmd(s, cmd)
            done = outcome.done
        assert done is True

    def test_incident_resolved_after_rollback(self):
        s = make_scenario()
        for cmd in self.OPTIMAL_COMMANDS:
            outcome = step_cmd(s, cmd)
        assert outcome.incident_resolved is True

    def test_root_cause_identified_after_diagnose(self):
        s = make_scenario()
        for cmd in self.OPTIMAL_COMMANDS[:3]:  # up to diagnose
            outcome = step_cmd(s, cmd)
        assert outcome.root_cause_identified is True

    def test_system_status_healed_after_resolution(self):
        s = make_scenario()
        for cmd in self.OPTIMAL_COMMANDS:
            step_cmd(s, cmd)
        assert s._current_system_status["auth"] == "healthy"
        assert s._current_system_status["api"] == "healthy"

    def test_total_optimal_score(self):
        s = make_scenario()
        total = sum(step_cmd(s, cmd).reward for cmd in self.OPTIMAL_COMMANDS)
        assert total == pytest.approx(0.63, abs=1e-6)


# ── 2. Determinism ────────────────────────────────────────────────────────────


class TestDeterminism:
    """Same actions must produce identical rewards across 3 fresh episodes."""

    COMMANDS = [
        "query_logs service=auth timerange=5m",
        "check_metrics service=auth metric=error_rate",
        "check_config service=auth",
        "diagnose root_cause=bad_config",
        "rollback_deploy service=auth",
    ]

    def _run_once(self) -> list[float]:
        s = make_scenario()
        rewards = []
        for cmd in self.COMMANDS:
            outcome = step_cmd(s, cmd)
            rewards.append(outcome.reward)
            if outcome.done:
                break
        return rewards

    def test_three_runs_identical(self):
        r1, r2, r3 = self._run_once(), self._run_once(), self._run_once()
        assert r1 == r2 == r3, f"Non-deterministic: {r1} vs {r2} vs {r3}"

    def test_investigation_results_identical(self):
        def get_result(cmd):
            s = make_scenario()
            return step_cmd(s, cmd).investigation_result

        cmd = "query_logs service=auth timerange=5m"
        assert get_result(cmd) == get_result(cmd) == get_result(cmd)


# ── 3. Reward bounds ──────────────────────────────────────────────────────────


class TestRewardBounds:
    """Every command must return reward in [0.01, 0.99]. Never raises."""

    ALL_COMMANDS = [
        # All valid commands on all services
        "query_logs service=auth timerange=5m",
        "query_logs service=api timerange=15m",
        "query_logs service=database timerange=30m",
        "query_logs service=payment timerange=5m",
        "query_logs service=nonexistent timerange=5m",
        "check_metrics service=auth metric=error_rate",
        "check_metrics service=auth metric=latency_p95",
        "check_metrics service=auth metric=connections",
        "check_metrics service=database metric=connections",
        "check_metrics service=nonexistent metric=cpu",
        "check_deps service=auth",
        "check_deps service=api",
        "check_deps service=database",
        "check_config service=auth",
        "check_config service=api",
        "diagnose root_cause=bad_config",  # correct
        "diagnose root_cause=config_typo",  # correct variant
        "diagnose root_cause=wrong_answer",  # incorrect
        "diagnose root_cause=database_overload",  # incorrect
        "diagnose root_cause=",  # empty
        "restart_service service=auth",
        "restart_service service=api",
        "rollback_deploy service=auth",  # correct
        "rollback_deploy service=api",  # wrong service
        "scale_resource service=auth resource=replicas",
        "kill_query service=database query_id=q123",
        "escalate reason=too complex",
        "escalate reason=",
        "escalate",
        "",  # empty command
        "gibberish xyz abc",  # unknown
        "QUERY_LOGS service=auth timerange=5m",  # uppercase
    ]

    @pytest.mark.parametrize("cmd", ALL_COMMANDS)
    def test_reward_in_bounds(self, cmd):
        s = make_scenario()
        outcome = step_cmd(s, cmd)
        assert 0.01 <= outcome.reward <= 0.99, (
            f"Reward {outcome.reward} out of bounds for: {cmd!r}"
        )

    @pytest.mark.parametrize("cmd", ALL_COMMANDS)
    def test_never_raises(self, cmd):
        """Environment must handle any string without crashing."""
        s = make_scenario()
        try:
            step_cmd(s, cmd)
        except Exception as e:
            pytest.fail(f"step() raised {type(e).__name__} for cmd={cmd!r}: {e}")


# ── 4. Scenario registration ──────────────────────────────────────────────────


class TestRegistration:
    def test_task_is_registered(self):
        from praxis_env.scenarios import list_tasks

        assert "single-service-alert" in list_tasks()

    def test_get_scenario_returns_correct_type(self):
        from praxis_env.scenarios import get_scenario

        s = get_scenario("single-service-alert")
        assert isinstance(s, SingleServiceAlertScenario)

    def test_scenario_name_matches_registry_key(self):
        assert SingleServiceAlertScenario.NAME == "single-service-alert"

    def test_scenario_has_valid_severity(self):
        assert SingleServiceAlertScenario.SEVERITY in ("P0", "P1", "P2", "P3")


# ── 5. Evidence and escalation logic ─────────────────────────────────────────


class TestEscalationLogic:
    def test_escalate_with_enough_evidence(self):
        s = make_scenario()
        step_cmd(s, "query_logs service=auth timerange=5m")
        step_cmd(s, "check_config service=auth")
        step_cmd(s, "check_metrics service=auth metric=error_rate")
        outcome = step_cmd(
            s, "escalate reason=config typo in db hostname at 14:23 deploy"
        )
        assert outcome.reward == pytest.approx(0.15)
        assert outcome.done is True

    def test_escalate_without_enough_evidence(self):
        s = make_scenario()
        outcome = step_cmd(s, "escalate reason=no idea")
        assert outcome.reward == pytest.approx(0.01)
        assert outcome.done is True

    def test_wrong_diagnosis_gives_negative_reward(self):
        s = make_scenario()
        outcome = step_cmd(s, "diagnose root_cause=network_partition")
        assert outcome.reward == pytest.approx(0.01)

    def test_restart_does_not_resolve(self):
        s = make_scenario()
        outcome = step_cmd(s, "restart_service service=auth")
        assert outcome.incident_resolved is False
