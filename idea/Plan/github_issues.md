# GitHub Issues — Praxis Theme #2 (21 issues, format-locked)

> Single source of truth for the team. The review policy lives in
> [`Project/DecisionLog.md`](./Project/DecisionLog.md) ADR-11 and is enforced
> by `.github/workflows/auto-review.yml` + `.github/CODEOWNERS`:
>
> - Architect (`@GunaPalanivel`) PRs → reviewed by `@Gokul287`.
> - TechLead (`@Gokul287`) PRs → reviewed by `@GunaPalanivel`.
> - SDE (`@snehasneha56526-arch`) PRs → reviewed by **both leads + auto PR review**. Sneha is never a reviewer.
>
> Assignees and reviewers live in GitHub's PR sidebar (auto-set by the
> workflow + CODEOWNERS); we do **not** duplicate them in the issue body.
> The Index table at the bottom of this file shows lane assignment for
> planning purposes. Source IDs (Sx) map to
> [`Project/EvidenceIndex.md`](./Project/EvidenceIndex.md).

---

# Issue #1 — [P0] Session-based PraxisEnvironment + X-Session-Id

**Labels**: `P0`, `blocker`, `server`, `concurrency`

## Context

`server/app.py` line 46 keeps a module-level `env = PraxisEnvironment()` singleton (S9). TRL `GRPOTrainer` rolls out N parallel completions per prompt (`num_generations=8` typical, S17), and the OpenEnv runtime validator opens multiple sessions (S14). With a singleton, two concurrent `/step` calls clobber `_step_count` → non-deterministic rewards → judging DQ (S3). This issue replaces the singleton with a `SessionManager` that mirrors `OpenEnv.create_app(..., max_concurrent_envs=N)` (S16) and the `SUPPORTS_CONCURRENT_SESSIONS` flag (S14).

## What to do

1. Add `server/session_manager.py` with `SessionManager`: `OrderedDict[str, Session]`, `threading.Lock`, LRU `popitem(last=False)` eviction, `max_sessions = int(os.getenv("PRAXIS_MAX_SESSIONS", "128"))`. Sketch in [`Architecture/ConcurrencyModel.md`](./Architecture/ConcurrencyModel.md) §4.
2. Rewrite `server/app.py`:
   - Drop the module-level `env = PraxisEnvironment()` (`server/app.py:46`).
   - Build `manager = SessionManager()` instead.
   - `POST /reset` → `manager.allocate(task_name, seed)` → returns `{"session_id": <uuid4>, "observation": ..., **flat_obs_dict}`.
   - `POST /step` → read `request.headers.get("x-session-id")`, call `manager.get(sid)`. Missing/unknown id → 400. Soft fallback to most-recently-touched session is allowed during deprecation but logs `WARN`.
   - `GET /state` → same routing as `/step`.
   - `/health`, `/tasks`, `/metadata`, `/schema`, `/mcp`, `/` keep working without a session.
3. Add `SUPPORTS_CONCURRENT_SESSIONS = True` and `REQUIRES_SINGLE_THREAD_EXECUTOR = False` class attrs on `PraxisEnvironment` (mirrors S14).
4. Add `# mirrors openenv.core.env_server.interfaces.Environment.SUPPORTS_CONCURRENT_SESSIONS  (S14)` comments where the flag is set.
5. Update `openenv.yaml`: add top-level `supports_concurrent_sessions: true` and `themes: [long-horizon-planning]`.

## Done when

- [ ] `server/app.py` no longer has a module-level `env = PraxisEnvironment()` (line 46 deleted/rewritten).
- [ ] `SessionManager` provides `allocate / get / touch / close` with the lock held on every mutation.
- [ ] `POST /reset` returns a fresh UUID4 `session_id` in the JSON body.
- [ ] `POST /step` and `GET /state` require `X-Session-Id`; absence returns HTTP 400 with `{"detail": "Missing X-Session-Id header"}`.
- [ ] `openenv.yaml` declares `supports_concurrent_sessions: true`.
- [ ] `pytest -q` still 289+ green; new tests added (or stubbed) in #15.
- [ ] `uv run openenv validate` PASS.

## Depends on

- _(none — this is the blocker)_

## Unblocks

- #2, #3, #6, #7, #8, #10, #15

## Acceptance criteria

- [ ] **APIContract**: field parity with `/reset`, `/step`, `/state` schemas in [`Architecture/APIContract.md`](./Architecture/APIContract.md) §3.
- [ ] **Determinism**: 8 parallel `/reset` calls (different tasks) return 8 distinct `session_id`s and produce identical reward vectors when re-run.
- [ ] **Reward bound**: scores stay in `[0.01, 0.99]` (`server/reward.py` clamp).
- [ ] **OpenEnv parity**: `PraxisEnvironment.SUPPORTS_CONCURRENT_SESSIONS = True` (S14); `openenv.yaml` mirrors.
- [ ] **Review**: `@Gokul287` approves before merge; PR description lists Assignee + Reviewer per §4 of the plan.

## Plan docs to update (same PR as code — keep plan == reality)

- [ ] [`Architecture/APIContract.md`](./Architecture/APIContract.md) (note any deviation from §3).
- [ ] [`Architecture/ConcurrencyModel.md`](./Architecture/ConcurrencyModel.md) (mark §4 sketch as "shipped").
- [ ] [`Architecture/SessionLifecycle.md`](./Architecture/SessionLifecycle.md) (failure-mode rows).

## References

- `server/app.py:46` (S9)
- `OpenEnv/src/openenv/core/env_server/interfaces.py` (S14)
- `OpenEnv/src/openenv/cli/templates/openenv_env/server/app.py` (S16)
- [`Project/EvidenceIndex.md`](./Project/EvidenceIndex.md) S9, S14, S16

---

# Issue #2 — [P0] Pydantic memory-aware action/observation schema

**Labels**: `P0`, `models`, `schema`

## Context

`PraxisObservation` in `praxis_env/models.py` (S10) doesn't expose memory state, so the agent can't tell when the cutoff fires and judges can't see "memory_active" in the JSON. We extend the Pydantic models to carry the new fields without breaking field-parity for existing judges. Mirrors OpenEnv's `extra="forbid"` discipline (S15).

## What to do

1. Edit `praxis_env/models.py`:
   - `PraxisObservation` — add `memory_active: bool = False` and `saved_findings_count: int = 0`. Keep `model_config` `extra="forbid"`.
   - `PraxisState` — add `session_id: str = ""` and `memory_active: bool = False`.
   - `AVAILABLE_COMMANDS` — append `"save_finding key=<key> value=<finding>"`, `"recall_memory"`, `"recall_memory key=<key>"` (mirrors [`MemoryModel.md`](./Architecture/MemoryModel.md) §6).
