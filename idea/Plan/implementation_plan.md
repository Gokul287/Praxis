# Praxis MissionOps — Final Execution Plan (v3.0)

> **Status**: 17 implementation issues (`#22 → #38`) + 1 tracker issue (`#39`). Pivot to MissionOps locked. Rootly real-data integration locked. Composable rubrics locked. Unsloth + multi-turn GRPO training pipeline locked.
> **Hackathon**: OpenEnv India 2026 — submission deadline ≤ 15 hours from T+0.
> **Theme**: #2 — (Super) Long-Horizon Planning & Instruction Following.
> **Plan source of truth**: [`idea/Plan/github_issues.md`](./github_issues.md), [`idea/Plan/Architecture/*`](./Architecture/), [`idea/Plan/Demo/*`](./Demo/), [`idea/Plan/Submission/*`](./Submission/), [`idea/Plan/Project/DecisionLog.md`](./Project/DecisionLog.md), [`idea/Plan/Project/EvidenceIndex.md`](./Project/EvidenceIndex.md).
>
> **v3.0 patch summary**: Phase 14 collapses Phases 11–13 of v2.1 into a single MissionOps push driven by the `FlawsToProduction/` audit. Old Issues #1–#21 are superseded (closed/folded). New issues `#22 → #38` are owner-mapped 6/6/6 across Architect / TechLead / SDE; `#39` is the tracker that gates submission.

---

## 1. Decisions locked (v3.0) — see `Project/DecisionLog.md`

| #   | Decision                       | Answer                                                                                            | ADR    |
| --- | ------------------------------ | ------------------------------------------------------------------------------------------------- | ------ |
| 1   | Theme angle                    | MissionOps — long-horizon SRE missions with planning, memory, and recovery as first-class skills. | ADR-16 |
| 2   | Real-world data                | Rootly AI Labs `logs-dataset` vendored into `data/artifacts/` with Apache-2.0 NOTICE.             | ADR-17 |
| 3   | Reward decomposition           | 4 composable rubrics — Planning 0.20, Memory 0.20, Recovery 0.20, Terminal 0.40 — sum to 1.0.     | ADR-18 |
| 4   | Training pipeline              | Unsloth GRPO + multi-turn GRPO (mtGRPO) over the live env via TRL `environment_factory`.          | ADR-19 |
| 5   | Final score formula            | `task_score = outcome × efficiency`, `efficiency = max(0.4, 1 − steps_used/MAX_STEPS)` clipped.   | ADR-20 |
| 6   | Concurrency                    | `asyncio.Lock`, session TTL 900 s, slowapi rate-limit 60/min on `/step` + `/reset`.               | ADR-04 + Mistake-4 |
| 7   | Memory                         | Explicit `save_finding` / `recall_memory` + per-scenario step cutoff.                              | ADR-05/06 |
| 8   | Evidence gating                | `remediation.*` events score 0 until root cause is identified.                                     | ADR-13 |
| 9   | Benchmark surface              | `GET /benchmark` reads `docs/baseline_scores.md` (4-row score gap table).                          | ADR-14 |
| 10  | Review policy                  | Architect ↔ TechLead reciprocal review; SDE PRs reviewed by both leads via `auto-review.yml`.     | ADR-11 |

---

## 2. The pitch (60 seconds, MissionOps cut) — `Demo/Narrative.md`

> "Production incidents take 4–6 hours. Today's agents fail at long-horizon SRE work because their context fills with noise, they don't plan, and they don't recover from disturbances. Praxis MissionOps is an OpenEnv where the agent runs an 8-phase production failure with scattered instructions, hidden dependencies, and real Rootly logs — earning credit for planning, recovery, and memory through four composable rubrics, not just for fixing the final symptom. Our trained Qwen agent jumps from a 0.18 baseline to 0.74 — a 4.1× lift — and the rollout shows it actually re-plans when we inject a disturbance. That's MissionOps: long-horizon, process-aware, and grounded in real production data."

---

