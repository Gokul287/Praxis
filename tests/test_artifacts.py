"""
tests for praxis_env.artifacts.ArtifactStore (Issue #38).

Covers the acceptance criteria from the issue:
  * Total vendored size <= 200 KB.
  * `(seed, kind, service, n)` is deterministic.
  * Provenance strings include the canonical prefix.
  * `services()` enumerates the exact set of services we ship for.
  * MissionScenario surfaces excerpts on `query_logs`/`check_runbook`
    and the Intake observation.
  * `/metadata` exposes the data-source attribution.

These tests run against the on-disk fixtures shipped in
`data/artifacts/`. They will fail if the layout drifts in a way that
breaks the contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from praxis_env.artifacts import (
    Artifact,
    ArtifactStore,
    default_artifact_root,
    load_default_store,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS_ROOT = REPO_ROOT / "data" / "artifacts"
TOTAL_SIZE_LIMIT_BYTES = 200 * 1024


# ── Constants pulled from the spec & current vendored layout ────────────


EXPECTED_LOG_SERVICES: set[str] = {
    "api",
    "auth",
    "database",
    "cache",
    "worker",
    "queue",
    "cdn",
    "dns",
}
EXPECTED_RUNBOOK_SERVICES: set[str] = {"api", "auth", "database", "cdn", "worker"}
EXPECTED_TICKET_SERVICES: set[str] = {"database", "cdn", "worker"}
EXPECTED_NOTE_SERVICES: set[str] = {"database", "cdn", "worker"}


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def store() -> ArtifactStore:
    return ArtifactStore(ARTIFACTS_ROOT, seed=42)


# ── Layout / size invariants ────────────────────────────────────────────


class TestLayout:
    def test_artifacts_root_exists(self) -> None:
        assert ARTIFACTS_ROOT.is_dir(), (
            "data/artifacts/ must be checked into the repo per Issue #38"
        )

    def test_required_subdirs_present(self) -> None:
        for sub in ("logs", "runbooks", "tickets", "notes"):
            assert (ARTIFACTS_ROOT / sub).is_dir(), f"data/artifacts/{sub}/ must exist"

    def test_notice_and_readme_present(self) -> None:
        assert (ARTIFACTS_ROOT / "NOTICE.md").is_file()
        assert (ARTIFACTS_ROOT / "README.md").is_file()

    def test_license_3rd_party_present(self) -> None:
        assert (REPO_ROOT / "LICENSE-3rd-party").is_file(), (
            "LICENSE-3rd-party must ship at the repository root"
        )

    def test_total_size_under_200kb(self) -> None:
        total = 0
        for path in ARTIFACTS_ROOT.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
        assert total <= TOTAL_SIZE_LIMIT_BYTES, (
            f"vendored artifacts total {total} bytes "
            f"> limit {TOTAL_SIZE_LIMIT_BYTES} bytes"
        )


# ── ArtifactStore behaviour ─────────────────────────────────────────────


class TestArtifactStore:
    def test_default_root_resolves(self) -> None:
        assert default_artifact_root() == ARTIFACTS_ROOT

    def test_load_default_store_returns_store(self) -> None:
        store = load_default_store(seed=0)
        assert store is not None
        assert isinstance(store, ArtifactStore)

    def test_services_includes_all_expected(self, store: ArtifactStore) -> None:
        services = set(store.services())
        for svc in EXPECTED_LOG_SERVICES:
            assert svc in services

    def test_log_kind_returns_artifact_for_each_service(
        self, store: ArtifactStore
    ) -> None:
        for svc in EXPECTED_LOG_SERVICES:
            artifacts = store.draw("log", svc, n=1)
            assert artifacts, f"expected log artifact for service '{svc}'"
            assert isinstance(artifacts[0], Artifact)
            assert artifacts[0].kind == "log"
            assert artifacts[0].service == svc
            assert artifacts[0].body, "artifact body must be non-empty"

    def test_runbook_kind_returns_artifact_for_expected_services(
        self, store: ArtifactStore
    ) -> None:
        for svc in EXPECTED_RUNBOOK_SERVICES:
            artifacts = store.draw("runbook", svc, n=1)
            assert artifacts, f"expected runbook for service '{svc}'"
            assert artifacts[0].kind == "runbook"

    def test_ticket_kind_returns_artifact_for_expected_services(
        self, store: ArtifactStore
    ) -> None:
        for svc in EXPECTED_TICKET_SERVICES:
            artifacts = store.draw("ticket", svc, n=1)
            assert artifacts, f"expected ticket for service '{svc}'"
            assert artifacts[0].kind == "ticket"

    def test_note_kind_returns_artifact_for_expected_services(
        self, store: ArtifactStore
    ) -> None:
        for svc in EXPECTED_NOTE_SERVICES:
            artifacts = store.draw("note", svc, n=1)
            assert artifacts, f"expected note for service '{svc}'"
            assert artifacts[0].kind == "note"

    def test_unknown_service_returns_empty_list(self, store: ArtifactStore) -> None:
        assert store.draw("log", "made-up-service", n=2) == []

    def test_unknown_kind_raises(self, store: ArtifactStore) -> None:
        with pytest.raises(ValueError):
            store.draw("invalid_kind", "api", n=1)

    def test_negative_n_raises(self, store: ArtifactStore) -> None:
        with pytest.raises(ValueError):
            store.draw("log", "api", n=-1)

    def test_zero_n_returns_empty(self, store: ArtifactStore) -> None:
        assert store.draw("log", "api", n=0) == []


# ── Determinism ─────────────────────────────────────────────────────────


class TestDeterminism:
    def test_same_seed_same_result(self) -> None:
        s1 = ArtifactStore(ARTIFACTS_ROOT, seed=7)
        s2 = ArtifactStore(ARTIFACTS_ROOT, seed=7)
        for kind in ("log", "runbook", "ticket", "note"):
            for svc in EXPECTED_LOG_SERVICES:
                if kind != "log" and svc not in EXPECTED_RUNBOOK_SERVICES:
                    continue
                a = s1.draw(kind, svc, n=2)
                b = s2.draw(kind, svc, n=2)
                assert [x.body for x in a] == [x.body for x in b]

    def test_different_seeds_can_diverge(self) -> None:
        s1 = ArtifactStore(ARTIFACTS_ROOT, seed=1)
        s2 = ArtifactStore(ARTIFACTS_ROOT, seed=999)
        diverged = False
        for svc in ("api", "database", "cdn", "worker"):
            a = [x.body for x in s1.draw("log", svc, n=2)]
            b = [x.body for x in s2.draw("log", svc, n=2)]
            if a != b:
                diverged = True
                break
        assert diverged, "expected at least one (kind, service) to diverge across seeds"

    def test_repeated_calls_same_seed_same_call_match(self) -> None:
        s = ArtifactStore(ARTIFACTS_ROOT, seed=11)
        first = s.draw("log", "database", n=2)
        second = s.draw("log", "database", n=2)
        assert [x.body for x in first] == [x.body for x in second]
        assert [x.source for x in first] == [x.source for x in second]


# ── Provenance ──────────────────────────────────────────────────────────


class TestProvenance:
    def test_log_artifacts_carry_jsonl_line_provenance(
        self, store: ArtifactStore
    ) -> None:
        log = store.draw("log", "api", n=1)[0]
        assert log.source.startswith(ArtifactStore.PROVENANCE_PREFIX)
        assert "logs/" in log.source
        assert "#L" in log.source

    def test_runbook_artifacts_carry_file_provenance(
        self, store: ArtifactStore
    ) -> None:
        rb = store.draw("runbook", "database", n=1)[0]
        assert rb.source.startswith(ArtifactStore.PROVENANCE_PREFIX)
        assert "runbooks/" in rb.source
        assert "#L" not in rb.source  # whole-file artifacts have no line range

    def test_attribution_string_is_self_describing(self, store: ArtifactStore) -> None:
        attribution = store.attribution()
        assert ArtifactStore.PROVENANCE_PREFIX in attribution
        assert "services=" in attribution
        assert "total_artifacts=" in attribution


# ── MissionScenario integration ─────────────────────────────────────────


class TestMissionScenarioIntegration:
    def _new_env(self) -> "object":
        from server.praxis_environment import PraxisEnvironment

        env = PraxisEnvironment()
        env.reset(task_name="cascading-platform-failure", seed=42)
        return env

    def test_query_logs_includes_vendored_excerpt(self) -> None:
        from praxis_env.models import PraxisAction

        env = self._new_env()
        out = env.step(PraxisAction(command="query_logs service=database timerange=5m"))
        text = out["observation"]["investigation_result"]
        assert "[VENDORED LOG EXCERPT: database]" in text
        assert "Source: praxis:fixtures/logs/database" in text

    def test_check_runbook_includes_vendored_runbook(self) -> None:
        from praxis_env.models import PraxisAction

        env = self._new_env()
        out = env.step(PraxisAction(command="check_runbook service=cdn"))
        text = out["observation"]["investigation_result"]
        assert "[VENDORED RUNBOOK EXCERPT: cdn]" in text
        assert "Source: praxis:fixtures/runbooks/cdn" in text

    def test_check_runbook_kind_ticket_returns_ticket(self) -> None:
        from praxis_env.models import PraxisAction

        env = self._new_env()
        out = env.step(PraxisAction(command="check_runbook service=worker kind=ticket"))
        text = out["observation"]["investigation_result"]
        assert "[PRIOR TICKET EXCERPT: worker]" in text
        assert "Source: praxis:fixtures/tickets/worker" in text

    def test_intake_observation_includes_oncall_note(self) -> None:
        from server.praxis_environment import PraxisEnvironment

        env = PraxisEnvironment()
        # MissionScenario picks the on-call note deterministically per seed.
        # seed=0 -> database, seed=1 -> cdn, seed=2 -> worker (mod 3).
        obs = env.reset(task_name="cascading-platform-failure", seed=2)
        intake_text = obs.alert_summary or ""
        # The base intake banner is the alert_summary; the on-call note is
        # appended via get_initial_observation_text(). Investigation result
        # is empty on reset; the note shows up in alert_summary follow-up.
        # The implementation appends to base().get_initial_observation_text(),
        # which is the empty string for the legacy scenario; so the note
        # surfaces in obs.investigation_result after reset.
        full_obs = obs.investigation_result or ""
        assert (
            "[INTAKE: most-recent on-call note for the impacted service]" in full_obs
            or "[INTAKE:" in intake_text
        )

    def test_artifact_attribution_in_state(self) -> None:
        env = self._new_env()
        state = env.state()
        assert state.artifact_attribution, (
            "MissionScenario.state must surface artifact attribution"
        )
        assert any(
            ArtifactStore.PROVENANCE_PREFIX in line
            for line in state.artifact_attribution
        )


# ── /metadata endpoint integration ──────────────────────────────────────


class TestMetadataEndpoint:
    def test_metadata_lists_data_sources(self) -> None:
        from server.app import app

        with TestClient(app) as client:
            r = client.get("/metadata")
            assert r.status_code == 200
            payload = r.json()
            sources = payload.get("data_sources", [])
            assert sources, "/metadata must list at least one data_source"
            mission_src = next(
                (s for s in sources if s["name"] == "praxis-mission-fixtures"),
                None,
            )
            assert mission_src is not None
            assert mission_src["provenance_prefix"] == "praxis:fixtures"
            assert mission_src["artifact_count"] >= 1
            assert "attribution" in mission_src

    def test_metadata_tasks_match_registered_catalog(self) -> None:
        from server.app import app
        from server.praxis_environment import PraxisEnvironment

        with TestClient(app) as client:
            r = client.get("/metadata")
            assert r.status_code == 200
            tasks = {task["name"]: task for task in r.json()["tasks"]}

        assert set(tasks) == set(PraxisEnvironment().list_tasks())
        assert tasks["cascading-platform-failure"]["max_steps"] == 150
        assert tasks["cascading-platform-failure"]["phases"] == [
            "Intake",
            "Exploration",
            "Planning",
            "Execution",
            "Disturbance",
            "Recovery",
            "Completion",
            "Reflection",
        ]

    def test_metadata_lists_rubrics(self) -> None:
        from server.app import app

        with TestClient(app) as client:
            r = client.get("/metadata")
            assert r.status_code == 200
            rubrics = r.json()["rubrics"]

        assert {item["name"] for item in rubrics} == {
            "PlanningRubric",
            "MemoryRubric",
            "RecoveryRubric",
            "TerminalRubric",
        }
        assert sum(item["weight"] for item in rubrics) == 1.0
