# Release Package — What Ships, Where It Lives

> The bill of materials for the final submission. Owned by Issue #38; updated
> as Issues #22–#37 land. Every item has a stable URL **before** the submission deadline.

---

## 1. The repo (frozen at submission commit)

- GitHub: `https://github.com/<org>/praxis` — pin a commit SHA in the submission form.
- HF Space mirror: `https://huggingface.co/spaces/<org>/praxis-env`.
- License: existing repo license (MIT preferred). Third-party attributions in `LICENSE-3rd-party` + `data/artifacts/NOTICE.md`.

Tree shape at submission (Plan v3.0 / MissionOps):

```
praxis/
├── README.md                       # rewritten (Issue #38) — opens with rollout_compare.png + demo.gif
├── Dockerfile                       # uvicorn CMD fix (Issue #22) + HF Space deploy (Issue #37)
├── openenv.yaml                     # 6 tasks + supports_concurrent_sessions + data_sources + rubrics block
├── pyproject.toml                   # adds slowapi (Issue #22), unsloth (Issue #31)
├── inference.py                     # MissionOps system prompt + score= field (Issues #22, #30, ADR-20)
├── train_praxis_grpo.py             # Unsloth + mtGRPO (Issue #31, ADR-19)
├── praxis_env/
│   ├── memory.py
│   ├── models.py                    # MissionOps fields (Issue #25)
│   ├── client.py
│   ├── artifacts.py                 # NEW (Issue #27, ADR-17) — ArtifactStore
│   ├── mission_plan.py              # NEW (Issue #25) — MissionPlan + planning actions
│   ├── __init__.py
│   ├── rubrics/                     # NEW (Issue #24, ADR-18)
│   │   ├── __init__.py
│   │   ├── base.py                  # Rubric ABC
│   │   ├── planning.py              # PlanningRubric (0.20)
│   │   ├── memory.py                # MemoryRubric   (0.20)
│   │   ├── recovery.py              # RecoveryRubric (0.20)
│   │   └── terminal.py              # TerminalRubric (0.40)
│   └── scenarios/
│       ├── base.py
│       ├── single_service_alert.py
│       ├── ambiguous_incident.py
│       ├── cascading_failure.py
│       ├── memory_leak_scenario.py  # +Rootly excerpts via ArtifactStore (Issue #27)
│       ├── mission_scenario.py      # NEW (Issue #25, #26) — replaces mega_incident.py
│       ├── procedural_incident.py   # shipped (Issue #8)
│       └── __init__.py              # registry update
├── server/
│   ├── app.py                       # async handlers + slowapi + GET /benchmark (Issue #22)
│   ├── praxis_environment.py        # mission phase machine + planning routing
│   ├── command_parser.py            # planning + reporting commands (Issue #25)
│   ├── reward.py                    # rubric-aware RewardEngine (Issue #24)
│   ├── session_manager.py           # asyncio.Lock + TTL eviction (Issue #22)
│   └── requirements.txt
├── tests/
│   ├── smoke_test.py                # full submission smoke (Issue #37)
│   ├── test_memory.py               # extended for per-scenario cutoff
│   ├── test_concurrent_sessions.py  # async client + rate-limit (Issue #22)
│   ├── test_artifacts.py            # NEW (Issue #27) — determinism of ArtifactStore.draw
│   ├── test_rubrics.py              # NEW (Issue #34) — orthogonality + score formula
│   ├── test_task5_mission.py        # NEW (Issues #25, #26) — phases, scattered, hidden deps, recovery
│   ├── test_task6_procedural.py     # shipped
│   └── (existing tests)
├── data/
│   └── artifacts/                   # NEW (Issue #27)
│       ├── README.md
│       ├── NOTICE.md                # Apache-2.0 attribution to Rootly AI Labs
│       ├── logs/*.jsonl
│       ├── runbooks/*.md
│       ├── tickets/*.md
│       └── notes/*.md
├── docs/
│   ├── baseline_scores.md           # 4-row table (Issues #30 + #32)
│   ├── reward_curve.png             # mtGRPO ≥50 steps (Issue #32)
│   ├── loss_curve.png               # mtGRPO loss (Issue #32)
│   ├── rollout_baseline.txt         # before-rollout (Issue #33)
│   ├── rollout_trained.txt          # after-rollout (Issue #33)
│   ├── rollout_compare.png          # side-by-side reward chart (Issue #33)
│   ├── demo.gif                     # cutoff banner moment (Issue #33)
│   ├── rubric_attribution.png       # optional (post-#32)
│   ├── determinism_receipt.txt
│   ├── runtime_receipt.txt
│   ├── training_links.md            # Trackio + WandB public URLs (Issue #32)
│   └── demo_trajectory.txt          # deterministic replay
├── LICENSE
├── LICENSE-3rd-party                # NEW — Rootly Apache-2.0 attribution (Issue #27)
└── idea/Plan/                       # planning docs (this folder)
```

