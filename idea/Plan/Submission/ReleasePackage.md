# Release Package — What Ships, Where It Lives

> The bill of materials for the final submission. Owned by Issue #20; updated
> as Issues #18, #19, #11, #12 land. Every item has a stable URL **before**
> the submission deadline.

---

## 1. The repo (frozen at submission commit)

- GitHub: `https://github.com/<org>/praxis` — pin a commit SHA in the submission form.
- HF Space mirror: `https://huggingface.co/spaces/<org>/praxis-env`.
- License: existing repo license (MIT preferred).

Tree shape at submission:

```
praxis/
├── README.md                       # rewritten (Issue #19)
├── Dockerfile                       # updated for memory module (Issue #18)
├── openenv.yaml                     # new tasks + supports_concurrent_sessions (Issue #9)
├── pyproject.toml
├── inference.py                     # SRE prompt (Issue #10)
├── train_praxis_grpo.py             # NEW (Issue #11)
├── praxis_env/
│   ├── memory.py                    # NEW (Issue #3)
│   ├── models.py                    # extended (Issue #2)
│   ├── client.py
│   ├── __init__.py
│   └── scenarios/
│       ├── base.py
│       ├── single_service_alert.py
│       ├── ambiguous_incident.py
│       ├── cascading_failure.py
│       ├── memory_leak_scenario.py
│       ├── mega_incident.py         # NEW (Issue #7)
│       ├── procedural_incident.py   # NEW (Issue #8)
│       └── __init__.py              # registry update (Issue #9)
├── server/
│   ├── app.py                       # SessionManager (Issue #1)
│   ├── praxis_environment.py        # memory hook (Issue #6)
│   ├── command_parser.py            # save/recall (Issue #4)
│   ├── reward.py                    # memory events (Issue #5)
│   └── requirements.txt
├── tests/
│   ├── smoke_test.py                # moved from mock_validator.py (Issue #16)
│   ├── test_memory.py               # NEW (Issue #13)
│   ├── test_concurrent_sessions.py  # NEW (Issue #15)
│   ├── test_task5_mega_incident.py  # NEW (Issue #14)
│   ├── test_task6_procedural.py     # NEW (Issue #14)
│   └── (existing tests)
├── docs/
│   ├── baseline_scores.md           # 3-row score gap (Issue #10)
│   ├── reward_curve.png             # GRPO 50-step curve (Issue #12)
│   ├── memory_reward_attribution.png  # optional (Issue #11)
│   ├── determinism_receipt.txt
│   ├── runtime_receipt.txt
│   ├── demo_trajectory.txt          # deterministic replay (Issue #20)
│   └── demo.gif                     # cutoff banner moment (Issue #20)
└── idea/Plan/                       # planning docs (this folder)
```

---

## 2. External assets (URLs in README)

| Asset                   | Owner | URL pattern                                                     | Issue   |
| ----------------------- | ----- | --------------------------------------------------------------- | ------- |
| HuggingFace Space       | Gokul | `https://huggingface.co/spaces/<org>/praxis-env`                | #18     |
| Trackio run / dashboard | Gokul | `https://trackio.io/<run-id>` or HF Trackio Space               | #11/#12 |
| Mini-blog (HF blog)     | Gokul | `https://huggingface.co/blog/<slug>`                            | #20     |
| YouTube video (≤ 2 min) | Gokul | `https://youtu.be/<id>` (alt: HF Space video tab)               | #20     |
| Slide deck              | Gokul | Google Slides public URL OR PDF in repo                         | #20     |
| arxiv references        | —     | AgeMem (S28), Context Bloat 2601.07190 (S29), GRPO survey (S30) | n/a     |

Constraint (S2): _"Please do not include big video files in your Env submission on HF Hub… Please use url as reference link to additional materials."_

---

## 3. README link block (top of file, judge-discoverable in 30 s)

```markdown
**Praxis: Long-Horizon SRE Agent Training — where plans span more steps than context windows**

- 🚀 Live env: https://huggingface.co/spaces/<org>/praxis-env
- 📈 Reward curve: docs/reward_curve.png · Trackio: <link>
- 📊 Score gap: docs/baseline_scores.md
- 🏆 Benchmark API: `GET /benchmark` (Issue #21, ADR-14) — live model-vs-mean-score table, parsed from `docs/baseline_scores.md`
- 🎬 60-second demo (cutoff at step 30): <youtube link>
- 📝 Mini-blog: https://huggingface.co/blog/<slug>
- 📑 Slides: <link>
- 🧠 Memory design: idea/Plan/Architecture/MemoryModel.md
- 🔁 Train: train_praxis_grpo.py (TRL environment_factory)

Cited frontier work: arxiv:AgeMem · arxiv:2601.07190 · GRPO survey
```

This block is the first thing judges see. It is the storytelling 30% in 8 lines.

---

## 4. The 5 sentences in the mini-blog (or video script)

If we can't say all five in 90 seconds, the blog/video isn't shipping yet:

1. "Production incidents take 4–6 hours; current AI agents fail at step 30 from context bloat."
2. "Praxis exposes `save_finding` and `recall_memory` as agent-callable tools — the agent decides what to remember."
3. "After step 30 the full log is removed from the observation; only what the agent saved survives."
4. "We reward the agent for thinking correctly through the whole trajectory, not just the final step — process-aware reward."
5. "Trains end-to-end with TRL's `GRPOTrainer.environment_factory`; ∞ tasks via the procedural seed; ready for Anthropic's next Opus."

---

## 5. Submission day checklist

- [ ] `git tag praxis-submit-vN` and push.
- [ ] HF Space rebuilt against the tagged commit.
- [ ] Smoke script (S `SubmissionChecklist.md` §4) green.
- [ ] All `docs/*` artefacts present and committed.
- [ ] All external URLs in `README.md` resolve from a private window (no auth).
- [ ] Slack the team the submission form preview before clicking submit.
- [ ] Submit.

---

## 6. Post-submit guardrails

Per S2: _"Changes or commits after the submission deadline will not be considered."_ So:

- **Do not** push to `main` after submit unless coordinating with the panel.
- **Do** keep monitoring the HF Space — if it cold-starts during agentic eval, no judge will retry.
- **Do** keep the Trackio run public until awards are announced.
