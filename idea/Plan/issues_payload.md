# Issues payload — Praxis MissionOps (Plan v3.0)

> Ready-to-paste payloads for the 17 implementation issues (`#22 → #38`) and 1 tracker (`#39`). After plan approval, file each issue with `gh issue create` (or use the GitHub web UI). **No GitHub mutations are performed by this plan step** — that happens manually after approval.
>
> Source of truth for issue bodies: [`github_issues.md`](./github_issues.md). The tracker (`#39`) body comes from [`Submission/SubmissionChecklist.md`](./Submission/SubmissionChecklist.md) §8.
>
> Conventions:
> - Title: `<short user-friendly title>` (matches `github_issues.md` heading minus the `Issue #NN — ` prefix).
> - Labels: as listed under each issue's `**Labels**:` line.
> - Owner: per the lane index in `github_issues.md` (Architect / TechLead / SDE).
> - Reviewers are set automatically by `.github/CODEOWNERS` + `.github/workflows/auto-review.yml` (ADR-11). Do not pass `--reviewer` flags.
>
> Filing order (must respect dependencies — see `dependency_graph.md` §3 for the critical path):
>
> ```
> #22 → #23 → #24 → #25 → #26 → #27 → #28 → #29 → #30 → #31 → #32 → #33 → #34 → #35 → #36 → #37 → #38 → #39
> ```

---

## How to file (one block, copy-paste from your shell)

> Use PowerShell on Windows (the `@'…'@` heredoc syntax). On macOS/Linux, swap to bash heredocs (`<<'EOF' … EOF`). Each block files exactly one issue. **Run them sequentially in the order above** so dependency references in later issues resolve.

```powershell
# Pre-flight (run once)
gh auth status        # must be logged in to GunaPalanivel/Praxis
gh repo view --json name,owner | ConvertFrom-Json
```

After all 17 implementation issues are filed and merged, file `#39` last so the dependency list is complete.

---

# Issue #22 — Safety bundle: asyncio.Lock + slowapi + uvicorn CMD + threshold raise

**Labels**: `P0`, `blocker`, `server`, `concurrency`, `safety`  ·  **Owner**: Architect (`@GunaPalanivel`)

```powershell
gh issue create --title "[P0] Safety bundle: asyncio.Lock + slowapi + uvicorn CMD + threshold raise" `
  --label "P0,blocker,server,concurrency,safety" `
  --body @'
## Context

`FlawsToProduction/Critical Mistakes (Real-World Failures).md` Mistakes 4 / 6 / 8 + S39: `threading.Lock` blocks the FastAPI event loop, no rate limiting, Dockerfile re-imports the app on `python -m server.app`, and `SUCCESS_SCORE_THRESHOLD=0.10` is trivially passable. All four are P0 for a public HF Space facing GRPO rollouts and judges.

## What to do

1. `server/session_manager.py`: replace `threading.Lock()` with `asyncio.Lock()`; convert `allocate / get / touch / close` to `async`; add `session_timeout_s = 900` TTL eviction in `_evict_expired_unlocked()`. Spec: `idea/Plan/Architecture/ConcurrencyModel.md` §2 + §4.
2. `server/app.py`: convert `/reset`, `/step`, `/state` handlers to `async def` and `await manager.*`. Add `slowapi` `Limiter(get_remote_address, default_limits=["120/minute"])`; per-route `60/minute` for `/step`, `30/minute` for `/reset`. Add `pyproject.toml` dep `slowapi>=0.1.9`.
3. `Dockerfile`: replace `CMD ["python", "-m", "server.app"]` with `CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]`; remove the duplicate `if __name__ == "__main__": uvicorn.run(...)` block from `server/app.py`.
4. `inference.py`: raise `MAX_TOKENS = 256`, `SUCCESS_SCORE_THRESHOLD = 0.50`; add gate `success = (state.incident_resolved and state.root_cause_identified and final_score >= 0.50)`.

## Done when

- [ ] All `SessionManager` methods are `async`; route handlers `await` them; no `threading.Lock` import remains in `server/`.
- [ ] `slowapi` returns `429 + Retry-After` after burst; honest GRPO rollout (8 sessions × 60 turns / 5 min) passes.
- [ ] `docker build && docker run` boots the app exactly once; `curl /health` returns 200; no double-init log lines.
- [ ] `inference.py` `[END]` line includes `score=<float>`; `success=true` requires `incident_resolved AND root_cause_identified AND score>=0.50`.
- [ ] `pytest tests/test_concurrent_sessions.py -q` (Issue #34) green; `tests/smoke_test.py` (Issue #37) green.

## Depends on

- _(none — this is the new blocker)_

## Unblocks

- #23, #24, #25, #34, #37

## Acceptance criteria

- [ ] **Concurrency**: 8 parallel `httpx.AsyncClient` `/reset` + `/step` runs under `asyncio.gather` finish without state corruption inside 60 s.
- [ ] **Rate limit**: 100 `/step` calls in 60 s from a single IP returns ≥ 1 `429`; valid `Retry-After` header.
- [ ] **Docker**: `docker run praxis-env:test` startup logs contain exactly one `Uvicorn running on` line.
- [ ] **Inference gate**: random-baseline rollout with the new threshold yields `success=false` ≥ 95% of seeds.
- [ ] **Plan docs**: `idea/Plan/Architecture/ConcurrencyModel.md` §2/§4/§6 marked "shipped"; ADR-16/ADR-20 cross-linked.
'@
```

---

# Issue #23 — Outcome × efficiency score formula

**Labels**: `P0`, `reward`, `inference`  ·  **Owner**: Architect (`@GunaPalanivel`)