2. Update `BaseScenario.get_observation()` and `BaseScenario.get_state()` to populate the new fields with safe defaults (memory hook will overwrite in #6).
3. Regenerate JSON schema sanity by hitting `/schema` in `tests/test_models.py` and asserting the new fields exist.

## Done when

- [ ] `PraxisObservation` has `memory_active: bool` and `saved_findings_count: int`.
- [ ] `PraxisState` has `session_id: str` and `memory_active: bool`.
- [ ] `AVAILABLE_COMMANDS` lists the three new memory commands.
- [ ] `tests/test_models.py` asserts the new fields and the `extra="forbid"` rejection of unknown fields.
- [ ] `pytest -q` green.

## Depends on

- #1

## Unblocks

- #4, #6

## Acceptance criteria

- [ ] **APIContract**: `PraxisObservation` / `PraxisState` field list matches [`Architecture/APIContract.md`](./Architecture/APIContract.md) §2.
- [ ] **Determinism**: Pydantic JSON schema output is byte-stable across runs (no datetime / random fields).
- [ ] **Reward bound**: no change to reward path; existing clamp invariants preserved.
- [ ] **OpenEnv parity**: `model_config = ConfigDict(extra="forbid", validate_assignment=True)` (S15).
- [ ] **Review**: `@Gokul287` approves; PR header carries §4 review line.

## Plan docs to update (same PR as code)

- [ ] [`Architecture/APIContract.md`](./Architecture/APIContract.md) (§2 schema if anything diverges).
- [ ] [`Architecture/MemoryModel.md`](./Architecture/MemoryModel.md) (§6 `AVAILABLE_COMMANDS` list).

## References

- `praxis_env/models.py` (S10)
- `OpenEnv/src/openenv/core/env_server/types.py` (S15)
- [`Project/EvidenceIndex.md`](./Project/EvidenceIndex.md) S10, S15

---

# Issue #3 — [P0] PraxisMemory module (save_finding / recall_memory / cutoff)

**Labels**: `P0`, `feature`, `memory`, `theme-2`

## Context

This is the **moat** (ADR-05, S26, S28, S29). Add an explicit, agent-controlled working-memory class with a context cutoff that flips the observation from raw log to a memory summary at step 30 by default.

## What to do

1. Create `praxis_env/memory.py` with the `PraxisMemory` dataclass exactly as specified in [`Architecture/MemoryModel.md`](./Architecture/MemoryModel.md) §1 + §3:
   ```python
   @dataclass
   class PraxisMemory:
       saved_findings: dict[str, str] = field(default_factory=dict)
       CONTEXT_CUTOFF_STEP: int = 30
       def save_finding(self, key, value) -> str: ...
       def recall_memory(self, key=None) -> str: ...
       def get_observation_context(self, full_log, step) -> str: ...
       def is_active(self, step) -> bool: ...
       def reset(self) -> None: ...
   ```
2. No I/O, no randomness, no timestamps. Pure state machine.
3. Export `PraxisMemory` from `praxis_env/__init__.py`.
4. Cite source in module docstring: `# Grounded in arxiv AgeMem (S28) + arxiv 2601.07190 Context Bloat (S29)`.

## Done when

- [ ] `praxis_env/memory.py` exists with the 5-method API.
- [ ] `is_active(step)` returns `step >= CONTEXT_CUTOFF_STEP`.
- [ ] `get_observation_context(history, step)` returns the cutoff banner exactly as in [`Architecture/MemoryModel.md`](./Architecture/MemoryModel.md) §3 once active.
- [ ] `reset()` clears `saved_findings`.
- [ ] `praxis_env/__init__.py` exports `PraxisMemory`.

## Depends on

- #1

## Unblocks

- #4, #5, #6, #13

## Acceptance criteria

- [ ] **APIContract**: text returned by `get_observation_context` fits inside `PraxisObservation.investigation_result: str`.
- [ ] **Determinism**: same `(history, step, saved_findings)` always produces the same output bytes.
- [ ] **Reward bound**: emits no rewards itself; bonuses are added in #5/#6.
- [ ] **OpenEnv parity**: stays Python-only; no FastAPI / Pydantic dependency in `memory.py`.
- [ ] **Review**: `@Gokul287` approves.

## Plan docs to update (same PR as code)

- [ ] [`Architecture/MemoryModel.md`](./Architecture/MemoryModel.md) (mark §1/§3 "shipped").
- [ ] [`Project/DecisionLog.md`](./Project/DecisionLog.md) ADR-05 cross-link.

## References

- `idea/Task.md` lines 161–171 (S27)
- arxiv AgeMem (S28), arxiv 2601.07190 (S29)
- [`Project/EvidenceIndex.md`](./Project/EvidenceIndex.md) S26, S27, S28, S29

---

# Issue #4 — [P0] command_parser KNOWN_ACTIONS + AVAILABLE_COMMANDS for memory

**Labels**: `P0`, `parser`, `memory`

## Context

`server/command_parser.py` (S13) advertises `KNOWN_ACTIONS` and uses a `key=value` grammar with a special-case for `escalate reason=<free text>`. We need analogous handling for `save_finding key=<k> value=<v>` so the value can include spaces, plus a no-arg / single-key form for `recall_memory`.

## What to do

1. Extend `KNOWN_ACTIONS` in `server/command_parser.py`:
   ```python
   KNOWN_ACTIONS = frozenset({
       ..., "save_finding", "recall_memory",
   })
   ```
2. Add a `save_finding` branch in `parse_command()` that mirrors the `escalate` pattern but extracts both `key=<k>` and the rest after `value=` as the finding (regex: `r"key=([^\s]+)\s+value=(.+)$"`). If the regex fails, set `params={}` and let the env's unknown-command handler reject it.
3. `recall_memory` parses with the standard `key=value` rule; `key` may be missing.
4. Ensure `AVAILABLE_COMMANDS` in `praxis_env/models.py` already lists the new commands (added in #2). If #2 hasn't merged, do it here too.
5. Add unit tests in `tests/test_command_parser.py` for: `save_finding key=db_pool value=exhausted at step 4`, `recall_memory`, `recall_memory key=db_pool`, and a bogus `save_finding` (no `value=`).

## Done when

- [ ] `KNOWN_ACTIONS` includes `save_finding` and `recall_memory`.
- [ ] `parse_command("save_finding key=db_pool value=exhausted at step 4")` returns `params={"key": "db_pool", "value": "exhausted at step 4"}`.
- [ ] `parse_command("recall_memory")` returns `params={}`.
- [ ] `parse_command("recall_memory key=db_pool")` returns `params={"key": "db_pool"}`.
- [ ] All tests in `tests/test_command_parser.py` green.

## Depends on

- #3

## Unblocks

- #6, #13, #14

## Acceptance criteria

- [ ] **APIContract**: parser output `ParsedCommand` shape unchanged (S10).
- [ ] **Determinism**: regex parsing has no side effects.
- [ ] **Reward bound**: unchanged; parser doesn't compute rewards.
- [ ] **OpenEnv parity**: matches the `escalate reason=...` precedent in `server/command_parser.py`.
- [ ] **Review**: both leads + auto PR review approve.

## Plan docs to update (same PR as code)

- [ ] [`Architecture/MemoryModel.md`](./Architecture/MemoryModel.md) §5 (parser grammar table).

## References

- `server/command_parser.py` (S13)
- `praxis_env/models.py` AVAILABLE_COMMANDS (S10)
- [`Project/EvidenceIndex.md`](./Project/EvidenceIndex.md) S10, S13

---

# Issue #5 — [P0] reward.py memory events across all task policies

**Labels**: `P0`, `reward`, `memory`

## Context

The reward engine (S12) needs to score memory events with cutoff-aware values. Per [`Architecture/RewardPolicy.md`](./Architecture/RewardPolicy.md) §1 we add 6 new event tags to **every** task's `event_values` map.

## What to do

1. Add to `server/reward.py`:
   ```python
   _MEMORY_EVENTS: Mapping[str, float] = {
       "memory.save_finding.before_cutoff":  0.05,
       "memory.save_finding.after_cutoff":   0.02,
       "memory.recall_memory.before_cutoff": 0.01,
       "memory.recall_memory.after_cutoff":  0.08,
       "memory.illegal_log_after_cutoff":   -0.05,
       "memory.empty_recall_after_cutoff":  -0.02,
   }
   def _with_memory_events(events): ...
   ```
2. Wrap **every** existing entry in `DEFAULT_REWARD_POLICIES` through `_with_memory_events`. Do **not** mutate the original mappings — return new ones.
3. Add tests in `tests/test_reward.py`:
   - Every task's `event_values` contains all 6 memory tags.
   - `score("memory.recall_memory.after_cutoff")` returns `+0.08` pre-clamp.
   - 1000 random sequences stay clamped to `[0.01, 0.99]`.

## Done when

- [ ] `_MEMORY_EVENTS` and `_with_memory_events` defined.
- [ ] Every task in `DEFAULT_REWARD_POLICIES` has all 6 memory keys.
- [ ] No reward exceeds `[0.01, 0.99]` over a property-test sweep.
- [ ] `pytest -q tests/test_reward.py` green.

## Depends on

- #3

## Unblocks

- #6, #7, #14

## Acceptance criteria

- [ ] **APIContract**: reward field stays `float` in `[0.01, 0.99]` (S12).
- [ ] **Determinism**: pure-function scoring; no module state mutated.
- [ ] **Reward bound**: enforced at the `clamp_reward` boundary exactly once.
- [ ] **OpenEnv parity**: composability matches the rubric pattern (S20) — memory events stack with existing investigation/diagnosis/remediation slots.
- [ ] **Evidence gate**: every reward policy returns 0 for any `remediation.*` event when the scenario's `_root_cause_identified` is False; covered by a new `tests/test_reward.py::test_remediation_requires_diagnosis` (one row per task). See ADR-13.
- [ ] **Review**: both leads + auto PR review approve.

## Plan docs to update (same PR as code)

- [ ] [`Architecture/RewardPolicy.md`](./Architecture/RewardPolicy.md) (§5 helper, §7 audit checklist).
- [ ] [`Architecture/MemoryModel.md`](./Architecture/MemoryModel.md) §4 (cross-link).
- [ ] [`Project/DecisionLog.md`](./Project/DecisionLog.md) ADR-13 (cross-link).

## References

- `server/reward.py` (S12)
- `OpenEnv/src/openenv/core/rubrics/` (S20)
- [`Project/EvidenceIndex.md`](./Project/EvidenceIndex.md) S12, S20

---

# Issue #6 — [P0] PraxisEnvironment memory hook + cutoff observation rewrite

**Labels**: `P0`, `env`, `memory`

## Context

`server/praxis_environment.py` (S21) is the integration point. After this issue, `step()` routes `save_finding`/`recall_memory` to `PraxisMemory`, applies cutoff rewriting to `investigation_result`, and emits the right reward event tag.

## What to do

1. In `server/praxis_environment.py`:
   - Construct `self._memory = PraxisMemory()` in `__init__`.
   - Add `cutoff = getattr(scenario, "MEMORY_CUTOFF_OVERRIDE", PraxisMemory.CONTEXT_CUTOFF_STEP)` and apply it on `reset` (`self._memory.CONTEXT_CUTOFF_STEP = cutoff; self._memory.reset()`).
   - In `step(action)`:
     - Parse via `parse_command(action.command)` (already used).
     - If `parsed.action_type in {"save_finding", "recall_memory"}`, route to memory and emit `memory.<action>.<before|after>_cutoff` event for reward.
     - If `parsed.action_type` queries logs (`query_logs`, `check_logs`) and `step >= cutoff`, emit `memory.illegal_log_after_cutoff` and append a `[CONTEXT LIMIT]` line to the investigation result.
     - Else: existing scenario step path.
   - After producing the observation, set `observation.investigation_result = self._memory.get_observation_context(history, step)` if `is_active`, else keep as-is.
   - Always set `observation.memory_active = self._memory.is_active(step)` and `observation.saved_findings_count = len(self._memory.saved_findings)`.
   - Mirror in `state()`: `state.memory_active`, `state.session_id` (carried in from `SessionManager`).
2. Hand `session_id` from `SessionManager` to `PraxisEnvironment.reset(... session_id=...)` and stash on `self._session_id`.

## Done when

- [ ] `server/praxis_environment.py` constructs `PraxisMemory` once and resets it on every `reset`.
- [ ] `step()` routes memory commands without delegating to scenarios.
- [ ] After cutoff, `observation.investigation_result` is the memory banner; `memory_active=true`.
- [ ] `query_logs` / `check_logs` after cutoff emit `memory.illegal_log_after_cutoff` (-0.05).
- [ ] `state()` returns the new `session_id` and `memory_active` fields.

## Depends on

- #2, #3, #4, #5

## Unblocks

- #7, #13, #14, #15

## Acceptance criteria

- [ ] **APIContract**: response shape matches [`Architecture/APIContract.md`](./Architecture/APIContract.md) §3 (`/step`, `/state`).
- [ ] **Determinism**: replaying a fixed action list yields identical observations + rewards over 3 runs.
- [ ] **Reward bound**: stays in `[0.01, 0.99]` after the new bonuses.
- [ ] **OpenEnv parity**: cutoff banner is plain text, fits inside the existing `investigation_result: str` field.
- [ ] **Review**: `@Gokul287` approves.

## Plan docs to update (same PR as code)

- [ ] [`Architecture/DataFlow.md`](./Architecture/DataFlow.md) (§3 step flow → mark "shipped").
- [ ] [`Architecture/MemoryModel.md`](./Architecture/MemoryModel.md) (§2 lifecycle).
- [ ] [`Architecture/SessionLifecycle.md`](./Architecture/SessionLifecycle.md) (§5 memory lifecycle).

## References

- `server/praxis_environment.py` (S21)
- [`Project/EvidenceIndex.md`](./Project/EvidenceIndex.md) S10, S12, S21

---

# Issue #7 — [P0] Mega-incident scenario (cascading-platform-failure, 120 steps)

**Labels**: `P0`, `feature`, `scenario`, `theme-2`

## Context

The headline Theme #2 task. 120 steps, 8 services, 3 simultaneous root causes (`db_pool_corrupted`, `cdn_tls_expired`, `worker_memory_leak`), 6 red herrings, sparse milestone rewards. Forces the agent to actively use `save_finding`/`recall_memory` because the cutoff fires at step 30.

## What to do

1. Create `praxis_env/scenarios/mega_incident.py` extending `BaseScenario` (S11):
   ```python
   class MegaIncidentScenario(BaseScenario):
       NAME = "cascading-platform-failure"
       SEVERITY = "P1"   # escalates to P0 at 70% via base class
       MAX_STEPS = 120
       MEMORY_CUTOFF_OVERRIDE = 30
       INITIAL_AFFECTED_SERVICES = ["api","auth","database","cache","worker","queue","cdn","dns"]
   ```
2. Topology + investigation_results map per [`Architecture/ScenarioCatalog.md`](./Architecture/ScenarioCatalog.md) §3 — pre-baked logs/metrics for each service, deterministic.
3. Reward policy in `server/reward.py` per [`Architecture/RewardPolicy.md`](./Architecture/RewardPolicy.md) §3; goes through `_with_memory_events` (#5).
4. Resolution rule: `incident_resolved=True` when all 3 root causes diagnosed AND all 3 remediations applied; OR evidence-backed escalation after diagnosis #1 + ≥6 unique investigations.
5. Determinism: `tests/test_task5_mega_incident.py` (Issue #14) runs the optimal trajectory 3× and asserts identical reward vectors.

## Done when

- [ ] `MegaIncidentScenario` registered (Issue #9).
- [ ] `MAX_STEPS=120`, `MEMORY_CUTOFF_OVERRIDE=30`.
- [ ] 8 services and 3 root causes are pre-baked.
- [ ] Optimal-path test scores ≥ 0.55.
- [ ] Wrong-diagnosis test scores ≤ 0.10.

## Depends on

- #1, #6

## Unblocks

- #9, #14

## Acceptance criteria

- [ ] **APIContract**: returns valid `PraxisObservation` after each step (no extra fields, S15).
- [ ] **Determinism**: 3 identical runs → identical reward vectors.
- [ ] **Reward bound**: clamped per `BaseScenario.clamp_reward` (S11).
- [ ] **OpenEnv parity**: extends `BaseScenario`; no module singletons; works under `SessionManager`.
- [ ] **Evidence gate**: in `MegaIncidentScenario.step`, `remediation.*` events score 0 until at least one root cause has been correctly diagnosed; verified by `tests/test_task5_mega_incident.py::test_remediation_before_diagnosis_scores_zero`. See ADR-13.
- [ ] **Review**: `@GunaPalanivel` approves.

## Plan docs to update (same PR as code)

- [ ] [`Architecture/ScenarioCatalog.md`](./Architecture/ScenarioCatalog.md) §3 (mark shipped).
- [ ] [`Architecture/RewardPolicy.md`](./Architecture/RewardPolicy.md) §3.
- [ ] [`Project/DecisionLog.md`](./Project/DecisionLog.md) ADR-13 (cross-link).

## References

- `praxis_env/scenarios/base.py` (S11)
- `idea/Architecture/scenario_design.md` (S23)
- [`Project/EvidenceIndex.md`](./Project/EvidenceIndex.md) S11, S12, S23, S26

---

# Issue #8 — [P0] Procedural incident generator (seeded easy/medium/hard)

**Labels**: `P0`, `feature`, `scenario`, `procedural`

## Context

Turn Praxis from "4 tasks" into "∞ tasks" via a seeded generator. Same `(seed, difficulty)` → byte-identical scenario data. Mirrors the Llama 4 hard-prompt curriculum idea (S19) and ADR-07.

## What to do

1. Create `praxis_env/scenarios/procedural_incident.py`:
   ```python
   class ProceduralIncidentScenario(BaseScenario):
       NAME = "procedural-incident"
       def __init__(self, seed=None, difficulty="medium"):
           super().__init__()
           self._rng = random.Random(seed)
           self._difficulty = difficulty
   ```
2. Populate the pools in [`Architecture/ScenarioCatalog.md`](./Architecture/ScenarioCatalog.md) §4.2 (`ROOT_CAUSE_POOL`, `RED_HERRING_POOL`, `SERVICE_POOL`).
3. `_reset_scenario_state()` builds the scenario data and stamps `MAX_STEPS` + `MEMORY_CUTOFF_OVERRIDE` from the difficulty config (`easy=15/8`, `medium=25/15`, `hard=50/25`).
4. Build a difficulty-aware reward policy via `_build_procedural_policy(difficulty)` (per [`Architecture/RewardPolicy.md`](./Architecture/RewardPolicy.md) §4) and register it dynamically.
5. Plumb `seed` through `/reset` → `SessionManager.allocate(seed=...)` → `PraxisEnvironment.reset(seed=...)` → scenario `__init__`.

## Done when

- [ ] Generator produces a valid scenario for any seed + difficulty.
- [ ] Same `(seed, difficulty)` → identical observations and rewards over 3 runs.
- [ ] `seed=None` is rejected at `/reset` boundary; the env picks a default seed and returns it in metadata.
- [ ] `tests/test_task6_procedural.py` (Issue #14) green.

## Depends on

- #1

## Unblocks

- #9, #14

## Acceptance criteria

- [ ] **APIContract**: `/reset` accepts `seed: int` per [`Architecture/APIContract.md`](./Architecture/APIContract.md) §3.
- [ ] **Determinism**: `random.Random(seed)` is the only randomness source; tests assert byte-identity.
- [ ] **Reward bound**: clamped per `BaseScenario`.
- [ ] **OpenEnv parity**: extends `BaseScenario`; no global state.
- [ ] **Evidence gate**: in `ProceduralIncidentScenario.step`, `remediation.*` events score 0 until the chosen root cause has been diagnosed; verified by `tests/test_task6_procedural.py::test_remediation_before_diagnosis_scores_zero` across all 3 difficulties. See ADR-13.
- [ ] **Review**: `@GunaPalanivel` approves.

## Plan docs to update (same PR as code)

- [ ] [`Architecture/ScenarioCatalog.md`](./Architecture/ScenarioCatalog.md) §4 (mark shipped).
- [ ] [`Architecture/RewardPolicy.md`](./Architecture/RewardPolicy.md) §4 (mark shipped).
- [ ] [`Project/DecisionLog.md`](./Project/DecisionLog.md) ADR-07 + ADR-13 (cross-link).

## References

- `praxis_env/scenarios/base.py` (S11)
- Llama 4 blog (S19)
- [`Project/EvidenceIndex.md`](./Project/EvidenceIndex.md) S11, S19, S27

---

# Issue #9 — [P1] Scenario registry + openenv.yaml updates

**Labels**: `P1`, `manifest`, `registry`

## Context

The new scenarios must be discoverable by `/tasks`, `/metadata`, `openenv validate`, and the OpenEnv runtime validator (S18). The yaml also gains `supports_concurrent_sessions` and `themes`.

## What to do

1. Update `praxis_env/scenarios/__init__.py`:
   ```python
   SCENARIOS = {
       "single-service-alert":       SingleServiceAlertScenario,
       "ambiguous-incident":         AmbiguousIncidentScenario,
       "cascading-failure":          CascadingFailureScenario,
       "memory-leak":                MemoryLeakScenario,
       "cascading-platform-failure": MegaIncidentScenario,
       "procedural-incident":        ProceduralIncidentScenario,
   }
   ```
2. Update `openenv.yaml`:
   ```yaml
   supports_concurrent_sessions: true
   themes:
     - long-horizon-planning
   tasks:
     - { name: single-service-alert, difficulty: easy, max_steps: 15 }
     - { name: ambiguous-incident, difficulty: medium, max_steps: 25 }
     - { name: cascading-failure, difficulty: hard, max_steps: 20 }
     - { name: memory-leak, difficulty: hard, max_steps: 25 }
     - { name: cascading-platform-failure, difficulty: hard, max_steps: 120 }
     - { name: procedural-incident, difficulty: medium, max_steps: 25 }
   ```
3. Update `server/app.py` `/metadata` handler to list all 6 tasks + the new fields.
4. Add `tests/test_imports.py` checks for new scenario classes.

## Done when

- [ ] `/tasks` returns 6 names.
- [ ] `/metadata` returns the new top-level fields.
- [ ] `uv run openenv validate` PASS.

## Depends on

- #7, #8

## Unblocks

- #17

## Acceptance criteria

- [ ] **APIContract**: `/metadata` matches [`Architecture/APIContract.md`](./Architecture/APIContract.md) §3.
- [ ] **Determinism**: registry is a static dict; no dynamic lookup at request time beyond key hit.
- [ ] **Reward bound**: unaffected.
- [ ] **OpenEnv parity**: yaml fields recognised by `openenv validate` (S18).
- [ ] **Review**: both leads + auto PR review approve.

## Plan docs to update (same PR as code)

- [ ] [`Architecture/ScenarioCatalog.md`](./Architecture/ScenarioCatalog.md) §1 catalog table.
- [ ] [`Architecture/APIContract.md`](./Architecture/APIContract.md) §3 metadata example.

## References

- `praxis_env/scenarios/__init__.py`
- `openenv.yaml`
- `OpenEnv` docs (S18)

---

# Issue #10 — [P1] SRE system prompt + 3-row score gap table

**Labels**: `P1`, `inference`, `evidence`

## Context

Covers the 20% rewards-criterion via the inference-tier evidence path (ADR-08, S30). 30-minute task, no GPU required.

## What to do

1. Edit `inference.py` to add a structured SRE `SYSTEM_PROMPT` (verbatim from [`idea/Plan/task.md`](./task.md) T05 § "System Prompt"). Keep the existing `[START]/[STEP]/[END]` contract (S31).
2. Add a `--no-system-prompt` flag for the no-context row.
3. Add a `random_baseline()` helper that picks uniform random commands.
4. Run all 3 modes against `single-service-alert` and capture mean scores into `docs/baseline_scores.md`:
   ```markdown
   | Agent | Mean score | Behaviour |
   | Random baseline | ~0.021 | ... |
   | Qwen2.5-72B (no system prompt) | ~0.062 | ... |
   | Qwen2.5-72B (SRE system prompt) | 0.30+ | ... |
   ```
5. `[END]` line + reward vector for one full run goes into `docs/baseline_runs.txt`.

## Done when

- [ ] `docs/baseline_scores.md` exists with the 3-row table.
- [ ] SRE-prompted score is ≥ 5× random baseline on `single-service-alert`.
- [ ] `inference.py` still passes `tests/test_inference.py` (stdout contract).

## Depends on

- #1

## Unblocks

- #11, #19

## Acceptance criteria

- [ ] **APIContract**: stdout contract `[START]/[STEP]/[END]` unchanged (S31).
- [ ] **Determinism**: random baseline uses a fixed seed for reproducibility.
- [ ] **Reward bound**: scores remain in `[0.01, 0.99]`.
- [ ] **OpenEnv parity**: uses OpenAI client with `API_BASE_URL` / `MODEL_NAME` / `HF_TOKEN` (S31).
- [ ] **Review**: `@GunaPalanivel` approves.

## Plan docs to update (same PR as code)

- [ ] [`Demo/EvidencePackage.md`](./Demo/EvidencePackage.md) §1 (mark shipped, link to `docs/baseline_scores.md`).

## References

- `inference.py`
- `idea/Task.md` Decision 2 (S27)
- GRPO survey (S30)

---

# Issue #11 — [P1] train_praxis_grpo.py with TRL environment_factory + Trackio

**Labels**: `P1`, `training`, `pipeline`

## Context

Required minimum-submission deliverable (S2). Standalone Colab/HF-Jobs-ready GRPO trainer wired to Praxis via TRL `environment_factory` (S17). Trackio (S2: "metrics … reward plots") gives us live curves.

## What to do

1. Create `train_praxis_grpo.py` at the repo root. Implement `PraxisToolEnv` wrapper exactly as in [`idea/Plan/task.md`](./task.md) T06 § "environment_factory example" — methods: `reset`, `check_logs`, `check_metrics`, `check_deps`, `check_config`, `diagnose`, `restart_service`, `rollback_deploy`, `scale_resource`, `kill_query`, `escalate`, `save_finding`, `recall_memory`. Each routes to `PraxisEnv.step` and returns `result.observation.investigation_result`.
2. Configure `GRPOTrainer` with `Qwen/Qwen2.5-7B-Instruct`, `num_generations=8`, `max_completion_length=4096`, `task_names=["cascading-platform-failure","single-service-alert"]`.
3. Wire Trackio (`huggingface-trackio` skill — `idea/Task.md` cross-references; S2): `import trackio; trackio.init(project="praxis", config={...})` and `trackio.log({...})` at each `train_step`.
4. Top of file: PEP 723 inline metadata + `pip install` block so judges can `python train_praxis_grpo.py` from a clean Colab/HF Job.
5. Save a reward-plot helper that emits `docs/reward_curve.png` (matplotlib) and exits cleanly.

## Done when

- [ ] `train_praxis_grpo.py` runs end-to-end on a small CPU-only smoke (`num_generations=2`, `--max-steps 1`) without crashing.
- [ ] `PraxisToolEnv` has docstrings on every tool method (TRL parses these).
- [ ] Trackio init + logs are present.
- [ ] PEP 723 header lists all deps with pinned versions.

## Depends on

- #5, #10

## Unblocks

- #12, #19

## Acceptance criteria

- [ ] **APIContract**: communicates via `PraxisEnv` HTTP client only; never imports server internals.
- [ ] **Determinism**: deterministic on `seed` parameter for the smoke path.
- [ ] **Reward bound**: rewards consumed are in `[0.01, 0.99]`.
- [ ] **OpenEnv parity**: uses TRL `environment_factory` exactly per S17.
- [ ] **Review**: `@GunaPalanivel` approves.

## Plan docs to update (same PR as code)

- [ ] [`Demo/EvidencePackage.md`](./Demo/EvidencePackage.md) §2 (mark "scaffolded; curve pending #12").
- [ ] [`Submission/ReleasePackage.md`](./Submission/ReleasePackage.md) §1 file tree.

## References

- TRL docs (S17)
- `praxis_env/client.py`
- [`Project/EvidenceIndex.md`](./Project/EvidenceIndex.md) S17, S30, S32

---

# Issue #12 — [P1] GRPO 50-step run on Qwen2.5-7B + reward_curve.png

**Labels**: `P1`, `training`, `evidence`

## Context

Captures the actual training-improvement curve (S2 "Showing improvement in rewards"). 50 steps on `Qwen/Qwen2.5-7B-Instruct` × `single-service-alert` is the minimum that produces a meaningful curve (per `idea/Task.md` lines 132–146).

## What to do

1. If HF compute credits are present (`hf jobs status`), launch:
   ```
   uv run python train_praxis_grpo.py --task single-service-alert --max-steps 50 --num-generations 8
   ```
2. Otherwise log the gap explicitly in the README per ADR-08 and rely on the score gap from #10.
3. On completion, save:
   - `docs/reward_curve.png` (matplotlib; labelled axes, legend "trained vs random baseline").
   - Trackio run URL into `docs/trackio_url.txt`.
4. Update `docs/baseline_scores.md` with the trained-mean row.

## Done when

- [ ] `docs/reward_curve.png` committed with both axes labelled.
- [ ] Trackio URL committed.
- [ ] `docs/baseline_scores.md` has a 4th row (trained Qwen).
- [ ] If GPU credits unavailable: README explicitly documents the fallback (no silent gap).

## Depends on

- #11

## Unblocks

- #19

## Acceptance criteria

- [ ] **APIContract**: doesn't change wire format; consumes `/reset`+`/step` only.
- [ ] **Determinism**: same `seed` + `task` reproduces the same starting state on the env side.
- [ ] **Reward bound**: rewards in `[0.01, 0.99]` throughout.
- [ ] **OpenEnv parity**: TRL `environment_factory` is the only training pathway used.
- [ ] **Review**: `@GunaPalanivel` approves.

## Plan docs to update (same PR as code)

- [ ] [`Demo/EvidencePackage.md`](./Demo/EvidencePackage.md) §2 + §7 (final inventory).
- [ ] [`Submission/ReleasePackage.md`](./Submission/ReleasePackage.md) §2 (Trackio URL row).

## References

- `idea/Task.md` Decision 2 (S27)
- GRPO survey (S30)

---

# Issue #13 — [P1] Memory layer tests (cutoff behaviour, determinism, reset)

**Labels**: `P1`, `tests`, `memory`

## Context

Memory is the moat — it must be tested to death. This suite locks the cutoff banner, the determinism contract, the cross-episode reset, and the reward-tag emissions.

## What to do

1. New file `tests/test_memory.py`:
   - `test_save_finding_returns_confirmation` — `save_finding("k","v")` returns `"Saved: k"` (or matching string per #3).
   - `test_recall_specific_key` and `test_recall_all`.
   - `test_recall_unknown_key_returns_helpful_message`.
   - `test_get_observation_context_pre_cutoff_returns_log_tail` — last 10 entries.
   - `test_get_observation_context_post_cutoff_returns_banner` — banner contains `[CONTEXT LIMIT REACHED]` and the saved keys.
   - `test_reset_clears_findings`.
   - `test_determinism` — same trajectory replayed 3× → identical outputs.
2. New file `tests/test_memory_cutoff.py` — integration via the env:
   - `test_step_30_flips_observation` on `cascading-platform-failure`.
   - `test_query_logs_after_cutoff_emits_illegal_event` and applies −0.05.
   - `test_recall_after_cutoff_emits_after_cutoff_event` and applies +0.08.

## Done when

- [ ] All listed tests written and green.
- [ ] `pytest -q tests/test_memory.py tests/test_memory_cutoff.py` passes.
- [ ] Coverage for `praxis_env/memory.py` ≥ 95% lines.

## Depends on

- #3, #6

## Unblocks

- #17

## Acceptance criteria

- [ ] **APIContract**: tests assert observation field shape (S15) — `memory_active`, `saved_findings_count`, `investigation_result`.
- [ ] **Determinism**: 3-run replay assertion is in the suite.
- [ ] **Reward bound**: every tested reward in `[0.01, 0.99]`.
- [ ] **OpenEnv parity**: tests run with `pytest` only — no network, no Docker.
- [ ] **Review**: both leads + auto PR review approve.

## Plan docs to update (same PR as code)

- [ ] [`Architecture/MemoryModel.md`](./Architecture/MemoryModel.md) §7 (mark "tested").

## References

- `praxis_env/memory.py` (#3)
- `server/praxis_environment.py` (S21)

---

# Issue #14 — [P1] Mega + procedural scenario tests

**Labels**: `P1`, `tests`, `scenario`

## Context

Locks the optimal-path scores, red-herring penalties, and seed determinism for the two new scenarios.

## What to do

1. `tests/test_task5_mega_incident.py`:
   - `test_optimal_trajectory_scores_above_0_55` (deterministic action list from [`Demo/ScreenplayScript.md`](./Demo/ScreenplayScript.md) §3).
   - `test_wrong_diagnosis_scores_below_0_15`.
   - `test_red_herring_does_not_resolve_incident`.
   - `test_severity_escalates_to_p0_at_step_84`.
   - `test_determinism_3_runs`.
2. `tests/test_task6_procedural.py`:
   - `test_same_seed_same_observation_byte_identical` (3 difficulty tiers).
   - `test_different_seeds_produce_different_root_causes` (sample 20 seeds; assert variance).
   - `test_easy_difficulty_uses_15_steps`.
   - `test_hard_difficulty_uses_50_steps`.
   - `test_optimal_path_scores_meet_targets` (per [`Architecture/ScenarioCatalog.md`](./Architecture/ScenarioCatalog.md) §4.1).
3. **Evidence-gate tests** (cross-scenario, ADR-13):
   - `tests/test_task5_mega_incident.py::test_remediation_before_diagnosis_scores_zero` — remediation event before any diagnose call returns reward `0.01` (clamp floor) and `_root_cause_identified` stays `False`.
   - `tests/test_task6_procedural.py::test_remediation_before_diagnosis_scores_zero` — same assertion across all 3 difficulty tiers (`easy`, `medium`, `hard`).

## Done when

- [ ] Both files exist and all listed tests are green.
- [ ] Determinism assertions cover both scenarios.
- [ ] `test_remediation_before_diagnosis_scores_zero` passes for both new scenarios across all 3 procedural difficulties.

## Depends on

- #5, #7, #8

## Unblocks

- #17

## Acceptance criteria

- [ ] **APIContract**: tests use `PraxisEnv` HTTP client, never import server internals (S2 "client/server separation").
- [ ] **Determinism**: byte-identical reward vectors over 3 runs.
- [ ] **Reward bound**: target scores fall inside `[0.01, 0.99]`.
- [ ] **OpenEnv parity**: extends `BaseScenario`; no global state leaks.
- [ ] **Review**: both leads + auto PR review approve.

## Plan docs to update (same PR as code)

- [ ] [`Architecture/ScenarioCatalog.md`](./Architecture/ScenarioCatalog.md) §6 (mark coverage shipped).

## References

- `idea/Architecture/scenario_design.md` (S23)

---

# Issue #15 — [P1] Concurrent sessions tests (8 parallel sessions, no cross-talk)

**Labels**: `P1`, `tests`, `concurrency`

## Context

Locks the `SessionManager` from Issue #1. TRL parallel rollouts (S17) and the OpenEnv runtime validator (S14) both need this assured.

## What to do

1. `tests/test_concurrent_sessions.py`:
   - `test_8_parallel_resets_yield_distinct_session_ids`.
   - `test_independent_step_counts` — run 8 sessions, each takes a different number of steps, assert no drift.
   - `test_lru_eviction_at_129th_session` — allocate 130, oldest id no longer resolves.
   - `test_step_without_session_id_returns_400`.
   - `test_step_with_unknown_session_id_returns_400`.
   - `test_session_isolation_with_memory` — session A saves a finding; session B's `recall_memory` does not see it.
2. Use `concurrent.futures.ThreadPoolExecutor(max_workers=8)` against the FastAPI test client.

## Done when

- [ ] All listed tests written and green.
- [ ] Suite total runtime < 30 s.

## Depends on

- #1, #6

## Unblocks

- #17

## Acceptance criteria

- [ ] **APIContract**: 400 detail messages match [`Architecture/SessionLifecycle.md`](./Architecture/SessionLifecycle.md) §8.
- [ ] **Determinism**: parallel runs produce reproducible reward vectors per session id (recorded as fixture).
- [ ] **Reward bound**: rewards in `[0.01, 0.99]`.
- [ ] **OpenEnv parity**: `SUPPORTS_CONCURRENT_SESSIONS = True` exercised.
- [ ] **Review**: both leads + auto PR review approve.

## Plan docs to update (same PR as code)

- [ ] [`Architecture/ConcurrencyModel.md`](./Architecture/ConcurrencyModel.md) §6 (mark covered).
- [ ] [`Architecture/SessionLifecycle.md`](./Architecture/SessionLifecycle.md) §8 (failure-modes column).

## References

- `OpenEnv/src/openenv/core/env_server/interfaces.py` (S14)

---

# Issue #16 — [P2] Move mock_validator.py → tests/smoke_test.py + import audit

**Labels**: `P2`, `cleanup`

## Context

`mock_validator.py` lives at the repo root today; that screams "demo art" to a Meta engineer browsing the repo. Move it under `tests/` and rerun an import audit to catch any path that hard-codes the root location.

## What to do

1. `git mv mock_validator.py tests/smoke_test.py`.
2. `rg -n "mock_validator"` and update every callsite (Dockerfile, scripts, docs).
3. Add an `__init__.py` if missing in `tests/`.
4. Update `pyproject.toml` if the test discovery glob excludes `smoke_test.py` (it shouldn't by default).

## Done when

- [ ] `mock_validator.py` no longer exists at repo root.
- [ ] `tests/smoke_test.py` works under `pytest -q tests/smoke_test.py`.
- [ ] No string `"mock_validator"` remains anywhere except in git history.

## Depends on

- _(none — independent cleanup)_

## Unblocks

- #17

## Acceptance criteria

- [ ] **APIContract**: unchanged.
- [ ] **Determinism**: smoke script re-runs without env mutations.
- [ ] **Reward bound**: unaffected.
- [ ] **OpenEnv parity**: tests live under `tests/` (S5 code-quality bar).
- [ ] **Review**: both leads + auto PR review approve.

## Plan docs to update (same PR as code)

- [ ] [`Submission/ReleasePackage.md`](./Submission/ReleasePackage.md) §1 file tree (mock_validator removed).

## References

- repo root listing
- `idea/Plan/task.md` T09

---

# Issue #17 — [P2] Full server validation script (all 6 tasks, < 20 min, vCPU2/8GB)

**Labels**: `P2`, `validation`, `submission`

## Context

The Phase 1 auto-validation gates (S3) say: HF Space deploys, `openenv validate` passes, `inference.py` reproduces, runtime < 20 min on vCPU=2/8GB. We bundle this into a single repeatable script.

## What to do

1. Create `scripts/validate_submission.sh` (or `.ps1`):
   ```bash
   set -euo pipefail
   uv sync
   uv run openenv validate
   pytest -q
   python -m uvicorn server.app:app --port 7860 &
   PID=$!
   trap "kill $PID" EXIT
   sleep 3
   curl -s http://localhost:7860/health | grep healthy
   for task in single-service-alert ambiguous-incident cascading-failure memory-leak \
               cascading-platform-failure procedural-incident; do
     curl -s -X POST http://localhost:7860/reset \
          -H "Content-Type: application/json" \
          -d "{\"task_name\":\"$task\"}" | python -m json.tool >/dev/null
   done
   API_BASE_URL=... MODEL_NAME=... HF_TOKEN=... python inference.py
   ```
2. Capture stdout/stderr to `docs/runtime_receipt.txt` and `docs/determinism_receipt.txt`.
3. CI (GitHub Actions or local `act`): wire `scripts/validate_submission.sh` to run on every PR.

## Done when

- [ ] Script exists and exits 0 on a clean clone.
- [ ] `docs/runtime_receipt.txt` and `docs/determinism_receipt.txt` populated.
- [ ] CI step added (or local-only with a `nightly.yml` placeholder is acceptable for the hackathon).

## Depends on

- #9, #13, #14, #15, #16

## Unblocks

- #18

## Acceptance criteria

- [ ] **APIContract**: hits all endpoints in [`Architecture/APIContract.md`](./Architecture/APIContract.md) §1.
- [ ] **Determinism**: receipt files reproducible across 3 runs.
- [ ] **Reward bound**: every per-task run shows rewards in `[0.01, 0.99]`.
- [ ] **OpenEnv parity**: `openenv validate` PASS.
- [ ] **Review**: both leads + auto PR review approve.

## Plan docs to update (same PR as code)

- [ ] [`Submission/SubmissionChecklist.md`](./Submission/SubmissionChecklist.md) §4 (link to script).
- [ ] [`Demo/EvidencePackage.md`](./Demo/EvidencePackage.md) §4 + §5.

## References

- `idea/PROBLEM STATEMENT/How Judging works.md` (S3)

---

# Issue #18 — [P2] Dockerfile + HF Spaces deploy + /health verification

**Labels**: `P2`, `deployment`

## Context

Required minimum-submission deliverable (S2). The HF Space must serve all 6 tasks and `/health` must return 200 from a private window.

## What to do

1. Update `Dockerfile`:
   - Ensure `COPY praxis_env/memory.py` is covered by the existing `COPY praxis_env/ /app/praxis_env/` glob; if not, add it explicitly.
   - Ensure `train_praxis_grpo.py` is **NOT** baked into the runtime image (we don't train inside the Space).
   - `EXPOSE 7860`; `CMD ["uvicorn","server.app:app","--host","0.0.0.0","--port","7860"]`.
2. `docker build -t praxis-env:submit .` locally; `docker run -p 7860:7860 praxis-env:submit`; verify `/health` 200.
3. Push to HF Spaces:
   - `hf auth login`
   - `hf repo create spaces/<org>/praxis-env --type space --private` (if not exists)
   - `git remote add hf https://huggingface.co/spaces/<org>/praxis-env`
   - `git push hf main`
4. Verify Space cold-start completes; `/health` returns 200; all 6 tasks reachable.
5. Save the Space URL into `docs/space_url.txt`.

## Done when

- [ ] Local `docker run` shows healthy status and serves `/reset` for all 6 tasks.
- [ ] HF Space `/health` returns 200 from a private window (no auth).
- [ ] `docs/space_url.txt` committed.
- [ ] `huggingface-cli`/`hf` CLI is the only deploy path used (S2).

## Depends on

- #17

## Unblocks

- #19, #20

## Acceptance criteria

- [ ] **APIContract**: all routes from [`Architecture/APIContract.md`](./Architecture/APIContract.md) §1 reachable on the Space.
- [ ] **Determinism**: deployed Space matches the local image SHA.
- [ ] **Reward bound**: live `/step` returns rewards in `[0.01, 0.99]`.
- [ ] **OpenEnv parity**: Space tagged with `openenv` per S2.
- [ ] **Review**: `@GunaPalanivel` approves.

## Plan docs to update (same PR as code)

- [ ] [`Submission/SubmissionChecklist.md`](./Submission/SubmissionChecklist.md) §1 (mark hard-gate done).
- [ ] [`Submission/ReleasePackage.md`](./Submission/ReleasePackage.md) §2 (Space URL row).

## References

- `Dockerfile`
- `hf-cli` skill (S2)

---

# Issue #19 — [P2] README rewrite — memory story, arch diagram, score table, training links

**Labels**: `P2`, `documentation`, `submission`

## Context

The README is the storytelling 30% in concentrated form. Judges spend 3–5 minutes here. It must lead with the memory hook, show the cutoff diagram, link to the Space, the score table, and the reward curve.

## What to do

1. Rewrite `README.md`:
   - Tagline + the 8-line link block from [`Submission/ReleasePackage.md`](./Submission/ReleasePackage.md) §3.
   - "Why this matters" — 2 paragraphs grounded in S26, S28, S29.
   - "Memory system" — explain `save_finding`, `recall_memory`, cutoff banner; embed the architecture diagram from [`Architecture/DataFlow.md`](./Architecture/DataFlow.md) §1 inline.
   - "Tasks" — table mirroring [`Architecture/ScenarioCatalog.md`](./Architecture/ScenarioCatalog.md) §1.
   - "Reward design" — mention the 6 memory event tags + clamp; link to [`Architecture/RewardPolicy.md`](./Architecture/RewardPolicy.md).
   - "Baseline scores" — paste the `docs/baseline_scores.md` table.
   - "Training" — embed the TRL `environment_factory` snippet from `train_praxis_grpo.py`; link Trackio.
   - "Benchmark API" — one-liner pointing at `GET /benchmark` (Issue #21) so judges see the env was designed for benchmarking.
   - "Citations" — AgeMem (S28), 2601.07190 (S29), GRPO survey (S30).
   - "Quick start" — 5-command clone-to-running.
2. Add `docs/demo.gif` (1:10 cutoff moment, 3–6 second loop, < 4 MB).
3. **Patch [`praxis_env/scenarios/ambiguous_incident.py`](../../praxis_env/scenarios/ambiguous_incident.py)** — discoverability fix for the cold-start LLM (closes critique #4):
   - Extend `INITIAL_AFFECTED_SERVICES` to include `"dns-resolver"` and `"load-balancer"` so `services_affected` surfaces them in the first observation.
   - Rephrase the opening line of `ALERT_SUMMARY` to explicitly say `Investigate app + infrastructure layers (dns-resolver, load-balancer, cdn)` **without** naming the root cause.
   - Re-tune `tests/test_task3_ambiguous_incident.py` baselines if the optimal-path score moves > 0.02; add `test_initial_observation_lists_infra_services` asserting the new field membership.
   - Take the README screenshot **after** this patch so the visible alert reflects shipping reality.

## Done when

- [ ] `README.md` rewritten.
- [ ] All link-block URLs resolve.
- [ ] Score table inline with at least 3 rows; reward curve image inline (or fallback note).
- [ ] arxiv citations present.
- [ ] `docs/demo.gif` < 4 MB and rendered in the README.
- [ ] `praxis_env/scenarios/ambiguous_incident.py` lists `dns-resolver` + `load-balancer` in `INITIAL_AFFECTED_SERVICES` and the rephrased `ALERT_SUMMARY`.
- [ ] `tests/test_task3_ambiguous_incident.py::test_initial_observation_lists_infra_services` green; existing scenario tests still green (re-tuned only if delta > 0.02).

## Depends on

- #10, #12, #18

## Unblocks

- #20

## Acceptance criteria

- [ ] **APIContract**: README links to [`Architecture/APIContract.md`](./Architecture/APIContract.md).
- [ ] **Determinism**: text uses concrete numbers, not "we plan to".
- [ ] **Reward bound**: any reward references match the open `(0.0, 1.0)` interval.
- [ ] **OpenEnv parity**: README explicitly mentions `openenv validate`, `SUPPORTS_CONCURRENT_SESSIONS`, TRL `environment_factory`.
- [ ] **Discoverability**: a frontier LLM can identify `dns-resolver` as a candidate service from the first observation alone (no prior domain knowledge required); `tests/test_task3_ambiguous_incident.py::test_initial_observation_lists_infra_services` asserts the field membership.
- [ ] **Review**: `@Gokul287` approves.

## Plan docs to update (same PR as code)

- [ ] [`Submission/SubmissionChecklist.md`](./Submission/SubmissionChecklist.md) §3 (mark each row green).
- [ ] [`Submission/ReleasePackage.md`](./Submission/ReleasePackage.md) §3 link block.
- [ ] [`Architecture/ScenarioCatalog.md`](./Architecture/ScenarioCatalog.md) §2 (`ambiguous-incident` recap — note the discoverability tweak).

## References

- `idea/Plan/task.md` T06 README structure
- S2, S26, S28, S29, S30

---

# Issue #20 — [P2] Demo Narrative + ScreenplayScript + mini-blog/video + slides

**Labels**: `P2`, `demo`, `submission`

## Context

The pitch + media package. Without this, storytelling 30% loses points even if everything else is perfect (S2 "Tell a story, not an API doc").

## What to do

1. Lock [`Demo/Narrative.md`](./Demo/Narrative.md) and [`Demo/ScreenplayScript.md`](./Demo/ScreenplayScript.md) — verify timings (60–90 s pitch, ≤ 2:30 demo) by walking through 3× with a watch.
2. Record the live demo flow per `Demo/ScreenplayScript.md` §2 cue sheet:
   - Step 1:10 must show the cutoff banner.
   - Total < 2 min for the YouTube video.
3. Publish:
   - YouTube unlisted ≤ 2 min OR HF Space video tab.
   - Mini-blog on HF blog with the 5 sentences from [`Submission/ReleasePackage.md`](./Submission/ReleasePackage.md) §4.
   - Slide deck (Google Slides public link) — 5 slides per `Demo/Narrative.md` §3.
4. Commit `docs/demo_trajectory.txt` (deterministic replay) so we can reproduce the demo if the live LLM stalls.
5. Update `README.md` link block with the new URLs.

## Done when

- [ ] YouTube/video URL live (< 2 min, public unlisted).
- [ ] Mini-blog URL live.
- [ ] Slide deck URL live.
- [ ] `docs/demo_trajectory.txt` committed and replays cleanly via `python -c "from inference import replay_trajectory; replay_trajectory('docs/demo_trajectory.txt')"`.
- [ ] README link block updated.

## Depends on

- #18, #19

## Unblocks

- _(this is the final pre-submit issue)_

## Acceptance criteria

- [ ] **APIContract**: replay uses `PraxisEnv` HTTP client only.
- [ ] **Determinism**: replay produces the same `[END]` reward vector across 3 runs.
- [ ] **Reward bound**: rewards visible in the demo are `(0.0, 1.0)`.
- [ ] **OpenEnv parity**: video shows `openenv validate` PASS, the score gap, and the cutoff banner.
- [ ] **Review**: `@GunaPalanivel` approves; final 60-second pitch rehearsed by Gokul on stage timing.

## Plan docs to update (same PR as code)

- [ ] [`Demo/Narrative.md`](./Demo/Narrative.md) (confirm timing).
- [ ] [`Demo/ScreenplayScript.md`](./Demo/ScreenplayScript.md) (confirm trajectory committed).
- [ ] [`Submission/ReleasePackage.md`](./Submission/ReleasePackage.md) §2 (URLs filled in).

## References

- S2 ("Tell a story…", "Make your plots readable")
- `idea/Task.md` Decision 3 (S27)
- arxiv AgeMem (S28)

---

# Issue #21 — [P2] GET /benchmark endpoint reading docs/baseline_scores.md

**Labels**: `P2`, `server`, `benchmark`, `submission`

## Context

Critique #5 from the Apr-25 audit thread asks for a `GET /benchmark` endpoint that signals "this env was designed for benchmarking" the moment a Meta engineer browses the API. SF-winner envs shipped this. We piggy-back on `docs/baseline_scores.md` (produced by Issue #10) so the endpoint stays a thin read-only adapter — no new state, no concurrency surface. ADR-14 in [`Project/DecisionLog.md`](./Project/DecisionLog.md) documents the trade-off (small duplication with `/metadata`, but cheap and high-signal for judges).

## What to do

1. Add a small parser in [`server/app.py`](../../server/app.py) (or a new `server/benchmark.py` if cleaner) that reads `docs/baseline_scores.md` once at process start, parses the markdown table into `[{model, mean_score, run_date, behaviour}]`, and caches it for the process lifetime. Re-parse on `SIGHUP` is **not** required for the hackathon.
2. Mount `GET /benchmark` returning a Pydantic-validated body:
   ```python
   class BenchmarkResponse(BaseModel):
       model_config = ConfigDict(extra="forbid")
       environment: str        # "praxis-env"
       model_scores: list[ModelScore]
       note: str               # default fixed sentence below
       source: str             # "docs/baseline_scores.md"
   class ModelScore(BaseModel):
       model_config = ConfigDict(extra="forbid")
       model: str
       mean_score: float
       run_date: str           # YYYY-MM-DD; empty string if unknown
       behaviour: str = ""
   ```
   Default `note`: `"Higher scores require multi-hop investigation before diagnosis"`.
3. Missing-file fallback: if `docs/baseline_scores.md` does not exist (e.g. first deploy), return 200 with `model_scores: []` and `note: "Benchmark scores not yet recorded; see docs/baseline_scores.md once Issue #10 ships."` Do **not** error.
4. Add the schema row to [`Architecture/APIContract.md`](./Architecture/APIContract.md) §1 endpoints table and append the `GET /benchmark` wire-format block to §3.
5. New tests in `tests/test_api_benchmark.py`:
   - `test_benchmark_returns_200_and_three_rows` against a fixture markdown file.
   - `test_benchmark_missing_file_returns_empty_list_with_helpful_note`.
   - `test_benchmark_response_rejects_extra_fields` (ConfigDict extra="forbid", S15).
6. Link `GET /benchmark` from the README link block in Issue #19.

## Done when

- [ ] `GET /benchmark` returns 200 with parsed rows when `docs/baseline_scores.md` exists.
- [ ] Missing-file fallback returns 200 with `model_scores: []` and the helpful `note`.
- [ ] `tests/test_api_benchmark.py` (3 tests) green.
- [ ] [`Architecture/APIContract.md`](./Architecture/APIContract.md) §1 + §3 list the endpoint.
- [ ] README link block (Issue #19) references `GET /benchmark`.

## Depends on

- #1 (FastAPI app shape via `SessionManager`)
- #10 (`docs/baseline_scores.md` exists with at least 3 rows)

## Unblocks

- #19 (README link block now resolves)

## Acceptance criteria

- [ ] **APIContract**: response shape matches [`Architecture/APIContract.md`](./Architecture/APIContract.md) §3 (`BenchmarkResponse`); no extra fields (S15).
- [ ] **Determinism**: parsing is byte-stable; same `baseline_scores.md` always yields the same JSON ordering.
- [ ] **Reward bound**: endpoint reports `mean_score` as float; values pass through unchanged (clamping is the inference script's job, not this endpoint's).
- [ ] **OpenEnv parity**: `extra="forbid"` Pydantic response per S15; no session header required (matches `/health` / `/tasks`).
- [ ] **Review**: `@GunaPalanivel` approves.

## Plan docs to update (same PR as code — keep plan == reality)

- [ ] [`Architecture/APIContract.md`](./Architecture/APIContract.md) §1 endpoints table + §3 wire-format block.
- [ ] [`Submission/ReleasePackage.md`](./Submission/ReleasePackage.md) §3 README link block.
- [ ] [`Project/DecisionLog.md`](./Project/DecisionLog.md) ADR-14 (cross-link).

## References

- `server/app.py` (S9) — current FastAPI surface
- `docs/baseline_scores.md` (produced by Issue #10)
- ADR-14 in [`Project/DecisionLog.md`](./Project/DecisionLog.md)
- Critique #5 (Apr-25 audit thread): "Add a `GET /leaderboard` or `GET /benchmark` endpoint"
- S2 "What makes a submission stand out" — designed-for-benchmarking signal

---

## Index

| #   | Title                                                            | Assignee                | Reviewer(s)                                     | Wave |
| --- | ---------------------------------------------------------------- | ----------------------- | ----------------------------------------------- | ---- |
| 1   | Session-based PraxisEnvironment + X-Session-Id                   | `@GunaPalanivel`        | `@Gokul287`                                     | 1    |
| 2   | Pydantic memory-aware action/observation schema                  | `@GunaPalanivel`        | `@Gokul287`                                     | 2    |
| 3   | PraxisMemory module                                              | `@GunaPalanivel`        | `@Gokul287`                                     | 3    |
| 4   | command_parser KNOWN_ACTIONS + AVAILABLE_COMMANDS for memory     | `@snehasneha56526-arch` | `@GunaPalanivel` + `@Gokul287` + auto PR review | 3    |
| 5   | reward.py memory events across all task policies                 | `@snehasneha56526-arch` | `@GunaPalanivel` + `@Gokul287` + auto PR review | 4    |
| 6   | PraxisEnvironment memory hook + cutoff observation rewrite       | `@GunaPalanivel`        | `@Gokul287`                                     | 4    |
| 7   | Mega-incident scenario (cascading-platform-failure, 120 steps)   | `@Gokul287`             | `@GunaPalanivel`                                | 2-3  |
| 8   | Procedural incident generator (seeded easy/medium/hard)          | `@Gokul287`             | `@GunaPalanivel`                                | 4    |
| 9   | Scenario registry + openenv.yaml updates                         | `@snehasneha56526-arch` | `@GunaPalanivel` + `@Gokul287` + auto PR review | 5    |
| 10  | SRE system prompt + 3-row score gap table                        | `@Gokul287`             | `@GunaPalanivel`                                | 5    |
| 11  | train_praxis_grpo.py with TRL environment_factory + Trackio      | `@Gokul287`             | `@GunaPalanivel`                                | 6    |
| 12  | GRPO 50-step run + reward_curve.png                              | `@Gokul287`             | `@GunaPalanivel`                                | 7    |
| 13  | Memory layer tests                                               | `@snehasneha56526-arch` | `@GunaPalanivel` + `@Gokul287` + auto PR review | 5    |
| 14  | Mega + procedural scenario tests                                 | `@snehasneha56526-arch` | `@GunaPalanivel` + `@Gokul287` + auto PR review | 6    |
| 15  | Concurrent-session tests                                         | `@snehasneha56526-arch` | `@GunaPalanivel` + `@Gokul287` + auto PR review | 6    |
| 16  | Move mock_validator.py → tests/smoke_test.py                     | `@snehasneha56526-arch` | `@GunaPalanivel` + `@Gokul287` + auto PR review | 7    |
| 17  | Full server validation script (all 6 tasks, < 20 min, vCPU2/8GB) | `@snehasneha56526-arch` | `@GunaPalanivel` + `@Gokul287` + auto PR review | 7    |
| 18  | Dockerfile + HF Spaces deploy + /health verification             | `@Gokul287`             | `@GunaPalanivel`                                | 8    |
| 19  | README rewrite                                                   | `@GunaPalanivel`        | `@Gokul287`                                     | 8    |
| 20  | Demo Narrative + ScreenplayScript + mini-blog/video + slides     | `@Gokul287`             | `@GunaPalanivel`                                | 9    |
| 21  | GET /benchmark endpoint reading docs/baseline_scores.md          | `@Gokul287`             | `@GunaPalanivel`                                | 8    |

> Critical path: **#1 → #3 → #6 → #7 → #9 → #17 → #18 → #19 → #20** (≈ 9 h with buffer).
> Anything off this chain runs in parallel — including #21, which slots into the Gokul tail of Wave 8 alongside #18. Quality > parallelism.
