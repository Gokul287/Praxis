"""
praxis_env.scenarios — Scenario registry and base classes.

Each scenario is a self-contained, deterministic state machine representing
a specific production incident. Scenarios are loaded by the environment
server during reset() and stepped through during the episode.
"""

from praxis_env.scenarios.base import BaseScenario
from praxis_env.scenarios.single_service_alert import SingleServiceAlertScenario
from praxis_env.scenarios.cascading_failure import CascadingFailureScenario
from praxis_env.scenarios.ambiguous_incident import AmbiguousIncidentScenario
from praxis_env.scenarios.memory_leak_scenario import MemoryLeakScenario

# Populated as phases complete. Add new scenarios here.
SCENARIO_REGISTRY: dict[str, type[BaseScenario]] = {
    "single-service-alert": SingleServiceAlertScenario,
    "cascading-failure": CascadingFailureScenario,
    "ambiguous-incident": AmbiguousIncidentScenario,
    "memory-leak": MemoryLeakScenario,
}


def get_scenario(task_name: str) -> BaseScenario:
    """
    Instantiate a registered scenario by task name.

    Args:
        task_name: One of the registered scenario names

    Returns:
        A fresh, initialised BaseScenario instance

    Raises:
        ValueError: if task_name is not registered
    """
    if task_name not in SCENARIO_REGISTRY:
        available = ", ".join(sorted(SCENARIO_REGISTRY.keys()))
        raise ValueError(f"Unknown task: '{task_name}'. Available tasks: [{available}]")
    return SCENARIO_REGISTRY[task_name]()


def list_tasks() -> list[str]:
    """Return sorted list of all registered task names."""
    return sorted(SCENARIO_REGISTRY.keys())