```powershell
gh issue create --title "[P0] Outcome × efficiency score formula" `
  --label "P0,reward,inference" `
  --body @'
## Context

ADR-20 + `FlawsToProduction/Critical Mistakes` Mistake 9: avg-reward `compute_task_score` makes a 20-step wander tie a 4-step targeted solve. Replace with `score = outcome_quality × (1 − steps/max_steps)` where `outcome_quality = 0` unless `_incident_resolved AND _root_cause_identified`. See `idea/Plan/Architecture/RewardPolicy.md` §9.

## What to do

1. Add `compute_task_score(rewards, *, state, max_steps)` helper in `server/reward.py` per RewardPolicy §9.1 (outcome gate + linear efficiency factor + `clamp_reward`).
2. Update `inference.py` `[END]` emitter to print `score=<final>` and use it for the success gate (paired with #22).
3. Update `server/praxis_environment.py` to expose `compute_score()` on episode end so `/state` can return both `cumulative_reward` and `final_score`.
4. Update `docs/baseline_scores.md` schema to "Mean score (outcome × efficiency)" header.
5. Tests: `tests/test_reward.py::test_score_formula_outcome_times_efficiency` covers (a) wandering not resolved → 0.01, (b) resolved 4/20 → ≈ 0.80 × cum_reward, (c) clamps to `[0.01, 0.99]`.

## Done when

- [ ] `compute_task_score` lives in `server/reward.py` with the §9 signature.
- [ ] `inference.py` emits `score=` in `[END]`; success gate uses it.
- [ ] `server/praxis_environment.py.get_state()` includes `final_score: float | None`.
- [ ] `tests/test_reward.py` adds the 3-row formula test; all rows pass.
- [ ] `docs/baseline_scores.md` header updated; old avg-reward rows recomputed.

## Depends on

- #22

## Unblocks

- #24, #30, #32

## Acceptance criteria

- [ ] **Formula**: `score = outcome_quality × (1 − steps/max_steps)`, `outcome_quality = state.cumulative_reward` if both flags True else `0.0`.
- [ ] **Clamp**: final score in `[0.01, 0.99]` for all unit-test rows.
- [ ] **Backwards-compat**: `/state` still returns `cumulative_reward`; `final_score` is an additive field.
- [ ] **Determinism**: 3× re-run identical seed → byte-identical `final_score`.
- [ ] **Plan docs**: `idea/Plan/Architecture/RewardPolicy.md` §9 marked "shipped"; cross-link ADR-20.
'@
```

---

# Issue #24 — Composable Rubrics refactor (Planning / Memory / Recovery / Terminal)

**Labels**: `P0`, `reward`, `architecture`  ·  **Owner**: Architect (`@GunaPalanivel`)

```powershell
gh issue create --title "[P0] Composable Rubrics refactor (Planning / Memory / Recovery / Terminal)" `
  --label "P0,reward,architecture" `
  --body @'
## Context

ADR-18 + judges' verbatim checklist item #13 (_"composable rubrics > monolithic scoring"_). Refactor `server/reward.py` into 4 rubric classes with weights 0.20 / 0.20 / 0.20 / 0.40 summing to 1.0. Existing per-task `event_values` become inputs to the rubrics. Spec: `idea/Plan/Architecture/RewardPolicy.md` §8.

## What to do

1. Create `praxis_env/rubrics/` package: `base.py` (`Rubric` ABC with `name`, `weight`, `score(trajectory)`), `planning.py`, `memory.py`, `recovery.py`, `terminal.py`. Each `score()` returns a value in `[-1.0, 1.0]`.
2. `server/reward.py::RewardEngine` accepts `rubrics: Sequence[Rubric] = DEFAULT_RUBRIC_BUNDLE`; `score(trajectory)` returns `RewardBreakdown(planning, memory, recovery, terminal, total)`. Engine init asserts `sum(weights) == 1.0`.
3. `Trajectory` dataclass added in `praxis_env/trajectory.py` carrying step_count, action history, world state delta, memory state, plan state — inputs each rubric reads.
4. `/step` response `info` includes `breakdown: {"planning": float, "memory": float, "recovery": float, "terminal": float}` per `idea/Plan/Architecture/APIContract.md` §3.
5. `tests/test_rubrics.py` (Issue #34): orthogonality test, weights-sum invariant, each rubric's clamp invariant.

## Done when

- [ ] `praxis_env/rubrics/` package exists with the 4 rubric classes + `DEFAULT_RUBRIC_BUNDLE`.
- [ ] `RewardEngine` returns `RewardBreakdown` with the 4 rubric scores; total `clamp_reward`-bounded.
- [ ] `/step` payload includes `info.breakdown`.
- [ ] All existing reward tests still pass against the rubric-aware engine (per-task `event_values` route to MemoryRubric / TerminalRubric correctly).
- [ ] `pytest tests/test_rubrics.py` green.

## Depends on

- #22, #23

## Unblocks

- #25, #26, #30, #31, #32, #34

## Acceptance criteria

- [ ] **Weights sum to 1.0**: asserted at engine init; raising 0.21 anywhere fails the assert.
- [ ] **Orthogonality**: setting any one rubric weight to 0.0 drops `RewardBreakdown.total` by exactly `weight × that_rubric_score`.
- [ ] **Clamp**: `RewardBreakdown.total` always in `[0.01, 0.99]`.
- [ ] **API parity**: `info.breakdown` keys match `idea/Plan/Architecture/APIContract.md` §3 example.
- [ ] **Plan docs**: `idea/Plan/Architecture/RewardPolicy.md` §8 marked "shipped".
'@
```

---

# Issue #25 — MissionPlan + planning actions

**Labels**: `P0`, `mission-ops`, `actions`  ·  **Owner**: TechLead (`@Gokul287`)