## 3. Architecture index (under `idea/Plan/Architecture/`)

| Doc                                                            | Purpose                                                                                              |
| -------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| [`APIContract.md`](./Architecture/APIContract.md)              | Endpoints, schemas, X-Session-Id, MissionOps fields, planning commands, `/metadata`, `/benchmark`.   |
| [`DataFlow.md`](./Architecture/DataFlow.md)                    | End-to-end sequences: reset, step, planning actions, reward composition, live training loop.        |
| [`ConcurrencyModel.md`](./Architecture/ConcurrencyModel.md)    | `asyncio.Lock`, session TTL, slowapi, OpenEnv parity flags.                                          |
| [`MemoryModel.md`](./Architecture/MemoryModel.md)              | `PraxisMemory`, save/recall, per-scenario cutoff %, MemoryRubric link.                               |
| [`ScenarioCatalog.md`](./Architecture/ScenarioCatalog.md)      | All scenarios; `cascading-platform-failure` rewritten as the MissionOps mega-mission.                |
| [`RewardPolicy.md`](./Architecture/RewardPolicy.md)            | Composable rubrics, weights, outcome × efficiency formula, audit checklist.                          |
| [`SessionLifecycle.md`](./Architecture/SessionLifecycle.md)    | Reset / step / done / TTL eviction state machine.                                                    |

---

## 4. Evidence index (full: `Project/EvidenceIndex.md` S1 → S40)

Anchors that drive Plan v3.0:

- **S2 / S3** — Judging weights 40/30/20/10; vCPU=2 / 8 GB; runtime < 20 min.
- **S26** — Theme #2 "beyond context memory limits" framing.
- **S30** — GRPO survey: process rewards > terminal rewards.
- **S33** — Rootly AI Labs `logs-dataset` (Apache-2.0).
- **S34** — SRE-skills-bench taxonomy for planning + recovery.
- **S35** — Unsloth GRPO + mtGRPO recipes.
- **S36** — UltraHorizon failure modes (planning, recovery, instruction adherence).
- **S37** → **S40** — `FlawsToProduction/` audit memos (Mistakes 1–7, MissionOps mandate, Rootly mandate, training pipeline mandate).

---

## 5. Phase 14 — MissionOps push (Plan v3.0)

> Phases 1–13 are sealed (audit findings folded into the issue body of `#22`). Phase 14 is one wave, three lanes, six waves of work on the wall clock. Issue ↔ wave mapping is the single source of truth for delivery.

### 5.1 Lanes

| Lane                              | Issues                       | Total |
| --------------------------------- | ---------------------------- | ----- |
| **Architect** (`@GunaPalanivel`)  | #22, #23, #24, #37, #38, #39 | 6     |
| **TechLead** (`@Gokul287`)        | #25, #26, #27, #31, #32, #33 | 6     |
| **SDE** (`@snehasneha56526-arch`) | #28, #29, #30, #34, #35, #36 | 6     |

### 5.2 Waves and deliverables

#### Wave 0 — Safety + correctness foundation (T+0 → T+1h)

- `#22` *Safety bundle*: replace `threading.Lock` → `asyncio.Lock`, add slowapi rate-limit (60/min on `/step` + `/reset`), uvicorn `CMD ["uvicorn",...,"--host","0.0.0.0","--port","7860"]`, raise success thresholds out of triviality (`server/reward.py` policy adjust).
- **Validation**: `pytest -q` 289+ green, `tests/test_concurrent_sessions.py` PASS, `tests/test_rate_limit.py` PASS, `openenv validate` PASS.

#### Wave 1 — Reward foundation (T+1h → T+2h)

- `#23` *Outcome × efficiency score*: implement `compute_task_score(outcome, steps_used, max_steps)` in `praxis_env/scoring.py`, expose in `/state.task_score`, fail tests if formula drifts.
- `#25` design phase started in parallel.

#### Wave 2 — Composable rubrics + planning skeleton (T+2h → T+4h)