---

## 2. External assets (URLs in README)

| Asset                   | Owner | URL pattern                                                     | Issue       |
| ----------------------- | ----- | --------------------------------------------------------------- | ----------- |
| HuggingFace Space       | Gokul | `https://huggingface.co/spaces/<org>/praxis-env`                | #37         |
| Trackio run / dashboard | Gokul | `https://trackio.io/<run-id>` or HF Trackio Space               | #32         |
| WandB **public** run    | Gokul | `https://wandb.ai/<team>/praxis-mission-ops/runs/<id>`          | #32         |
| Mini-blog (HF blog)     | Gokul | `https://huggingface.co/blog/<slug>` (title per S39)            | #38         |
| YouTube video (≤ 2 min) | Gokul | `https://youtu.be/<id>` (alt: HF Space video tab)               | #38         |
| Slide deck              | Gokul | Google Slides public URL OR PDF in repo                         | #38         |
| Rootly logs-dataset     | —     | `https://huggingface.co/datasets/Rootly-AI-Labs/logs-dataset`   | #27 (ADR-17)|
| arxiv references        | —     | AgeMem (S28), Context Bloat 2601.07190 (S29), GRPO survey (S30), UltraHorizon (S36) | n/a |

Constraint (S2): _"Please do not include big video files in your Env submission on HF Hub… Please use url as reference link to additional materials."_

---

## 3. README link block (top of file, judge-discoverable in 30 s)

```markdown
**Praxis MissionOps — Long-Horizon SRE Agent Training**
### Plan. Remember. Recover. Score = outcome × efficiency.

![rollout_compare](docs/rollout_compare.png)
![demo](docs/demo.gif)

- 🚀 Live env: https://huggingface.co/spaces/<org>/praxis-env
- 📈 Reward curve: docs/reward_curve.png · Loss curve: docs/loss_curve.png
- 📊 Score gap (4 rows): docs/baseline_scores.md
- 🎯 Trackio: <link> · WandB (public): <link> (docs/training_links.md)
- 🏆 Benchmark API: `GET /benchmark` (Issue #21, ADR-14) — model-vs-mean-score JSON
- 🎬 Mini-blog: https://huggingface.co/blog/<slug>
- 📑 Slides: <link>
- 🧠 Architecture: idea/Plan/Architecture/{DataFlow,RewardPolicy,ScenarioCatalog,APIContract,MemoryModel,ConcurrencyModel}.md
- 🔁 Train: train_praxis_grpo.py (Unsloth + mtGRPO via TRL environment_factory)
- 📚 Real production logs: Rootly AI Labs logs-dataset (Apache-2.0) — see data/artifacts/NOTICE.md

Cited frontier work: arxiv:AgeMem · arxiv:2601.07190 · GRPO survey · UltraHorizon · mtGRPO
```

This block is the first thing judges see. It is the storytelling 30% in 12 lines.

---

## 4. The 5 sentences in the mini-blog (and video script)

If we can't say all five in 90 seconds, the blog/video isn't shipping yet. Verbatim from `idea/Plan/Demo/Narrative.md` §1:

1. "Real production incidents take 4 to 6 hours and span runbooks, tickets, and on-call notes. Praxis MissionOps is the only environment where agents have to plan, remember, and recover across the full mission — not just answer one alert."
2. "Here is a baseline Qwen-7B agent. It wanders, queries logs after the context window collapses, never plans, and gets a final score of 0.04."
3. "Here is the same model after one mtGRPO training run on Praxis. It calls `create_plan` early, saves three findings before the cutoff, recovers from a deploy disturbance, submits a consistent post-incident report, and scores 0.31 — a 7.7× lift."
4. "Four composable rubrics — Planning, Memory, Recovery, Terminal — score the trajectory. Real Rootly production logs feed the artifacts. Outcome × efficiency stops the agent reward-farming."
5. "Anthropic's next Opus could literally train on this. Everything is in the README — Trackio, WandB, the rollouts, and the HF Space."

---

## 5. Submission day checklist

- [ ] `git tag praxis-submit-vN` and push.
- [ ] HF Space rebuilt against the tagged commit.
- [ ] `tests/smoke_test.py` green from a clean clone.
- [ ] All `docs/*` artefacts present and committed.
- [ ] All external URLs in `README.md` resolve from a private window (no auth).
- [ ] WandB run is public; Trackio run accessible.
- [ ] `data/artifacts/NOTICE.md` present.
- [ ] Slack the team the submission form preview before clicking submit.
- [ ] Submit.

---

## 6. Post-submit guardrails

Per S2: _"Changes or commits after the submission deadline will not be considered."_ So:

- **Do not** push to `main` after submit unless coordinating with the panel.
- **Do** keep monitoring the HF Space — if it cold-starts during agentic eval, no judge will retry.
- **Do** keep Trackio + WandB runs public until awards are announced.