```powershell
gh issue create --title "[P0] MissionPlan + planning actions" `
  --label "P0,mission-ops,actions" `
  --body @'
## Context

ADR-16 + `FlawsToProduction/Verdict.md`: introduce 5 first-class agent commands (`create_plan`, `revise_plan`, `checkpoint`, `submit_report`, `request_clarification`) and the `MissionPlan` dataclass. Adds `mission_id`, `phase`, `time_budget`, `pending_objectives` to `PraxisObservation`. Spec: `idea/Plan/Architecture/APIContract.md` §2 + §2.4 and `idea/Plan/Architecture/DataFlow.md` §7.

## What to do

1. `praxis_env/mission_plan.py`: `MissionPlan` dataclass with `milestones: list[str]`, `revisions: int`, `checkpoints_completed: list[str]`, `create / revise / checkpoint(milestone, world_state)` methods.
2. `server/command_parser.py`: extend `KNOWN_ACTIONS` with the 5 planning commands and their grammars; rate-limit `request_clarification` to 1 per episode.
3. `praxis_env/models.py`: extend `PraxisObservation` and `PraxisState` with the 4 MissionOps fields per `idea/Plan/Architecture/APIContract.md`.
4. `server/praxis_environment.py`: route planning commands to `MissionPlan`; emit `plan.created_pre_cutoff`, `plan.covers_all_root_causes`, `plan.revised_after_evidence`, `checkpoint.consistent`, `submit_report.consistent_with_world_state` reward tags read by the rubrics.
5. Update `AVAILABLE_COMMANDS` in observations to advertise the 5 new commands.

## Done when

- [ ] `MissionPlan` class lands with full unit tests (`tests/test_mission_plan.py`).
- [ ] All 5 commands parse correctly in `command_parser` (positive + negative cases).
- [ ] Observations include `mission_id`, `phase`, `time_budget`, `pending_objectives` (None / empty for non-mission scenarios).
- [ ] PlanningRubric + RecoveryRubric + TerminalRubric pick up the new tags.
- [ ] `pytest -q` green; new tests for each command's reward tag.

## Depends on

- #22, #24

## Unblocks

- #26, #34

## Acceptance criteria

- [ ] **Schema**: `extra="forbid"` still passes; new fields are `None` / `[]` for legacy scenarios.
- [ ] **Reward tags**: each planning command emits exactly one named tag with value matching `idea/Plan/Architecture/ScenarioCatalog.md` §3.6.
- [ ] **Rate-limit**: 2nd `request_clarification` in same episode is no-op (no negative reward, no extra artifact).
- [ ] **Determinism**: same `(seed, plan history)` → identical observation deltas.
- [ ] **Plan docs**: `idea/Plan/Architecture/APIContract.md` §2 + §2.4 marked "shipped".
'@
```

---

# Issue #26 — MissionScenario: phases, scattered, hidden deps, disturbance, recovery

**Labels**: `P0`, `mission-ops`, `scenarios`  ·  **Owner**: TechLead (`@Gokul287`)

```powershell
gh issue create --title "[P0] MissionScenario: phases, scattered, hidden deps, disturbance, recovery" `
  --label "P0,mission-ops,scenarios" `
  --body @'
## Context

ADR-16. Replaces `MegaIncidentScenario` with `MissionScenario` exposing the 8-phase mission: Intake → Exploration → Planning → Execution → Disturbance → Recovery → Completion → Reflection over `MAX_STEPS=150`, `MEMORY_CUTOFF_OVERRIDE=30`. Hidden dependencies + disturbance injection per `idea/Plan/Architecture/ScenarioCatalog.md` §3.3.

## What to do

1. New `praxis_env/scenarios/mission_scenario.py` (rename old `mega_incident.py` → kept as alias for back-compat or deleted; coordinate via #29). Scenario `NAME = "cascading-platform-failure"` registers a MissionPlan, owns phase machine, tracks 3 RC tags + 6 red herrings.
2. Implement the phase state machine: phase transitions are step-bounded but advanced by agent actions (e.g., entering Planning after first `create_plan`).
3. Hidden-dependency engine: e.g., `restart_service database` before `cdn_tls` resolved fails with `tls_handshake` next observation; emits `recovery.detected_disturbance_within_3_steps` if the agent rolls back/replans.
4. Disturbance injection: at step `~96–105` (deterministic per seed) inject a queue-backlog spike that invalidates one milestone; if agent `revise_plan`, emit `recovery.replan_after_disturbance`.
5. Resolution rule: `_incident_resolved=True` only when (3 RCs diagnosed) + (3 remediations succeeded) + `submit_report` consistent with world state.

## Done when

- [ ] `MissionScenario` registered as `cascading-platform-failure` (or co-existing alias clarified in #29).
- [ ] All 8 phases reachable in deterministic replay with a fixed seed.
- [ ] Hidden dependency triggers `tls_handshake` failure when expected; rollback path scored.
- [ ] Disturbance injection deterministic per seed; replan path scored.
- [ ] `tests/test_task5_mission.py` (Issue #34) green for the optimal-path trajectory.

## Depends on

- #24, #25

## Unblocks

- #27 (artifact integration), #34, #33

## Acceptance criteria

- [ ] **Phases**: `phase` field cycles through all 8 over a 150-turn replay.
- [ ] **Hidden deps**: bypassed-deps trajectory scores strictly lower (≥ 0.05 lower) than dependency-respecting trajectory under same final actions.
- [ ] **Disturbance**: same seed, fixed action sequence → byte-identical disturbance step + content.
- [ ] **Resolution gate**: missing any of (3 diagnoses, 3 remediations, consistent report) ⇒ `_incident_resolved=False`.
- [ ] **Plan docs**: `idea/Plan/Architecture/ScenarioCatalog.md` §3 marked "shipped".
'@
```

---

# Issue #27 — ArtifactStore + Rootly logs-dataset vendoring

**Labels**: `P0`, `mission-ops`, `data`, `compliance`  ·  **Owner**: TechLead (`@Gokul287`)

