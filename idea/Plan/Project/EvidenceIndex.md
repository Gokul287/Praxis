# Evidence Index — Source IDs cited from every issue

> Every non-trivial claim in `idea/Plan/**` and the 20 issues references one of
> these IDs. New evidence appended at the bottom; never renumber.

---

## Sources

| ID  | Document / Path                                                                                                    | Why it matters                                                                                                                                                      |
| --- | ------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| S1  | Meta engineer venue statement (`idea/Task.md` line 100)                                                            | "Must be usable in PyTorch right away"; "Anthropic's next Opus could train on it". Justifies TRL `environment_factory` first-class support and HF Space deployment. |
| S2  | External Themes & Judging Criteria (`idea/Data/[External] Apr ‘26 OpenEnv Hackathon Themes & Judging Criteria.md`) | 40% Innovation / 30% Storytelling / 20% Rewards / 10% Pipeline weights. The four-criterion rubric every issue is judged against.                                    |
| S3  | How Judging Works (`idea/PROBLEM STATEMENT/How Judging works.md`)                                                  | Phase 1 auto-validation gates, infra restrictions (vCPU=2/8GB, <20 min), DQ rules.                                                                                  |
| S4  | Detailed Requirements (`idea/PROBLEM STATEMENT/Detailed Requirements.md`)                                          | Functional/non-functional requirements: ≥3 tasks, deterministic graders, reward in [0.0, 1.0], HF Space, Dockerfile.                                                |
| S5  | Evaluation Criteria (`idea/PROBLEM STATEMENT/Evaluation Criteria.md`)                                              | Round-1 rubric (real-world utility 30%, task quality 25%, env design 20%, code 15%, creativity 10%) — kept as "general quality bar".                                |
| S6  | The Task (`idea/PROBLEM STATEMENT/The Task.md`)                                                                    | Original Round-1 problem statement; Praxis is the answer to it.                                                                                                     |
| S7  | FromClaude research (`idea/Data/Research/FromClaude.md`)                                                           | SF winners, Llama 4 pipeline, SWE-RL, capability gaps survey.                                                                                                       |
| S8  | FromPerplexity research (`idea/Data/Research/FromPreplexity.md`)                                                   | Competitor analysis, Anthropic faithfulness needs.                                                                                                                  |
| S9  | `server/app.py` line 46 — `env = PraxisEnvironment()`                                                              | The current global singleton — a hard concurrency blocker (Issue #1).                                                                                               |
| S10 | `praxis_env/models.py`                                                                                             | Existing Pydantic action/observation/state models extended in Issue #2.                                                                                             |
| S11 | `praxis_env/scenarios/base.py`                                                                                     | `BaseScenario` ABC + `clamp_reward` open-interval contract.                                                                                                         |
| S12 | `server/reward.py`                                                                                                 | `RewardEngine`, `RewardPolicy`, `DEFAULT_REWARD_POLICIES`, clamp helpers.                                                                                           |
| S13 | `server/command_parser.py`                                                                                         | `KNOWN_ACTIONS` and the `key=value` grammar extended in Issue #4.                                                                                                   |
| S14 | `OpenEnv/src/openenv/core/env_server/interfaces.py`                                                                | `Environment` ABC, `SUPPORTS_CONCURRENT_SESSIONS`, `Rubric`, `Transform`.                                                                                           |
| S15 | `OpenEnv/src/openenv/core/env_server/types.py`                                                                     | Pydantic base models with `extra="forbid"`, session/capacity types.                                                                                                 |
| S16 | `OpenEnv/src/openenv/cli/templates/openenv_env/server/app.py`                                                      | `create_app(EnvCls, ActCls, ObsCls, env_name=..., max_concurrent_envs=N)` factory.                                                                                  |
| S17 | TRL docs (`huggingface-llm-trainer` skill referenced in `idea/Plan/implementation_plan.md`)                        | `GRPOTrainer.environment_factory` requirement; `num_generations`; PEP 723 UV scripts for HF Jobs.                                                                   |
| S18 | OpenEnv docs (`OpenEnv/docs/source/getting_started/environment-builder.md` and tutorials)                          | Reference for openenv.yaml manifest fields, `openenv validate`, `openenv push`.                                                                                     |
| S19 | Llama 4 blog (cited in `idea/Plan/implementation_plan.md` Evidence Index)                                          | Hard prompt curriculum, dynamic filtering — informs procedural difficulty mix.                                                                                      |
| S20 | OpenEnv `core/rubrics/` package                                                                                    | Composable rubric pattern; informs how memory bonuses are added without monolithic scoring.                                                                         |
| S21 | `server/praxis_environment.py`                                                                                     | Reset/step/state implementation; the integration point for `PraxisMemory`.                                                                                          |
| S22 | SUPO arxiv paper (cited in `idea/Plan/implementation_plan.md` Evidence Index)                                      | Summarisation-augmented policy optimisation — counterpoint to explicit memory; we explicitly _avoid_ passive summarisation.                                         |
| S23 | Existing Praxis `idea/Architecture/scenario_design.md`                                                             | Authoritative spec for the 4 shipping scenarios; new scenarios extend the same data shape.                                                                          |
| S24 | Existing Praxis `idea/Architecture/data_model.md`                                                                  | Existing action/observation/state and command grammar — the contract the new schema is a delta on.                                                                  |
| S25 | Existing Praxis `idea/Plan/task.md` and `idea/Plan/implementation_plan.md`                                         | Prior decisions T01–T14; consolidated into the 20 issues.                                                                                                           |
| S26 | Theme #2 description (`idea/Data/[External] ...`, S2)                                                              | "Beyond context memory limits", sparse/delayed rewards — the moat is grounded here.                                                                                 |
| S27 | Decision summary in `idea/Task.md` lines 119–171                                                                   | Decisions 1–3 (scope = mega+memory+procedural; compute = inference-first; pitch = merged memory + process).                                                         |
| S28 | arxiv AgeMem (cited in `idea/Task.md` line 130)                                                                    | "Memory operations as tool-based actions, GRPO-compatible". The single most-cited primary source.                                                                   |
| S29 | arxiv 2601.07190 (cited in `idea/Task.md` line 150)                                                                | "Context Bloat… passive summarisation fails" — the problem statement.                                                                                               |
| S30 | GRPO survey (cited in `idea/Task.md` line 142)                                                                     | "Process rewards are more informative than terminal rewards" — justifies inference-tier evidence as 70%-equivalent of training curves.                              |
| S31 | `idea/PROBLEM STATEMENT/How Judging works.md` — "Mandatory Additional Instructions"                                | `API_BASE_URL`, `MODEL_NAME`, `HF_TOKEN`; OpenAI client requirement; `inference.py` at root.                                                                        |
| S32 | OpenEnv `docs/guides/connecting.md` and `docs/guides/rl-integration.md`                                            | TRL connection patterns and reward integration.                                                                                                                     |

---

## How to cite

In an issue body or doc:

```
- See `praxis_env/scenarios/base.py` (S11) for the `BaseScenario` contract.
- The 40/30/20/10 weights come from S2.
- `SUPPORTS_CONCURRENT_SESSIONS` mirrors S14.
```

In a code comment:

```python
# mirrors openenv.core.env_server.interfaces.Environment.SUPPORTS_CONCURRENT_SESSIONS  (S14)
```

---

## Conflicts to flag if they appear

- If `idea/Architecture/data_model.md` (S24) says rewards are `[0.0, 1.0]` but `server/reward.py` (S12) clamps to `[0.01, 0.99]`, the code wins. We surface the open-interval choice in [`APIContract.md`](../Architecture/APIContract.md) §6 so judges aren't surprised.
- If `idea/Task.md` (S27) and an issue body diverge, this index is the tiebreaker; rewrite the issue.