- `#24` *Composable Rubrics*: refactor `server/reward.py` into `rubrics/{planning,memory,recovery,terminal}.py`; engine asserts weights sum to 1.0 ±1e-6.
- `#25` *MissionPlan + planning actions*: add `praxis_env/mission_plan.py`, wire `create_plan` / `revise_plan` / `checkpoint` / `submit_report` / `request_clarification` through `command_parser.py` and `praxis_environment.py`.

#### Wave 3 — MissionOps + manifest (T+4h → T+6h)

- `#26` *MissionScenario phases + scattered + recovery*: rewrite `praxis_env/scenarios/cascading_platform_failure.py` as 8-phase mega-mission with scattered instructions, hidden dependencies, and disturbance injection.
- `#29` *openenv.yaml + `/metadata`*: refresh manifest (rubric weights, data sources block) and `GET /metadata`.
- `#30` *3-row baseline scores*: produce `docs/baseline_scores.md` (random / no-memory / SRE-prompt) over 4 scenarios × 5 seeds.

#### Wave 4 — Real-data + memory-leak excerpts + tests (T+6h → T+8h)

- `#27` *ArtifactStore + Rootly vendoring*: implement `praxis_env/artifacts.py`, vendor sample under `data/artifacts/` with `LICENSE-3rd-party.md` + `NOTICE.md`.
- `#28` *memory-leak + Rootly excerpts*: inject runbook/log excerpts via `ArtifactStore` into the `memory-leak` scenario; reward credit only when content is recalled across the cutoff.
- `#34` *Test suite — rubrics + artifacts + mission*: add `tests/test_rubrics.py`, `tests/test_mission_scenario_phases.py`, `tests/test_artifacts.py`, `tests/test_planning_actions.py`, `tests/test_score_formula.py`.

#### Wave 5 — Trainer + receipts + benchmark (T+8h → T+11h)

- `#31` *`scripts/train_praxis_grpo.py`*: Unsloth + TRL `environment_factory` with multi-turn GRPO turn aggregator, parallel sessions, Trackio/WandB logging.
- `#35` *Determinism + runtime + resource receipts*: `tests/test_determinism.py` (5-seed reproducibility), `docs/runtime_receipt.md` (< 20 min on vCPU=2/8 GB), `docs/resource_receipt.md`.
- `#36` *`GET /benchmark`*: read `docs/baseline_scores.md`, return JSON; happy path + missing-file + extra-fields tests.

#### Wave 6 — Training run + rollout + Space (T+11h → T+13h)

- `#32` *Training run + curves + 4th baseline row*: capture `docs/loss_curve.png` + `docs/reward_curve.png`; append the trained-Qwen row to `docs/baseline_scores.md` (the 4-row gap table).
- `#33` *Before/after rollout — trophy moment*: `docs/rollout_before.md` + `docs/rollout_after.md` from real `/step` traces; same seed; show ≥ 4× lift on the MissionOps mega-mission.
- `#37` *HF Space + smoke + Dockerfile prod*: pin `requirements.txt`, ship Dockerfile (uvicorn CMD), deploy Space, `tests/smoke_test.py` green from cold start.

#### Wave 7 — README + demo + submission (T+13h → T+15h)

- `#38` *README + mini-blog + slide deck + video*: link block (Space `/health` `/metadata` `/benchmark`, training links, baseline scores, rollouts, evidence package); ≤ 2 min video.
- `#39` *Submission tracker* — flip the 20-item judge checklist green under each of the four weighted axes (40/30/20/10), then submit.

### 5.3 Critical path (must not slip)

```
#22 → #24 → #25 → #26 → #31 → #32 → #33 → #38 → #39
```

Detailed wall-clock and parallel lanes: [`dependency_graph.md`](./dependency_graph.md) §3–§4. T-task names per wave: [`task.md`](./task.md). Risk register: [`dependency_graph.md`](./dependency_graph.md) §5.

---

## 6. T+0 → T+15h schedule (single-screen view)

