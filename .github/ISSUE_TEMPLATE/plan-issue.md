---
name: Plan issue (Theme #2)
about: Use this template for any of the 21 issues defined in idea/Plan/github_issues.md
title: "[P?] <title>"
labels: ["plan-v2.1"]
---


## Context

<1-3 sentences grounded in repo files + source IDs (Sx) from `idea/Plan/Project/EvidenceIndex.md`>

## What to do

1. <bullet, code-pattern-tight, references concrete files>
2. <...>

## Done when

- [ ] <verifiable artifact 1>
- [ ] <verifiable artifact 2>

## Depends on

- #<n>

## Unblocks

- #<n>

## Acceptance criteria

- [ ] **APIContract**: field parity with `idea/Plan/Architecture/APIContract.md`
- [ ] **Determinism**: <test path>
- [ ] **Reward bound**: scores in `(0.0, 1.0)` (`server/reward.py` clamp)
- [ ] **OpenEnv parity**: <SUPPORTS_CONCURRENT_SESSIONS / Pydantic extra="forbid" / etc.>
- [ ] **Review**: matches §4 review policy (no self-merge; SDE PRs require both leads + auto PR review)

## Plan docs to update (same PR as code - keep plan == reality)

- [ ] `idea/Plan/Architecture/<X>.md`
- [ ] `idea/Plan/<Y>.md`

## References

- `<repo file path>:<line>`
- `idea/Plan/Project/EvidenceIndex.md` Sx
