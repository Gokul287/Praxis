# Submission Checklist — Phase 1 Auto-Validation + Judge 20-Item Checklist

> Two parts: hard auto-validation gates (DQ if any fail) and the user's 20-item
> judge checklist mapped 1-to-1 to the 4 weighted axes (40 / 30 / 20 / 10).
>
> Sources: `idea/PROBLEM STATEMENT/How Judging works.md` (S3), the External
> Themes & Judging Criteria (S2), `FlawsToProduction/Verdict.md` (S38),
> `FlawsToProduction/The Situation First.md` (S39), and the user's verbatim
> Final-Issue checklist (S40).

---

## 1. Hard gates (DQ if any fail)

- [ ] **HF Space deploys** — `/health` returns `{"status": "healthy"}`.
- [ ] **`openenv validate` passes** — `uv run openenv validate` exits 0 on the submitted commit.
- [ ] **Dockerfile builds** — `docker build .` succeeds; `CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]`.
- [ ] **`inference.py` reproduces** — runs end-to-end and emits valid `[START]/[STEP]/[END]` lines with `score=` field (ADR-20).
- [ ] **3+ tasks with graders** — Praxis ships **6**: `single-service-alert`, `ambiguous-incident`, `cascading-failure`, `memory-leak`, `cascading-platform-failure` (MissionOps), `procedural-incident`. Each grader returns rewards in the open `(0.0, 1.0)` interval; `compute_task_score` uses outcome × efficiency.
- [ ] **Graders are NOT constant** — `tests/test_scenarios.py` + `tests/test_artifacts.py` + `tests/test_rubrics.py` determinism + variance suite passes.
- [ ] **Runtime < 20 min** — `inference.py` for all 6 tasks totals under 20 min on `vCPU=2 / 8 GB`.
- [ ] **Mandatory env vars wired** — `API_BASE_URL`, `MODEL_NAME`, `HF_TOKEN` (S31).
- [ ] **OpenAI client used for LLM calls** — verified by `tests/test_inference.py`.
- [ ] **Stdout contract preserved** — `[START]/[STEP]/[END]` exactly per S3.
- [ ] **`inference.py` lives at repo root** — required by S31.

---

## 2. The 20-item judge checklist (Final tracker Issue #39 — mapped to 4 weighted axes)

This is the **verbatim** content for the body of Issue #39. Paste this into GitHub as one issue when the team is ready to file the tracker.

### Axis A — Environment Innovation (40%)

> _"Could a researcher write a paper about training on this?"_ (S2)

- [ ] **#1.** **MissionOps long-horizon environment** — `cascading-platform-failure` ships as 80–150 turn mission with 8 phases (Intake / Exploration / Planning / Execution / Disturbance / Recovery / Completion / Reflection). Issue #25, ADR-16. Spec: `idea/Plan/Architecture/ScenarioCatalog.md` §3.
- [ ] **#2.** **Real Rootly production logs as mission artifacts** — `praxis_env/artifacts.py::ArtifactStore` injects vendored Apache-2.0 Rootly `logs-dataset` excerpts as runbooks, tickets, notes, and log lines. Issue #27, ADR-17. NOTICE.md committed at `data/artifacts/NOTICE.md` (S33).
- [ ] **#3.** **Scattered instructions across artifacts** — root-cause hints split across `runbook` / `ticket` / `note` / `log` artifact kinds; agent never gets a single briefing. `ScenarioCatalog.md` §3.2 + `Verdict.md` "scattered instruction following beyond context limits".
- [ ] **#4.** **Hidden dependencies + Disturbance/Recovery phase** — RC #2 blocks RC #1 remediation; deploy disturbance at step ~100 invalidates plan and forces `revise_plan`. `RecoveryRubric` measures detection within ≤3 steps. `ScenarioCatalog.md` §3.3.
- [ ] **#5.** **Hard memory cutoff with explicit memory actions** — `save_finding`, `recall_memory` as first-class agent commands; full investigation log deleted at `CONTEXT_CUTOFF_STEP`. Mission cutoff = 30/150 (20%). Issue #25 builds on shipped Issue #3. `MemoryModel.md` §3 + §8.
- [ ] **#6.** **Composable Rubrics** — `PlanningRubric` 0.20 / `MemoryRubric` 0.20 / `RecoveryRubric` 0.20 / `TerminalRubric` 0.40. `RewardEngine` weights sum to 1.0; orthogonality asserted in `tests/test_rubrics.py`. Issue #24, ADR-18. (Verbatim hackathon-criterion line: _"composable rubrics > monolithic scoring"_.)
- [ ] **#7.** **Procedural mission generation** — `procedural-incident` shipped with seeded determinism + 3 difficulties; `(seed, difficulty)` → byte-identical scenario. Existing Issue #8 + ADR-07; tests `tests/test_task6_procedural.py`.

