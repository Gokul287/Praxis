# NOTICE — Vendored Mission Artifacts

This directory hosts the production-style logs, runbooks, prior
tickets, and on-call notes consumed by `MissionScenario`
(`cascading-platform-failure`, see Issue #37) via
`praxis_env.artifacts.ArtifactStore` (Issue #38).

## Provenance

All excerpts shipped here are **internally-authored Praxis fixtures**.
They are written to mirror the structure and tone of real production
incident artifacts (Apache common log / JSON structured logs / SRE
runbook prose / Jira-style tickets / on-call note prose) so the
MissionOps trajectory pressure-tests an agent's ability to read varied
real-world formats, but no third-party data is currently vendored.

The `ArtifactStore.attribution()` provenance prefix is `praxis:fixtures`
and every `Artifact.source` string is rooted in this directory, e.g.
`praxis:fixtures/logs/api_500s.jsonl#L7`.

## Why this differs from ADR-17

ADR-17 / `idea/Plan/Architecture/ScenarioCatalog.md` S7 documented a
plan to vendor a small sample of `Rootly-AI-Labs/logs-dataset` from
Hugging Face under Apache-2.0. That dataset was **not publicly
available** at the time Issue #38 shipped (verified 2026-04-25, both
`Rootly-AI-Labs/logs-dataset` and `rootly-ai-labs/logs-dataset` return
HTTP 404 on the Hugging Face API). Loghub (`logpai/loghub`), the next
canonical real-world log corpus, ships under a research-only license
that disallows redistribution in this repository.

To unblock the MissionOps scenarios without committing a license
violation, this PR ships the ArtifactStore plumbing + scenario wiring +
internally-authored fixtures **today**, and leaves the full Rootly
swap-in to a follow-up issue once a properly-licensed real-world source
is identified.

## Compliance checklist

- [x] No PII in any vendored artifact (no real names, addresses,
      account ids, secrets, or hostnames beyond the synthetic
      `*.example.com`).
- [x] No third-party copyrighted data is redistributed here.
- [x] `LICENSE-3rd-party` at the repository root mirrors this NOTICE.
- [x] `praxis_env.artifacts.ArtifactStore.attribution()` returns the
      same provenance string surfaced from `/metadata` so judges can
      audit it without opening the repository.

## Follow-up

Tracked in the Praxis backlog as **"swap mission artifacts to a
licensed real-world dataset"** — to be raised once a public Apache-2.0
production-incident corpus becomes available (track Rootly AI Labs +
Loghub-2.0 + community alternatives).