```powershell
gh issue create --title "[P0] ArtifactStore + Rootly logs-dataset vendoring" `
  --label "P0,mission-ops,data,compliance" `
  --body @'
## Context

ADR-17 + S33 + `FlawsToProduction/The Situation First.md`: real Rootly production logs (Apache-2.0) become mission artifacts. Vendor a small sample under `data/artifacts/` with NOTICE.md. Spec: `idea/Plan/Architecture/ScenarioCatalog.md` §7.

## What to do

1. `praxis_env/artifacts.py::ArtifactStore` per ScenarioCatalog §7.3: `__init__(root, seed)`, `_load()` index by `(kind, service)`, `draw(kind, service, n)` deterministic, `attribution()` string surfaced in `/metadata`.
2. Vendor a ≤ 200 KB de-duplicated sample under `data/artifacts/{logs,runbooks,tickets,notes}/` from Rootly `logs-dataset`. Strip any PII (verified by `pre-commit-hooks` GitGuardian on this subdir).
3. `data/artifacts/NOTICE.md`: Apache-2.0 attribution + dataset URL + commit hash + license text. `LICENSE-3rd-party` updated.
4. Wire `ArtifactStore` into `MissionScenario` (Issue #26) + `MemoryLeakScenario` (Issue #28): `query_logs` returns 1 log excerpt; `check_runbook` returns runbook excerpt; `check_runbook kind=ticket` returns ticket excerpt; `/reset` Intake observation includes 1 on-call note.
5. `openenv.yaml` adds top-level `data_sources: [{name: rootly-logs-dataset, license: Apache-2.0, url: ..., vendored_at: data/artifacts/}]`.

## Done when

- [ ] `praxis_env/artifacts.py` ships with `tests/test_artifacts.py` (Issue #34) green.
- [ ] `data/artifacts/` vendored with NOTICE + README; total size ≤ 200 KB.
- [ ] GitGuardian scan on `data/artifacts/` passes (no secrets / PII).
- [ ] `MissionScenario` returns Rootly-sourced excerpts on `query_logs` and `check_runbook`.
- [ ] `/metadata` lists `data_sources` block with attribution.

## Depends on

- #26

## Unblocks

- #28, #29, #33, #34

## Acceptance criteria

- [ ] **Determinism**: `(seed, kind, service, n)` → identical excerpts across 3 runs.
- [ ] **License**: NOTICE.md + LICENSE-3rd-party present; CI checks for their existence.
- [ ] **Provenance**: each `Artifact.source` string includes `rootly:logs-dataset/<file>#L<a>-L<b>`.
- [ ] **Size**: `du -sh data/artifacts` ≤ 200 KB.
- [ ] **Plan docs**: `idea/Plan/Architecture/ScenarioCatalog.md` §7 marked "shipped".
'@
```

---

# Issue #28 — memory-leak scenario integrates Rootly worker-OOM excerpts

**Labels**: `P1`, `scenarios`, `data`  ·  **Owner**: SDE (`@snehasneha56526-arch`)

```powershell
gh issue create --title "[P1] memory-leak scenario integrates Rootly worker-OOM excerpts" `
  --label "P1,scenarios,data" `
  --body @'
## Context

