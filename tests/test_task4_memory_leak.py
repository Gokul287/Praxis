import pytest
from praxis_env.models import ParsedCommand
from praxis_env.scenarios.memory_leak_scenario import MemoryLeakScenario


@pytest.fixture
def scenario():
    s = MemoryLeakScenario()
    s.reset("test_ep_4")
    return s


def test_optimal_path(scenario):
    """Test the documented optimal path for the memory leak scenario runs and resolves correctly."""
    rewards = []

    # 1. query_logs worker
    out = scenario.step(
        ParsedCommand(action_type="query_logs", params={"service": "worker"})
    )
    rewards.append(out.reward)
    assert out.reward == pytest.approx(0.035, abs=1e-6)
    assert not out.done

    # 2. check_metrics worker memory
    out = scenario.step(
        ParsedCommand(
            action_type="check_metrics",
            params={"service": "worker", "metric": "memory"},
        )
    )
    rewards.append(out.reward)
    assert out.reward == pytest.approx(0.085, abs=1e-6)
    assert not out.done

    # 3. check_config worker
    out = scenario.step(
        ParsedCommand(action_type="check_config", params={"service": "worker"})
    )
    rewards.append(out.reward)
    assert out.reward == pytest.approx(0.035, abs=1e-6)
    assert not out.done
    assert "BATCH_SIZE" in out.investigation_result

    # 4. diagnose
    out = scenario.step(
        ParsedCommand(
            action_type="diagnose", params={"root_cause": "large_batch_size_oom"}
        )
    )
    rewards.append(out.reward)
    assert out.reward == pytest.approx(0.135, abs=1e-6)
    assert not out.done
    assert scenario._root_cause_identified

    # 5. rollback_deploy worker
    out = scenario.step(
        ParsedCommand(action_type="rollback_deploy", params={"service": "worker"})
    )
    rewards.append(out.reward)
    assert out.reward == pytest.approx(0.185, abs=1e-6)
    assert out.done
    assert scenario._incident_resolved
    assert sum(rewards) == pytest.approx(0.475, abs=1e-6)
