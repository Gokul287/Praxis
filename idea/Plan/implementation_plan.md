# Praxis -> Theme #2: Final Execution Plan (v2.1)

> **Status**: 21 issues defined, decisions locked, docs aligned with reality (audit patch v2.1 absorbed)
> **Hackathon**: OpenEnv India 2026 | April 25-26
> **Theme**: #2 -- (Super) Long-Horizon Planning & Instruction Following
> **Plan source of truth**: `idea/Plan/github_issues.md` (21 issues), `idea/Plan/Architecture/*` (7 docs), `idea/Plan/Demo/*`, `idea/Plan/Project/*`, `idea/Plan/Submission/*`.
>
> **v2.1 patch summary**: evidence-gating made explicit across reward + new scenarios (ADR-13); ambiguous-incident discoverability tweak folded into Issue #19; new Issue #21 adds `GET /benchmark` (ADR-14). Critique items #1, #2, #3, #6, #9 already covered in v2; #8 (composite GRPO reward) deliberately not changed -- TRL already consumes `observation.reward: float`.

---

## Decisions (Locked) -- see `Project/DecisionLog.md` for full ADRs

| #   | Decision      | Answer                                                                    | ADR       |
| --- | ------------- | ------------------------------------------------------------------------- | --------- |
| 1   | Scope         | Mega-incident + Memory + Procedural. Drop scattered-instructions.         | ADR-07    |
| 2   | Compute       | Inference-first evidence NOW. Request HF credits in parallel.             | ADR-08    |
| 3   | Pitch         | Merged: lead memory, close with process-aware reward.                     | ADR-09    |
| 4   | Concurrency   | `SessionManager` + `X-Session-Id`; no module singletons.                  | ADR-04    |
| 5   | Memory        | Explicit `save_finding` / `recall_memory` + step-30 cutoff.               | ADR-05/06 |
| 6   | Review policy | Guna<->Gokul reciprocal; SDE PRs reviewed by both leads + auto PR review. | ADR-11    |
| 7   | Evidence gating | `remediation.*` events score 0 across all scenarios until `_root_cause_identified` is True. | ADR-13 |
| 8   | Benchmark surface | Add `GET /benchmark` reading `docs/baseline_scores.md` (Issue #21).                       | ADR-14 |

---

## The Pitch (30 seconds, verbatim) -- see `Demo/Narrative.md` for the full beat sheet

> "Production incidents can take 4-6 hours. Current AI agents fail at step 30 because their context fills up with noise. Praxis forces the agent to manage its own memory -- save the important finding, discard the noise, recall what matters when you need it. After step 30, the full log is gone. Only what you chose to remember remains. And we reward the agent for thinking correctly through the whole trajectory, not just solving the final step."

---

## Architecture index (rebuilt under `idea/Plan/Architecture/`)

| Doc                                                         | Purpose                                                                                |
| ----------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| [`APIContract.md`](./Architecture/APIContract.md)           | Endpoints, schemas, X-Session-Id header, field-parity rules.                           |
| [`DataFlow.md`](./Architecture/DataFlow.md)                 | End-to-end sequence diagrams: reset, step (memory branch), reward, episode terminator. |
| [`ConcurrencyModel.md`](./Architecture/ConcurrencyModel.md) | SessionManager, lock, LRU eviction, OpenEnv parity flags.                              |
| [`MemoryModel.md`](./Architecture/MemoryModel.md)           | `PraxisMemory` class, cutoff, save/recall semantics, reward integration.               |
| [`ScenarioCatalog.md`](./Architecture/ScenarioCatalog.md)   | All 6 tasks (4 shipping + mega + procedural).                                          |
| [`RewardPolicy.md`](./Architecture/RewardPolicy.md)         | Per-task event tables + cross-task memory bonus row.                                   |
| [`SessionLifecycle.md`](./Architecture/SessionLifecycle.md) | Reset/step/done/eviction state machine.                                                |

---

## Evidence Index (full: `Project/EvidenceIndex.md`)

| ID  | Source                                 | Why                                                                      |
| --- | -------------------------------------- | ------------------------------------------------------------------------ |
| S1  | Meta engineer venue statement          | "Used in PyTorch right away"; "Anthropic trains next model on it".       |
| S2  | External Themes & Judging Criteria     | 40/30/20/10 weights.                                                     |
| S3  | How Judging Works                      | Phase 1 auto gates; vCPU=2/8GB; <20 min runtime.                         |
| S9  | `server/app.py:46`                     | Global env singleton -- the concurrency blocker.                         |
| S14 | OpenEnv `interfaces.py`                | `Environment` ABC, `SUPPORTS_CONCURRENT_SESSIONS`, Rubric.               |
| S16 | OpenEnv `cli/templates/.../app.py`     | `create_app(..., max_concurrent_envs=N)` factory.                        |
| S26 | Theme #2 description                   | "Beyond context memory limits".                                          |
| S28 | arxiv AgeMem                           | Memory ops as tool-based GRPO actions.                                   |
| S29 | arxiv 2601.07190                       | Context Bloat -- passive summarisation fails.                            |
| S30 | GRPO survey                            | Process rewards > terminal rewards.                                      |
| S31 | How Judging Works (mandatory env vars) | API_BASE_URL, MODEL_NAME, HF_TOKEN; OpenAI client; inference.py at root. |

Full mapping in [`Project/EvidenceIndex.md`](./Project/EvidenceIndex.md).

---

## Phased delivery plan (extends the original Phases 1-10)

> Phases 1-10 are complete (4 shipping tasks, 289 tests, Docker/HF Space, inference.py). Phases 11-13 add the Theme #2 finale.

### Phase 11 -- Memory + Concurrency Foundation (Issues #1-#6)

**Goal**: Sessions work in parallel; `PraxisMemory` is wired into reset/step/observation/reward across all task policies.

**Deliverables**:

- `server/app.py` -> `SessionManager` (Issue #1).
- `praxis_env/models.py` -> memory-aware `PraxisObservation` + `PraxisState` (Issue #2).
- `praxis_env/memory.py` -> new (Issue #3).
- `server/command_parser.py` -> `save_finding` / `recall_memory` (Issue #4).
- `server/reward.py` -> `_with_memory_events` helper applied to every policy (Issue #5).
- `server/praxis_environment.py` -> memory hook + cutoff observation rewrite (Issue #6).

**Validation**:

- [ ] `pytest -q` still 289+ green.
- [ ] `tests/test_concurrent_sessions.py` (Issue #15) passes.
- [ ] `tests/test_memory.py` (Issue #13) passes.
- [ ] `uv run openenv validate` PASS.

### Phase 12 -- New Scenarios + Training Evidence (Issues #7-#12)

**Goal**: Mega-incident + procedural generator land; SRE-prompt baseline + GRPO script (and curve, if credits) provide the 20% rewards-criterion proof.

**Deliverables**:

- `praxis_env/scenarios/mega_incident.py` (Issue #7).
- `praxis_env/scenarios/procedural_incident.py` (Issue #8).
- `praxis_env/scenarios/__init__.py` + `openenv.yaml` registry (Issue #9).
- `inference.py` SRE prompt + `docs/baseline_scores.md` (Issue #10).
- `train_praxis_grpo.py` with TRL `environment_factory` + Trackio (Issue #11).
- `docs/reward_curve.png` (Issue #12, if HF credits arrive).

**Validation**:

- [ ] All 6 tasks reachable via `/reset` with valid initial observations.
- [ ] Score gap >= 5x between random baseline and SRE-prompted Qwen.
- [ ] Training script syntactically correct; runs end-to-end on Colab T4 if a curve is captured.

### Phase 13 -- Submission Package (Issues #13-#21)

**Goal**: Tests, validation, deploy, README, demo, mini-blog, slides, benchmark surface -- everything Issue #20 needs to click submit.

**Deliverables**:

- `tests/test_memory.py`, `tests/test_task5_mega_incident.py`, `tests/test_task6_procedural.py`, `tests/test_concurrent_sessions.py` (Issues #13-#15) -- including the new `test_remediation_before_diagnosis_scores_zero` evidence-gate tests (ADR-13).
- `tests/smoke_test.py` (Issue #16).
- Full server validation script (Issue #17).
- Updated Dockerfile + HF Space deploy (Issue #18).
- README rewrite + ambiguous-incident discoverability tweak (Issue #19).
- Demo Narrative + ScreenplayScript + mini-blog/video + slides (Issue #20).
- `GET /benchmark` endpoint reading `docs/baseline_scores.md` (Issue #21, ADR-14).

**Validation**:

- [ ] `tests/smoke_test.py` PASS.
- [ ] `tests/test_api_benchmark.py` PASS (3 cases: happy path, missing file, extra-fields rejection).
- [ ] HF Space `/health` and `/benchmark` 200 from a private window.
- [ ] README link block resolves all URLs (including `/benchmark`).
- [ ] 60-second pitch rehearsed by Gokul, timed.

---

## Execution timeline (T+0 = blocker landed)

```
T+0:00  #1 Sessions (BLOCKER)                 -> 60 min
T+1:00  #2 Schema (Guna lane)  || #7 Mega (Gokul lane)
T+2:00  #3 Memory  || #7 cont. || #4 Parser (SDE)
T+3:00  #6 Env hook || #8 Procedural || #5 Reward (SDE)
T+4:00  #9 Registry/yaml (SDE) || #10 SRE prompt (Gokul)
T+4:45  #11 GRPO script (Gokul) || #13 Memory tests (SDE)
T+5:45  #12 Reward curve (Gokul, GPU permitting) || #14 Scenario tests (SDE) || #15 Concurrent tests (SDE)
T+7:00  #16 Cleanup || #17 Server validation
T+7:45  #18 Docker+HF deploy (Gokul) + #21 GET /benchmark (Gokul tail) || #19 README rewrite (Guna)
T+8:30  #20 Demo+blog+video+slides (Gokul)
T+9:00  Submit (frozen commit)
```

Critical path: 1 -> 3 -> 6 -> 7 -> 9 -> 17 -> 18 -> 19/20 (~9 h with buffer).

---

## Minimum Submission Checklist (mirrors `Submission/SubmissionChecklist.md`)

- [ ] OpenEnv (latest) used.
- [ ] Training script (TRL) checked in.
- [ ] Reward evidence (curve OR score gap table) committed under `docs/`.
- [ ] Mini-blog OR ≤2 min video linked from README.
- [ ] HuggingFace Space deployed and 200.
- [ ] README explains problem, env, results in 3-5 minutes of reading.
- [ ] `inference.py` at root with `[START]/[STEP]/[END]` contract.
- [ ] 6 tasks with deterministic graders.
- [ ] Rewards in (0.0, 1.0).
- [ ] Runtime < 20 min on vCPU=2 / 8 GB.

---

## PLAN READY

All 21 issues are evidence-grounded, file-pathed, schema-backed, and review-policy-tagged. Proceed to `idea/Plan/github_issues.md` for full bodies and `idea/Plan/dependency_graph.md` for the wave plan.