The `memory-leak` scenario already exercises memory cutoff. Wiring Rootly worker-OOM log excerpts via `ArtifactStore` (Issue #27) makes the second-most-shown task feel as authentic as MissionOps for ~30 minutes of work.

## What to do

1. `praxis_env/scenarios/memory_leak_scenario.py`: in `__init__`, instantiate `ArtifactStore(seed=self._rng.randint(0, 2**31))`; on `query_logs service=worker`, append a deterministic Rootly excerpt to `investigation_result`.
2. Update `tests/test_task4_memory_leak.py`: assert that `investigation_result` contains a Rootly source string after `query_logs`.
3. Confirm the existing cutoff at step 20 + Rootly excerpt size keeps observation under existing token budget (no judging risk).

## Done when

- [ ] `memory-leak` `query_logs service=worker` returns at least one Rootly-sourced log line.
- [ ] `test_task4_memory_leak.py` asserts excerpt presence + determinism across reruns.
- [ ] No new failures in existing test suite.

## Depends on

- #27

## Unblocks

- #34

## Acceptance criteria

- [ ] **Authenticity**: excerpt source string visible in observation.
- [ ] **Size**: observation token count within existing per-step budget.
- [ ] **Determinism**: same seed → identical worker excerpts.
- [ ] **Backwards-compat**: existing reward vectors unchanged for memory-only paths.
- [ ] **Plan docs**: `idea/Plan/Architecture/ScenarioCatalog.md` §1 row updated.
'@
```

---

# Issue #29 — openenv.yaml + /metadata refresh (tasks, data_sources, rubrics)

**Labels**: `P0`, `manifest`, `api`  ·  **Owner**: SDE (`@snehasneha56526-arch`)

```powershell
gh issue create --title "[P0] openenv.yaml + /metadata refresh (tasks, data_sources, rubrics)" `
  --label "P0,manifest,api" `
  --body @'
## Context

`openenv.yaml` and `/metadata` must advertise: 6 tasks (with mission `phases`), `supports_concurrent_sessions: true`, `data_sources` (Rootly), and `rubrics` (4 entries summing to 1.0) per `idea/Plan/Architecture/APIContract.md` §3.

## What to do

1. `openenv.yaml`: refresh task list (`cascading-platform-failure` → `difficulty: mission, max_steps: 150, phases: [...]`), keep `procedural-incident` shipped row.
2. `openenv.yaml`: add top-level `data_sources` (from #27) + `rubrics` (from #24) blocks.
3. `server/app.py::metadata()`: emit the new tasks shape + `data_sources` + `rubrics` arrays.
4. `praxis_env/scenarios/__init__.py`: registry update so the `MissionScenario` (Issue #26) is loaded under `cascading-platform-failure`.

## Done when

- [ ] `uv run openenv validate` exits 0 against the new manifest.
- [ ] `curl /metadata | jq .data_sources, .rubrics` returns expected blocks.
- [ ] `tests/test_metadata.py` asserts presence of the new blocks + correct types.
- [ ] All 6 tasks resolve via `/reset {task_name: ...}`.

## Depends on

- #24, #26, #27

## Unblocks

- #36, #37

## Acceptance criteria

- [ ] **Validator**: `openenv validate` PASS.
- [ ] **Schema**: `/metadata` JSON includes both new top-level keys.
- [ ] **Test**: metadata test asserts rubric weights sum to 1.0.
- [ ] **Backwards-compat**: legacy clients reading `/metadata.tasks[].name` still get the 6 names.
- [ ] **Plan docs**: `idea/Plan/Architecture/APIContract.md` §3 example matches reality.
'@
```

---

# Issue #30 — 3-row baseline scores + MissionOps SRE prompt

**Labels**: `P0`, `evidence`, `inference`  ·  **Owner**: SDE (`@snehasneha56526-arch`)

```powershell
gh issue create --title "[P0] 3-row baseline scores + MissionOps SRE prompt" `
  --label "P0,evidence,inference" `
  --body @'
## Context

`docs/baseline_scores.md` rows 1–3 (random / no-prompt / SRE-prompt) under the new outcome × efficiency formula (#23). Expanded MissionOps system prompt teaches the agent to call `create_plan`, `save_finding`, `recall_memory`, `revise_plan`, `submit_report`. Spec: `idea/Plan/Architecture/RewardPolicy.md` §9 + `idea/Plan/Demo/EvidencePackage.md` §1.

## What to do

1. `inference.py`: define `SRE_MISSIONOPS_SYSTEM_PROMPT` covering planning + memory + recovery actions; selectable via `--system-prompt {sre,none,random}`.
2. Add `random_baseline()` helper that emits random valid commands.
3. Run 5 seeded rollouts per mode for `cascading-platform-failure` (and 1 sanity run on `single-service-alert`); compute mean score with the new formula.
4. Commit the 3-row table to `docs/baseline_scores.md`. Format per Demo/EvidencePackage.md §1 (header line + 3 rows + reproduction commands).
5. Wire the `--runs` and `--seed` flags so judges can re-run.

## Done when

- [ ] `docs/baseline_scores.md` has 3 rows: random / no-prompt / SRE-prompt with mean scores + behaviours.
- [ ] `inference.py --system-prompt sre --runs 5 --seed 2026` reproduces row 3 ± 0.02.
- [ ] Each row''s `behaviour` description grounded in observed trajectories.
- [ ] Total runtime ≤ 12 min on local CPU (fits under the 20-min judging budget).
- [ ] 5–8× lift between row 1 and row 3.

## Depends on

- #23, #25, #26

## Unblocks

- #32, #33, #36, #38

## Acceptance criteria

- [ ] **Scores**: under outcome × efficiency, row 1 ≤ 0.05, row 3 ≥ 0.15.
- [ ] **Reproducibility**: 3 reruns per row stay within ± 0.02 mean.
- [ ] **Determinism**: random_baseline is seedable.
- [ ] **Format**: table reads correctly in GitHub markdown; `Reproduction commands` block included.
- [ ] **Plan docs**: `idea/Plan/Demo/EvidencePackage.md` §1 marked "shipped".
'@
```

---

# Issue #31 — train_praxis_grpo.py with Unsloth + mtGRPO

**Labels**: `P0`, `training`, `pipeline`  ·  **Owner**: TechLead (`@Gokul287`)

```powershell
gh issue create --title "[P0] train_praxis_grpo.py with Unsloth + mtGRPO" `
  --label "P0,training,pipeline" `
  --body @'
## Context

ADR-19 + S35: Unsloth GRPO with multi-turn trajectory rewards (mtGRPO) — turn-level credit assignment, ~2.5× throughput, stable on sparse rewards. PEP 723 dependency block; Colab T4/A10G compatible. Diagram: `idea/Plan/Architecture/DataFlow.md` §8.

## What to do

1. New `train_praxis_grpo.py` with PEP 723 deps (`unsloth`, `trl`, `praxis_env`, `wandb`, `trackio`).
2. Loads Qwen2.5-7B-Instruct via Unsloth (4-bit); fallback `Qwen2.5-3B-Instruct` if T4.
3. `GRPOTrainer(environment_factory=PraxisToolEnv, num_generations=8, max_turns=150, reward_aggregator=mtGRPO_turn_credit)`. Reads `RewardBreakdown` per turn from `/step.info.breakdown`.
4. Logs to Trackio + WandB; `wandb.init(project="praxis-mission-ops", name=run_name, mode="online")`; ensures the run is **public** (verified via API after init).
5. Saves adapter to `./checkpoints/praxis-grpo/`.

## Done when

- [ ] `python train_praxis_grpo.py --steps 5 --tasks single-service-alert` runs end-to-end on local CPU/MPS in ≤ 5 min (smoke).
- [ ] On Colab T4 with Qwen-3B fallback, 50-step run completes in ≤ 90 min.
- [ ] Trackio + WandB log mean_reward, planning, memory, recovery, terminal, loss per step.
- [ ] WandB run is public from a private window.
- [ ] Adapter checkpoint saved.

## Depends on

- #24, #25, #26

## Unblocks

- #32

## Acceptance criteria

- [ ] **Smoke**: 5-step run green locally.
- [ ] **Public run**: WandB URL opens without auth.
- [ ] **mtGRPO**: per-turn credit assignment visible in WandB charts (4 lines for the 4 rubrics).
- [ ] **Fallback**: `--model qwen-3b` flag works; documented in script header.
- [ ] **Plan docs**: `idea/Plan/Architecture/DataFlow.md` §8 marked "shipped".
'@
```

---

# Issue #32 — Training run + reward_curve + loss_curve + 4th baseline row

**Labels**: `P0`, `evidence`, `training`  ·  **Owner**: TechLead (`@Gokul287`)

```powershell
gh issue create --title "[P0] Training run + reward_curve + loss_curve + 4th baseline row" `
  --label "P0,evidence,training" `
  --body @'
## Context

Execute the run from #31 long enough to produce `docs/reward_curve.png`, `docs/loss_curve.png`, the 4th row in `docs/baseline_scores.md`, and `docs/training_links.md`. Target: ≥ 5× lift baseline → trained.

## What to do

1. Run ≥ 50 mtGRPO steps with `cascading-platform-failure` + `single-service-alert` mix. Capture:
   - `docs/reward_curve.png` (mean reward / step; trained vs random baseline on same axes).
   - `docs/loss_curve.png` (loss / step).
2. Append row 4 (`Qwen-7B mtGRPO trained`) to `docs/baseline_scores.md`.
3. Commit `docs/training_links.md` with Trackio + WandB public URLs.
4. (Optional) `docs/rubric_attribution.png` bar chart of per-rubric contribution.

## Done when

- [ ] All four `docs/` assets committed.
- [ ] Row 4 mean score ≥ 5× row 1 mean score.
- [ ] `docs/training_links.md` URLs open without auth.
- [ ] README image links resolve.

## Depends on

- #30, #31

## Unblocks

- #33, #38

## Acceptance criteria

- [ ] **Lift**: row 4 mean ≥ 0.15 (target 0.31).
- [ ] **Plot quality**: x and y axes labeled; legend present; 16:9 aspect.
- [ ] **Public links**: Trackio + WandB URLs reachable from incognito.
- [ ] **Determinism**: chart generation script (`scripts/plot_curves.py`) runs from the WandB CSV deterministically.
- [ ] **Plan docs**: `idea/Plan/Demo/EvidencePackage.md` §1 + §2 marked "shipped".
'@
```

---

# Issue #33 — Before/after rollout (the trophy moment)

**Labels**: `P0`, `evidence`, `demo`  ·  **Owner**: TechLead (`@Gokul287`)

```powershell
gh issue create --title "[P0] Before/after rollout (the trophy moment)" `
  --label "P0,evidence,demo" `
  --body @'
## Context

ADR-16 / `FlawsToProduction/The Situation First.md` "Single Most Important Thing": the memory-cutoff demo is the trophy. Capture identical-seed rollouts of baseline vs trained agent and ship the comparison as the README hero.

## What to do

1. Run baseline Qwen-7B (no adapter) on `cascading-platform-failure` seed=2026; capture full text trajectory → `docs/rollout_baseline.txt`.
2. Run trained adapter (from #32) on the same seed; capture → `docs/rollout_trained.txt`.
3. Generate `docs/rollout_compare.png`: side-by-side per-turn cumulative reward chart from the two trajectories.
4. Generate `docs/demo.gif`: 8-second loop showing the cutoff banner + baseline vs trained reactions side-by-side. Use `asciinema` + `agg`, or screen-recorded mp4 → gif.
5. Verify rollouts narratively (baseline never `create_plan`, trained calls `create_plan` + `save_finding` × 3 + `revise_plan`).

## Done when

- [ ] All 4 assets committed under `docs/`.
- [ ] `docs/rollout_compare.png` legible at 800px width.
- [ ] `docs/demo.gif` ≤ 5 MB.
- [ ] README opens with both visuals (Issue #38).

## Depends on

- #32

## Unblocks

- #38

## Acceptance criteria

- [ ] **Same seed**: both `.txt` files start with identical mission_id / observation #1.
- [ ] **Score gap**: trained final score ≥ 4× baseline final score in the captured rollouts.
- [ ] **Visible behaviour**: trained trajectory contains `create_plan`, `save_finding`, `recall_memory`, `revise_plan`, `submit_report`; baseline contains none or few.
- [ ] **GIF size**: ≤ 5 MB; loops cleanly; readable text.
- [ ] **Plan docs**: `idea/Plan/Demo/EvidencePackage.md` §3 marked "shipped".
'@
```

---

# Issue #34 — Test suite: rubrics + artifacts + mission scenario + concurrency

**Labels**: `P0`, `tests`, `quality`  ·  **Owner**: SDE (`@snehasneha56526-arch`)

```powershell
gh issue create --title "[P0] Test suite: rubrics + artifacts + mission scenario + concurrency" `
  --label "P0,tests,quality" `
  --body @'
## Context

Single PR adds the test files spawned by #22, #24, #25, #26, #27. Ensures `pytest -q` stays green and CI gates the rest of the milestone.

## What to do

1. `tests/test_rubrics.py`: weights-sum invariant; orthogonality (zero-weight ⇒ reduced total); each rubric clamp; per-task event-tag routing.
2. `tests/test_artifacts.py`: `ArtifactStore.draw()` determinism across (seed, kind, service, n); attribution string format; size check.
3. `tests/test_task5_mission.py`: 8 phases reachable; hidden-dep failure behavior; disturbance determinism; resolution-gate negative tests; optimal-path final score ≥ 0.40 in deterministic replay.
4. `tests/test_concurrent_sessions.py`: 8 parallel `httpx.AsyncClient` resets + steps; LRU eviction at session 129; TTL eviction; `slowapi` rate-limit behavior.
5. `tests/test_memory.py` extension: per-scenario `MEMORY_CUTOFF_OVERRIDE` table from `idea/Plan/Architecture/MemoryModel.md` §8.

## Done when

- [ ] All 4 new test files green; total `pytest -q` runtime ≤ 4 min.
- [ ] CI workflow runs them; coverage report committed under `docs/coverage.txt`.
- [ ] No flakes across 3 reruns.

## Depends on

- #22, #24, #25, #26, #27

## Unblocks

- #37

## Acceptance criteria

- [ ] **Coverage**: new modules ≥ 80% line coverage.
- [ ] **Determinism**: all `*_determinism` tests pass byte-equality across 3 reruns.
- [ ] **Concurrency**: async test passes under `pytest -n 4` parallelism.
- [ ] **Quality**: `ruff check` + `ruff format --check` green.
- [ ] **Plan docs**: `idea/Plan/Architecture/ConcurrencyModel.md` §6 + `idea/Plan/Architecture/RewardPolicy.md` §10 marked "shipped".
'@
```

---

# Issue #35 — Determinism + runtime + resource receipts

**Labels**: `P1`, `evidence`, `submission`  ·  **Owner**: SDE (`@snehasneha56526-arch`)

```powershell
gh issue create --title "[P1] Determinism + runtime + resource receipts" `
  --label "P1,evidence,submission" `
  --body @'
## Context

Phase-1 auto-validation needs `docs/determinism_receipt.txt`, `docs/runtime_receipt.txt`, `docs/resource_receipt.txt` to satisfy DQ rules (S3).

## What to do

1. `scripts/capture_receipts.sh` runs the 3 captures and writes the txt files.
2. Receipts include: pytest determinism output (`-k determinism`), `time` output for `inference.py` per task, `/usr/bin/time -v` peak RSS during a 6-task run.
3. Wire `tests/smoke_test.py` (Issue #37) to fail if the receipts are stale (compare git mtime with `make receipts` output age).

## Done when

- [ ] All 3 receipts present in `docs/`.
- [ ] Total inference runtime per receipt ≤ 12 min on `vCPU=2 / 8 GB`.
- [ ] Peak RSS ≤ 1.6 GB.

## Depends on

- #34

## Unblocks

- #37

## Acceptance criteria

- [ ] **Determinism**: pytest `-k determinism` exits 0 across 3 captures.
- [ ] **Runtime**: ≤ 20 min total across 6 tasks.
- [ ] **Memory**: peak RSS ≤ 1.6 GB.
- [ ] **Format**: receipts plain text, ≤ 100 lines each.
- [ ] **Plan docs**: `idea/Plan/Demo/EvidencePackage.md` §5 + §6 marked "shipped".
'@
```

---

# Issue #36 — GET /benchmark endpoint

**Labels**: `P1`, `server`, `discoverability`  ·  **Owner**: SDE (`@snehasneha56526-arch`)

```powershell
gh issue create --title "[P1] GET /benchmark endpoint" `
  --label "P1,server,discoverability" `
  --body @'
## Context

ADR-14 / Issue #21 (carried forward). Read-only adapter over `docs/baseline_scores.md` returning model-vs-mean-score JSON. <50 LOC + 3 tests + 30 min. Spec: `idea/Plan/Architecture/APIContract.md` §3 ("/benchmark").

## What to do

1. New `server/benchmark.py` with `parse_baseline_md(path) -> list[BenchmarkRow]` + Pydantic response models with `extra="forbid"` (S15).
2. `server/app.py`: mount `GET /benchmark`; cache parsed result at startup.
3. Missing-file fallback returns 200 with empty `model_scores` and helpful `note`.
4. `tests/test_benchmark.py`: 3 cases (happy, missing file, malformed file → still 200).

## Done when

- [ ] `curl /benchmark` returns the 4-row JSON shape from APIContract §3.
- [ ] Missing file ⇒ 200 with empty list and note.
- [ ] 3 unit tests green.
- [ ] No new dependency; no startup time regression.

## Depends on

- #29, #32

## Unblocks

- #38

## Acceptance criteria

- [ ] **Schema**: response matches APIContract §3 exactly (extra="forbid").
- [ ] **No 404**: missing-file path returns 200.
- [ ] **Cache**: parsed list reused across requests; one read at startup.
- [ ] **Test**: parser handles odd whitespace + extra rows gracefully.
- [ ] **Plan docs**: `idea/Plan/Architecture/APIContract.md` §3 example marked "shipped".
'@
```

---

# Issue #37 — HF Space deploy + smoke_test.py + Dockerfile production

**Labels**: `P0`, `deployment`, `submission`  ·  **Owner**: Architect (`@GunaPalanivel`)

```powershell
gh issue create --title "[P0] HF Space deploy + smoke_test.py + Dockerfile production" `
  --label "P0,deployment,submission" `
  --body @'
## Context

Build a public HF Space hosting the FastAPI server; `tests/smoke_test.py` is the same script judges run during Phase 1 (S3); `Dockerfile` finalised for HF (uvicorn CMD from #22 + uv deps).

## What to do

1. `tests/smoke_test.py` (move from `mock_validator.py`): runs the §5 sequence from `idea/Plan/Submission/SubmissionChecklist.md` end-to-end against a local uvicorn process.
2. `Dockerfile` finalisation: multi-stage (uv install → runtime), `WORKDIR /app`, `COPY data/artifacts /app/data/artifacts`, healthcheck.
3. HF Space repo: push current commit; verify `/health`, `/reset` (`cascading-platform-failure`, seed=2026), `/step` (`create_plan`), `/state`, `/metadata`, `/benchmark`.
4. Tag the Space with `openenv` per S2.

## Done when

- [ ] `tests/smoke_test.py` runs locally + in CI green.
- [ ] HF Space deploys; `/health` returns 200 from a clean private window.
- [ ] All 6 tasks resolvable via the Space.
- [ ] `Dockerfile` `docker build` ≤ 4 min on local laptop.

## Depends on

- #22, #29, #34, #35, #36

## Unblocks

- #38, #39

## Acceptance criteria

- [ ] **Health**: `curl https://huggingface.co/spaces/<org>/praxis-env/health` → `{"status":"healthy"}`.
- [ ] **Smoke**: full §5 script green from a clean clone.
- [ ] **Cold start**: first `/reset` after wakeup completes < 60 s.
- [ ] **openenv validate**: PASS against the deployed manifest.
- [ ] **Plan docs**: `idea/Plan/Submission/SubmissionChecklist.md` §1 ticked.
'@
```

---

# Issue #38 — README + mini-blog + slide deck + video

**Labels**: `P0`, `submission`, `storytelling`  ·  **Owner**: Architect (`@GunaPalanivel`)

```powershell
gh issue create --title "[P0] README + mini-blog + slide deck + video" `
  --label "P0,submission,storytelling" `
  --body @'
## Context

Storytelling 30%. README opens with `docs/rollout_compare.png` + `docs/demo.gif` + the 5-sentence pitch. Mini-blog and / or video < 2 min are mandatory deliverables (S2). Slide deck ≤ 5 slides per `idea/Plan/Demo/Narrative.md` §3.

## What to do

1. Rewrite `README.md` per `idea/Plan/Submission/ReleasePackage.md` §3 link block + `idea/Plan/Submission/SubmissionChecklist.md` §4 contents.
2. Publish HF mini-blog: title verbatim from `FlawsToProduction/The Situation First.md` ("_Training LLMs to Remember: Praxis MissionOps and Long-Horizon Operational Reasoning_"). Embed reward curve, one Rootly snippet, before/after rollout.
3. Record ≤ 2-min video (or fallback to YouTube short) following `idea/Plan/Demo/ScreenplayScript.md` §2 cue sheet.
4. Build 5-slide deck (Google Slides public OR PDF in repo); slide assets per `idea/Plan/Demo/ScreenplayScript.md` §4.
5. All public URLs land in `idea/Plan/Submission/ReleasePackage.md` §2.

## Done when

- [ ] README opens with the visuals; all 5 sentences appear; all link rows resolve.
- [ ] Mini-blog public URL committed.
- [ ] Video URL committed; runtime ≤ 2:00.
- [ ] Slide deck URL committed.
- [ ] `tests/test_readme.py` (lightweight) verifies README contains all required sections.

## Depends on

- #32, #33, #36, #37

## Unblocks

- #39

## Acceptance criteria

- [ ] **Above-the-fold**: first 30 vertical-pixels-after-title block contains both visuals + first sentence.
- [ ] **All links**: tested from incognito.
- [ ] **Mini-blog**: includes reward curve image + Rootly snippet + before/after rollout link.
- [ ] **Video**: ≤ 2 min, captioned, hosted on YouTube or HF Spaces video tab.
- [ ] **Plan docs**: `idea/Plan/Demo/Narrative.md` + `idea/Plan/Demo/ScreenplayScript.md` marked "shipped".
'@
```

---

# Issue #39 — [Tracker] Submission checklist (the 20-item judge map)

**Labels**: `tracker`, `submission`, `priority:p0`  ·  **Owner**: Architect (`@GunaPalanivel`)

> File this **last**, after #22–#38 are open. The body is the verbatim ready-to-paste block from `idea/Plan/Submission/SubmissionChecklist.md` §8.

```powershell
gh issue create --title "Tracker — Praxis MissionOps Submission (20-item judge checklist)" `
  --label "tracker,submission,priority:p0" `
  --body @'
## Praxis MissionOps — final submission tracker

This tracker mirrors the 4 weighted hackathon axes (Environment Innovation 40%, Storytelling & Presentation 30%, Reward Improvement 20%, Reward & Training Pipeline 10%). Each implementation issue (#22 → #38) ships one or more checkboxes below. The tracker closes only after every box is green and the submission button is clicked.

### Hard auto-validation gates (DQ if any fail)

- [ ] HF Space `/health` returns `{"status":"healthy"}` from a private window.
- [ ] `uv run openenv validate` exits 0 on the submitted commit.
- [ ] `docker build .` succeeds; container `CMD` is `uvicorn server.app:app --host 0.0.0.0 --port 7860`.
- [ ] `inference.py` runs end-to-end and emits `[START]/[STEP]/[END]` with `score=` field on every line.
- [ ] 6 tasks ship with deterministic graders: `single-service-alert`, `ambiguous-incident`, `cascading-failure`, `memory-leak`, `cascading-platform-failure` (MissionOps), `procedural-incident`.
- [ ] Rewards bounded in (0.0, 1.0); `task_score = outcome × efficiency`.
- [ ] Total runtime < 20 min on vCPU=2 / 8 GB.
- [ ] Mandatory env vars wired: `API_BASE_URL`, `MODEL_NAME`, `HF_TOKEN`.
- [ ] OpenAI client used for all LLM calls.
- [ ] `inference.py` lives at repo root.

### Axis A — Environment Innovation (40%)

- [ ] **#1.** MissionOps long-horizon environment — `cascading-platform-failure` ships as 80–150 turn mission with 8 phases (Intake / Exploration / Planning / Execution / Disturbance / Recovery / Completion / Reflection). _(closes #26, references ADR-16)_
- [ ] **#2.** Real Rootly production logs as mission artifacts — `praxis_env/artifacts.py::ArtifactStore` injects vendored Apache-2.0 Rootly `logs-dataset` excerpts as runbooks, tickets, notes, and log lines; `data/artifacts/NOTICE.md` committed. _(closes #27, references ADR-17)_
- [ ] **#3.** Scattered instructions across artifacts — root-cause hints split across `runbook` / `ticket` / `note` / `log` artifact kinds; agent never gets a single briefing.
- [ ] **#4.** Hidden dependencies + Disturbance/Recovery phase — RC #2 blocks RC #1 remediation; deploy disturbance at step ~100 invalidates plan and forces `revise_plan`. `RecoveryRubric` measures detection within ≤ 3 steps.
- [ ] **#5.** Hard memory cutoff with explicit memory actions — `save_finding`, `recall_memory` are first-class agent commands; full investigation log deleted at `CONTEXT_CUTOFF_STEP`; mission cutoff = 30/150 (20%). _(closes #25)_
- [ ] **#6.** Composable Rubrics — `PlanningRubric` 0.20 / `MemoryRubric` 0.20 / `RecoveryRubric` 0.20 / `TerminalRubric` 0.40; engine asserts weights sum to 1.0 ± 1e-6; orthogonality tested. _(closes #24, references ADR-18)_
- [ ] **#7.** Procedural mission generation — `procedural-incident` shipped with seeded determinism + 3 difficulties; `(seed, difficulty)` → byte-identical scenario.

### Axis B — Storytelling & Presentation (30%)

- [ ] **#8.** Before/after rollout deliverables — `docs/rollout_baseline.txt`, `docs/rollout_trained.txt`, `docs/rollout_compare.png`, `docs/demo.gif` committed; same `mission_id` and seed; lift ≥ 4×. _(closes #33)_
- [ ] **#9.** 5-sentence pitch lands in ≤ 50 seconds — rehearsed; speaker-notes-ready.
- [ ] **#10.** README opens with the visual — first content block is `docs/rollout_compare.png` followed by `docs/demo.gif`, then the 5-sentence pitch. _(closes #38)_
- [ ] **#11.** Mini-blog OR YouTube ≤ 2 min — public link in README + `Submission/ReleasePackage.md`.
- [ ] **#12.** Slide deck (≤ 5 slides) — public Google Slides or PDF in repo.
- [ ] **#13.** Q&A drill prepared — verbatim answers to the 5 likely judge questions in `idea/Plan/Demo/Narrative.md` §6.

### Axis C — Reward Improvement (20%)

- [ ] **#14.** 4-row score gap table — `docs/baseline_scores.md` rows: random / no-prompt / SRE-prompt / mtGRPO-trained; ≥ 4× lift baseline → trained. _(closes #30, #32)_
- [ ] **#15.** Reward + loss curves — `docs/reward_curve.png` + `docs/loss_curve.png` from ≥ 50 mtGRPO steps; both inline in README. _(closes #32)_
- [ ] **#16.** Public Trackio + WandB run URLs — `docs/training_links.md` lists both; both public from a private window.
- [ ] **#17.** Outcome × efficiency score formula — `compute_task_score = outcome × efficiency` with `outcome = 0` unless `_incident_resolved AND _root_cause_identified`; old avg-reward formula removed. _(closes #23, references ADR-20)_

### Axis D — Reward & Training Pipeline (10%)

- [ ] **#18.** `train_praxis_grpo.py` with Unsloth + mtGRPO — turn-level credit assignment over per-rubric event credit; runs end-to-end on Colab T4/A10G. _(closes #31, references ADR-19)_
- [ ] **#19.** TRL `environment_factory` snippet works — 10–15 line snippet in README copy-pastes-runs against the deployed HF Space.
- [ ] **#20.** HF Space deploys + `openenv validate` + `inference.py` reproduces — full submission-day smoke (`tests/smoke_test.py`) runs green from a clean clone. _(closes #37)_

### Acceptance

This tracker is the only issue that closes after submission. Closing it is the visible signal that we hit every weighted axis.

---

**Depends on**: #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38
'@
```

---

## Verification after filing

```powershell
gh issue list --state open --label P0 --limit 50
gh issue list --state open --label tracker --limit 5
```

The expected output: 13 P0 issues (`#22-#27`, `#29-#34`, `#37-#38`), 4 P1 issues (`#28`, `#35`, `#36`, plus tail), and 1 tracker (`#39`) — matching the issue index in `github_issues.md` §"Index — assignment + lane".

For lane / reviewer / dependency details, see [`dependency_graph.md`](./dependency_graph.md). For the wave timeline, see [`implementation_plan.md`](./implementation_plan.md) §6.
