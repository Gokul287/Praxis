<!--
  Praxis PR template. Mirrors the issue body shape so plan == reality.
  See idea/Plan/Project/DecisionLog.md ADR-11 for the review policy.
-->

**Closes**: #<issue-number>

## Context

<1-3 sentences. Cite repo files + source IDs from `idea/Plan/Project/EvidenceIndex.md`.>

## What changed

- <bullet 1>
- <bullet 2>

## Acceptance criteria

- [ ] **APIContract**: field parity with `idea/Plan/Architecture/APIContract.md`
- [ ] **Determinism**: <test path>
- [ ] **Reward bound**: scores in `(0.0, 1.0)` per `server/reward.py` `clamp_reward()`
- [ ] **OpenEnv parity**: <SUPPORTS_CONCURRENT_SESSIONS / Pydantic extra="forbid" / etc.>
- [ ] **Review**: matches `idea/Plan/github_issues.md` §4 review policy (no self-merge; SDE PRs require both leads + auto PR review)

## Plan docs updated (same PR as code)

- [ ] `idea/Plan/Architecture/<X>.md`
- [ ] `idea/Plan/<Y>.md`

## How I tested this

```bash
pytest -q
uv run openenv validate
```