### Axis B — Storytelling & Presentation (30%)

> _"Make plots readable. Make the story land in 90 seconds."_ (S2)

- [ ] **#8.** **Before/after rollout deliverables** — `docs/rollout_baseline.txt`, `docs/rollout_trained.txt`, `docs/rollout_compare.png`, `docs/demo.gif` committed (Issue #33). Same `mission_id` and seed; baseline ≈ 0.04, trained ≈ 0.31 (≥ 5× lift).
- [ ] **#9.** **5-sentence pitch lands in ≤ 50 seconds** — `idea/Plan/Demo/Narrative.md` §1; rehearsed; speaker-notes-ready.
- [ ] **#10.** **README opens with the visual** — first content block of `README.md` is `docs/rollout_compare.png` followed by `docs/demo.gif`, then the 5-sentence pitch. No paragraphs above the fold. Issue #38.
- [ ] **#11.** **Mini-blog OR YouTube ≤ 2 min** — public link in README + `Submission/ReleasePackage.md` §2. Title: _"Training LLMs to Remember: Praxis MissionOps and Long-Horizon Operational Reasoning"_ (S39).
- [ ] **#12.** **Slide deck (5 slides max)** — public Google Slides or PDF in repo. Slides per `idea/Plan/Demo/ScreenplayScript.md` §4.
- [ ] **#13.** **Q&A drill prepared** — verbatim answers to the 5 likely Meta-engineer questions in `Narrative.md` §6 + `The Situation First.md` "Hour 40–48".

### Axis C — Reward Improvement (20%)

> _"Show training works. Process rewards beat terminal rewards."_ (S30)

- [ ] **#14.** **4-row score gap table** — `docs/baseline_scores.md` rows: random / no-prompt / SRE-prompt / mtGRPO-trained. ≥ 5× lift baseline → trained. Issues #30 + #32.
- [ ] **#15.** **Reward + loss curves** — `docs/reward_curve.png` + `docs/loss_curve.png` from ≥ 50 mtGRPO steps. Both linked inline in README. Issue #32.
- [ ] **#16.** **Public Trackio + WandB run URLs** — `docs/training_links.md` lists both; both public from a private window. Issue #32.
- [ ] **#17.** **Outcome × efficiency score formula** — `compute_task_score = outcome_quality × (1 - steps/max_steps)` with `outcome_quality = 0` unless `_incident_resolved AND _root_cause_identified`. ADR-20, Issue #23. Old avg-reward formula removed.

### Axis D — Reward & Training Pipeline (10%)

> _"Must be PyTorch-native. Anthropic's next Opus could train on it."_ (S1)

- [ ] **#18.** **`train_praxis_grpo.py` with Unsloth + mtGRPO** — turn-level credit assignment, ~2.5× throughput, stable on sparse reward. Issue #31, ADR-19. PEP 723 dependency block; runs on Colab T4/A10G.
- [ ] **#19.** **TRL `environment_factory` snippet works** — 10–15 line snippet in README copy-paste-runs against the deployed HF Space. Issue #38.
- [ ] **#20.** **HF Space deploys + `openenv validate` + `inference.py` reproduces** — full submission-day smoke (`tests/smoke_test.py`) runs green from a clean clone. Issue #37.

### Acceptance — when all 20 boxes ticked

This issue is the only one that closes after submission. It is the visible signal that we hit every weighted axis judges read against.

---

## 3. Required deliverables (S2 minimum submission)