```
T+0:00  Wave 0  #22 Safety bundle .................................. 60 min  [Architect]
T+1:00  Wave 1  #23 Score formula ................................. 60 min  [Architect] || #25 design starts [TechLead]
T+2:00  Wave 2  #24 Rubrics ........................................ 90 min  [Architect]
                #25 MissionPlan + planning actions ................. 90 min  [TechLead]
T+4:00  Wave 3  #26 MissionScenario ............................... 120 min  [TechLead]
                #29 openenv.yaml + /metadata ....................... 60 min  [SDE]
                #30 baseline 3-row scores .......................... 90 min  [SDE]
T+6:00  Wave 4  #27 ArtifactStore + Rootly ......................... 90 min  [TechLead]
                #28 memory-leak + Rootly excerpts .................. 60 min  [SDE]
                #34 Test suite ..................................... 90 min  [SDE]
T+8:00  Wave 5  #31 train_praxis_grpo.py .......................... 120 min  [TechLead]
                #35 Determinism + runtime + resource ............... 60 min  [SDE]
                #36 GET /benchmark ................................. 45 min  [SDE]
T+11:00 Wave 6  #32 Training run + curves + 4th row ............... 120 min  [TechLead]
                #33 Before/after rollout — trophy .................. 60 min  [TechLead]
                #37 HF Space + smoke + Dockerfile prod ............. 90 min  [Architect]
T+13:00 Wave 7  #38 README + blog + slides + video ................ 120 min  [Architect]
                #39 Submission tracker (20-item checklist) ......... 45 min  [Architect]
T+15:00 Submit (frozen commit)
```

Buffer is built into each wave (~30 min each). If GPU credits do not arrive, drop `#32`/`#33` to `#30` 3-row gap (still covers ~70% of the reward axis per S30) and document the fallback in the README.

---

## 7. Submission gates (mirror `Submission/SubmissionChecklist.md`)

The 20-item judge checklist groups into 4 weighted axes:

- **Environment Innovation (40%)** — MissionOps mega-mission, real Rootly artifacts, scattered instructions, hidden dependencies, disturbance injection, planning actions, composable rubrics, evidence-gated remediation.
- **Storytelling & Presentation (30%)** — README MissionOps headline, 5-sentence pitch, ≤ 2 min video, slide deck, before/after rollout trophy, mini-blog.
- **Reward Improvement (20%)** — Outcome × efficiency formula, baseline 4-row gap table, training curves, per-rubric attribution chart.
- **Reward & Training Pipeline (10%)** — `scripts/train_praxis_grpo.py` checked in, training run logs linked, mtGRPO multi-turn credit assignment, runtime + resource receipts.

Auto-validation gates (must be green):

- [ ] `pytest -q` ≥ 350 green (rubrics, artifacts, mission, planning, score, determinism, smoke).
- [ ] `uv run openenv validate` PASS.
- [ ] HF Space `/health`, `/metadata`, `/benchmark` 200 from a cold private window.
- [ ] `docs/baseline_scores.md` has 4 rows (random, no-memory, SRE-prompt, trained-Qwen) and the lift is ≥ 4× on the MissionOps mission.
- [ ] Runtime < 20 min on vCPU=2 / 8 GB on `tests/smoke_test.py`.

---

## 8. PLAN READY

All 17 implementation issues + 1 tracker are evidence-grounded, file-pathed, ADR-tagged, and lane-balanced. Proceed to:

- [`github_issues.md`](./github_issues.md) for issue bodies (5-line acceptance template per issue).
- [`dependency_graph.md`](./dependency_graph.md) for the DAG, lanes, critical path, wave timeline, and risk register.
- [`task.md`](./task.md) for the T-task ledger mapped to issues `#22 → #39`.
- [`Submission/SubmissionChecklist.md`](./Submission/SubmissionChecklist.md) for the 20-item judge checklist + tracker body.
- [`issues_payload.md`](./issues_payload.md) for ready-to-paste `gh issue create` payloads.
