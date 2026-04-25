# `data/artifacts/` — Vendored Mission Artifacts

This directory ships the on-disk fixtures consumed by
`praxis_env.artifacts.ArtifactStore`. The `MissionScenario`
(`cascading-platform-failure`) surfaces them when the agent investigates
the incident, in line with `idea/Plan/Architecture/ScenarioCatalog.md`
S7.

> **Provenance disclaimer**: see [`NOTICE.md`](./NOTICE.md). The shipped
> excerpts are internally-authored Praxis fixtures, not third-party
> data, because the canonical Rootly source from ADR-17 was unavailable
> at vendoring time.

## Layout

```
data/artifacts/
|- README.md                 # this file
|- NOTICE.md                 # provenance + license disclosure
|- logs/<service>_<topic>.jsonl
|- runbooks/<service>_<topic>.md
|- tickets/<service>_<topic>.md
`- notes/<service>_<topic>.md
```

- **logs/** — JSON-Lines production logs (`{"ts": ..., "svc": ...,
  "level": ..., "msg": ...}`). Every non-empty line becomes one
  `Artifact`.
- **runbooks/** — SRE runbooks in markdown. Whole document is one
  artifact.
- **tickets/** — closed prior incident tickets in markdown.
- **notes/** — on-call notes in markdown (used for the Mission Intake
  observation).

The leading token of the filename (`<service>_*`) determines which
service the artifact is indexed under, e.g. `logs/database_pool.jsonl`
indexes under `service="database"`.

## How `ArtifactStore` consumes this

```python
from praxis_env.artifacts import ArtifactStore

store = ArtifactStore(root="data/artifacts", seed=42)
log_excerpts = store.draw("log", "database", n=1)
runbook_pages = store.draw("runbook", "cdn", n=1)
ticket_excerpts = store.draw("ticket", "worker", n=1)
note_excerpts = store.draw("note", "database", n=1)
```

Same `(seed, kind, service, n)` always returns the same artifacts in
the same order.

## Constraints

- **Total size**: bounded to <= 200 KB (verified by
  `tests/test_artifacts.py::test_total_size_under_200kb`).
- **No PII / secrets**: all hostnames are `*.example.com`; no real
  account ids, names, or credentials.
- **Determinism**: `draw()` is reproducible per
  `(seed, kind, service, n)`.

## Adding new fixtures

1. Drop the file into the right `kind/` subdirectory using the
   `<service>_<topic>.<ext>` filename convention.
2. For `.jsonl`: each non-empty line becomes one artifact. Keep lines
   under ~300 chars.
3. For `.md`: keep documents under ~2 KB so the agent's context window
   isn't dominated by a single excerpt.
4. Update `tests/test_artifacts.py` if the new file changes the
   expected `services()` set or the per-`(kind, service)` count.