- [ ] OpenEnv (latest release) used — `pyproject.toml` pins it.
- [ ] Training script using TRL or Unsloth — `train_praxis_grpo.py` (Issue #31).
- [ ] Evidence of training — reward curve OR score gap table (Issues #30, #32).
- [ ] Mini-blog on HuggingFace **OR** YouTube video < 2 minutes — Issue #38.
- [ ] HuggingFace Space (tagged `openenv`) — Issue #37.
- [ ] README that motivates the problem, explains the env, shows results — Issue #38.
- [ ] All additional materials (video, blog, slides) **linked from README** — Issue #38.
- [ ] No big video files in the HF Hub repo — use URL references only (S2).

---

## 4. README must contain (Issue #38 owns)

- [ ] One-line MissionOps tagline + the before/after visual above the fold.
- [ ] Problem statement (2 sentences from `Narrative.md` §1).
- [ ] Architecture diagram (mermaid — same one in [`DataFlow.md`](../Architecture/DataFlow.md) §1).
- [ ] Action / observation / state schemas (link to [`APIContract.md`](../Architecture/APIContract.md)).
- [ ] Task table (6 rows from [`ScenarioCatalog.md`](../Architecture/ScenarioCatalog.md) §1).
- [ ] Memory + Planning + Recovery section (link to [`MemoryModel.md`](../Architecture/MemoryModel.md), [`RewardPolicy.md`](../Architecture/RewardPolicy.md) §8).
- [ ] 4-row score gap table inline.
- [ ] Reward curve + loss curve images inline.
- [ ] Before/after rollout image inline.
- [ ] Composable-rubric weights table inline.
- [ ] TRL `environment_factory` snippet (10–15 lines).
- [ ] arxiv + Rootly citations (S28, S29, S30, S33, S35, S36).
- [ ] Links: HF Space · Trackio · WandB · mini-blog/video · slide deck · `GET /benchmark`.
- [ ] Quick-start: 5 commands from clone → running.
- [ ] License + Rootly attribution (NOTICE.md link).

---

## 5. Pre-submission validation script

Run from a clean clone before clicking submit:

```bash
# 1. Validate
uv sync
uv run openenv validate

# 2. Tests
pytest -q
# Expect: > 289 passed (existing) + memory + rubrics + concurrency + artifact suites green.

# 3. Smoke
python -m uvicorn server.app:app --host 0.0.0.0 --port 7860 &
sleep 3
curl -s http://localhost:7860/health | grep healthy
curl -s http://localhost:7860/metadata | python -m json.tool | grep -E "rubrics|data_sources"
curl -s -X POST http://localhost:7860/reset \
     -H "Content-Type: application/json" \
     -d '{"task_name":"cascading-platform-failure","seed":2026}' | python -m json.tool
# Capture session_id, then exercise /step (with create_plan / save_finding) and /state with X-Session-Id header.

# 4. Inference + score field present
API_BASE_URL=... MODEL_NAME=... HF_TOKEN=... python inference.py | grep "score="

# 5. Docker
docker build -t praxis-env:submit .
docker run --rm -p 7860:7860 praxis-env:submit &
sleep 5
curl -s http://localhost:7860/health
```

All five steps must produce green output. Issue #37 packages this into `tests/smoke_test.py` so CI runs it.

---

## 6. Last-mile submission form

- [ ] HF Space URL: `https://huggingface.co/spaces/<org>/praxis-env`
- [ ] GitHub repo URL with permanent commit hash, not just `main`.
- [ ] One mini-blog OR video link.
- [ ] Optional: slides URL.
- [ ] Team members: `@Gokul287`, `@GunaPalanivel`, `@snehasneha56526-arch`.

Per S2: _"Please make sure that the URL link of your environment is submitted as judges will pull the environment from the URL to evaluate it. Changes or commits after the submission deadline will not be considered."_ → freeze the commit hash; do not push fixes after submit.

---

## 7. Common failure modes we've already mitigated

| Risk                                | Mitigation in this repo                                                                                            |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Reward not bounded                  | `clamp_reward` in `server/reward.py` (S11/S12).                                                                    |
| Grader non-deterministic            | No randomness; `ArtifactStore.draw` is seeded (Issue #27).                                                         |
| Docker build fails on HF            | Local `docker build` step in §5 mandatory before submit; Issue #22 fixes uvicorn CMD.                              |
| Stdout format wrong                 | `tests/test_inference.py` enforces `[START]/[STEP]/[END]` + `score=` (S31, ADR-20).                                |
| Concurrency corrupts state          | `asyncio.Lock` in `SessionManager` + `SUPPORTS_CONCURRENT_SESSIONS=true` (Issue #22, ADR-04, S14).                 |
| Reward farming via avg formula      | Outcome × efficiency formula (ADR-20, Issue #23) gates score on `_incident_resolved AND _root_cause_identified`.   |
| Memory tools never used by agent    | `save_finding`/`recall_memory`/`create_plan`/`revise_plan` advertised in `available_commands` every step.          |
| Always-same grader                  | Determinism receipt + per-task variance test in `tests/test_scenarios.py` + `tests/test_rubrics.py` (Issue #34).   |
| Real-log license violation          | `data/artifacts/NOTICE.md` Apache-2.0 attribution; `LICENSE-3rd-party` updated (Issue #27).                        |

---

## 8. Ready-to-paste body for tracker Issue #39

Title: `Tracker — Praxis MissionOps Submission (20-item judge checklist)`

Labels: `tracker`, `submission`, `priority:p0`.

> Paste the markdown block below verbatim as the body of the tracker issue
> when the team is ready to file it. It is identical to §2 above with the
> internal plan-doc cross-references swapped for short on-issue notes so the
> issue stays self-contained on GitHub. Do not edit this block in-place
> after the tracker is filed; track changes via comments on the issue.

```markdown
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
```

