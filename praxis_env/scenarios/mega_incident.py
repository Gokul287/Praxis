"""
praxis_env.scenarios.mega_incident - back-compat re-export shim.

Issue #37 replaced the legacy Mega-incident scenario with ``MissionScenario``
(see `mission_scenario.py`). The historical name ``MegaIncidentScenario`` is
preserved here as an alias for ``MissionScenario`` so existing imports
continue to work without churn.

If you need the pre-MissionOps 120-step behaviour, import
``MegaIncidentScenarioLegacy`` from ``praxis_env.scenarios.mega_incident_legacy``
directly.
"""

from __future__ import annotations

from praxis_env.scenarios.mega_incident_legacy import MegaIncidentScenarioLegacy
from praxis_env.scenarios.mission_scenario import MissionScenario


# Public alias kept for backward compatibility (tests, external imports).
MegaIncidentScenario = MissionScenario


__all__ = [
    "MegaIncidentScenario",
    "MegaIncidentScenarioLegacy",
    "MissionScenario",
]
