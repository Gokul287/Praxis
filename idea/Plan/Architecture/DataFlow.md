# Data Flow — End-to-End Praxis Trajectory

> Single-source diagrams that every issue can link to. Mirrors OpenEnv's
> `Environment / Action / Observation / State` contract from
> `OpenEnv/src/openenv/core/env_server/interfaces.py`.

---

## 1. Component map

```mermaid
flowchart LR
    subgraph Client[Client side]
        T[TRL GRPOTrainer<br/>environment_factory]
        I[inference.py]
        H[curl / judge harness]
    end

    subgraph API[FastAPI server: server/app.py]
        R[/reset/]
        S[/step/]
        ST[/state/]
        HE[/health, /metadata, /schema/]
    end

    subgraph Core[Per-session core]
        SM[SessionManager<br/>sessions: dict<br/>+ asyncio.Lock]
        PE[PraxisEnvironment]
        CP[command_parser]
        MEM[PraxisMemory]
        SC[BaseScenario subclass]
        AS[ArtifactStore<br/>Rootly logs-dataset]
        subgraph RUB[RewardEngine — composable rubrics]
            PR[PlanningRubric 0.20]
            MR[MemoryRubric 0.20]
            RR[RecoveryRubric 0.20]
            TR[TerminalRubric 0.40]
        end
    end

    T --> R
    I --> R
    H --> R
    T --> S
    I --> S
    H --> S
    T --> ST
    H --> HE

    R --> SM
    S --> SM
    ST --> SM

    SM --> PE
    PE --> CP
    PE --> MEM
    PE --> SC
    PE --> RUB
    SC --> AS
    SC --> RUB
    MEM --> RUB
```

---

## 2. Reset flow

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant API as POST /reset
    participant SM as SessionManager
    participant PE as PraxisEnvironment
    participant SC as Scenario
    participant M as PraxisMemory

    C->>API: {task_name, seed?}
    API->>SM: allocate_session(task_name, seed)
    SM->>SM: uuid4() + LRU evict if > 128
    SM->>PE: PraxisEnvironment()
    PE->>SC: get_scenario(task_name)(seed=seed)
    PE->>M: PraxisMemory()
    PE->>SC: reset(episode_id="task_N")
    SC-->>PE: initial state
    PE-->>SM: PraxisObservation(memory_active=false, ...)
    SM-->>API: (session_id, obs)
    API-->>C: {session_id, observation, ...flat}
```

Key invariants:

- `session_id` is a fresh UUID4 returned in the JSON body (not in a header).
- `seed` is forwarded only to scenarios that opt in (`procedural-incident`).
- Memory always resets in lockstep with the scenario.

---

## 3. Step flow (with memory branch)

Status: shipped in Issue #6 (`server/praxis_environment.py` + `server/session_manager.py`).

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant API as POST /step
    participant SM as SessionManager
    participant PE as PraxisEnvironment
    participant CP as command_parser
    participant M as PraxisMemory
    participant SC as Scenario
    participant RE as RewardEngine

    C->>API: X-Session-Id, {command}
    API->>SM: get(session_id)
    alt missing session
        API-->>C: 400 No active session
    end
    API->>PE: step(PraxisAction(command))
    PE->>CP: parse_command(command)
    CP-->>PE: ParsedCommand(action_type, params)

    alt action_type in {save_finding, recall_memory}
        PE->>M: save / recall
        PE->>RE: score(memory.save_finding.<cutoff_state>) or<br/>score(memory.recall_memory.<cutoff_state>)
        M-->>PE: result_text
    else action_type in {query_logs, check_logs} and step >= cutoff
        PE->>RE: score(memory.illegal_log_after_cutoff)
        PE-->>PE: append [CONTEXT LIMIT] marker to result text
    else scenario action
        PE->>SC: step(parsed)
        SC->>RE: _score_event(event)
        SC-->>PE: StepOutcome
    end

    PE->>M: get_observation_context(step)
    PE-->>API: {observation, reward, done, info}
    API-->>C: 200 JSON
```

Observation rewrite rules (executed by `PraxisEnvironment.step`):

- If `step >= memory.CONTEXT_CUTOFF_STEP`, replace `observation.investigation_result` with `memory.get_observation_context(...)`.
- Always set `observation.memory_active = (step >= cutoff)`.
- Always set `observation.saved_findings_count = len(memory.saved_findings)`.

---

## 4. Reward composition (composable rubrics — RewardPolicy §8)

```mermaid
flowchart TD
    Event[Event tag emitted by scenario / memory / planner] --> Route{tag prefix?}
    Route -- "plan.* / checkpoint.*" --> PR[PlanningRubric 0.20]
    Route -- "memory.*" --> MR[MemoryRubric 0.20]
    Route -- "recovery.* / destructive_penalty" --> RR[RecoveryRubric 0.20]
    Route -- "diagnosis.* / remediation.* / submit_report.* / _resolved" --> TR[TerminalRubric 0.40]

    PR --> Comp[RewardBreakdown<br/>{planning, memory, recovery, terminal}]
    MR --> Comp
    RR --> Comp
    TR --> Comp

    Comp --> Step[subtract time_pressure_cost_per_step]
    Step --> Sum[weighted sum, weights == 1.0]
    Sum --> Clamp["clamp_reward → [0.01, 0.99]"]
    Clamp --> Out[per-turn reward + per-rubric breakdown]
    Out --> Score["compute_task_score = outcome_quality × (1 − steps/max_steps)<br/>(ADR-20 / Issue #23)"]
```

Memory events feed into `MemoryRubric` (see [`RewardPolicy.md`](./RewardPolicy.md) §1 + §8):

- `memory.save_finding.before_cutoff` → +0.05
- `memory.save_finding.after_cutoff` → +0.02
- `memory.recall_memory.before_cutoff` → +0.01
- `memory.recall_memory.after_cutoff` → +0.08
- `memory.illegal_log_after_cutoff` → −0.05 (log queries after cutoff)
- `memory.empty_recall_after_cutoff` → −0.02

Planning + Recovery + Terminal events are documented in [`RewardPolicy.md`](./RewardPolicy.md) §8 and `ScenarioCatalog.md` §3.6.

---

## 5. Episode terminator decision tree

```mermaid
flowchart TD
    Start[Step returns] --> Resolved{incident_resolved?}
    Resolved -- yes --> Done1[done = true]
    Resolved -- no --> Max{step >= MAX_STEPS?}
    Max -- yes --> Done2[done = true, max-steps timeout]
    Max -- no --> Esc{escalation with evidence?}
    Esc -- yes --> Done3[done = true, escalated]
    Esc -- no --> Cont[done = false, continue]
```

Driven by `BaseScenario.is_done()` plus the memory-aware `PraxisEnvironment` wrapper.

---

## 6. Cross-doc links

- Endpoints / schemas: [`APIContract.md`](./APIContract.md)
- Sessions + locking: [`ConcurrencyModel.md`](./ConcurrencyModel.md)
- Memory tool design: [`MemoryModel.md`](./MemoryModel.md)
- Per-task reward maps: [`RewardPolicy.md`](./RewardPolicy.md)
- Scenario inventory: [`ScenarioCatalog.md`](./ScenarioCatalog.md)
- Reset/step/done lifecycle: [`SessionLifecycle.md`](./SessionLifecycle.md)

---

## 7. Planning-action sequence (MissionOps phases)

> Issue #25 introduces 5 new commands: `create_plan`, `revise_plan`, `checkpoint`, `submit_report`, `request_clarification`. They route through the same `command_parser` → `PraxisEnvironment.step` path, but their reward tags are read by `PlanningRubric` / `RecoveryRubric` / `TerminalRubric` (RewardPolicy §8).

```mermaid
sequenceDiagram
    autonumber
    participant A as Agent
    participant API as POST /step
    participant PE as PraxisEnvironment
    participant CP as command_parser
    participant SC as MissionScenario
    participant AS as ArtifactStore
    participant PL as MissionPlan
    participant RE as RewardEngine

    Note over PE: phase = "Intake" / "Exploration"
    A->>API: command="check_runbook service=database"
    API->>PE: step(action)
    PE->>CP: parse → ParsedCommand(check_runbook, service=database)
    PE->>SC: step(parsed)
    SC->>AS: draw(kind="runbook", service="database", n=1)
    AS-->>SC: Artifact(body=..., source="rootly:...")
    SC-->>PE: StepOutcome(reward_tag="investigation.runbook_hit")
    PE-->>API: obs(phase="Exploration", artifact_excerpt=...)

    Note over PE: phase advances to "Planning"
    A->>API: command="create_plan milestones=[diag_db,diag_cdn,diag_worker,remediate_all]"
    API->>PE: step(action)
    PE->>CP: parse → ParsedCommand(create_plan, milestones=[...])
    PE->>PL: PL.create(milestones)
    PL-->>PE: ok
    PE->>RE: emit("plan.created_pre_cutoff") + "plan.covers_all_root_causes" if hit
    RE-->>PE: PlanningRubric.score += weighted

    Note over PE: phase = "Execution"
    A->>API: command="checkpoint milestone=diag_db"
    PE->>PL: PL.checkpoint("diag_db", world_state=...)
    PL-->>PE: consistent? true
    PE->>RE: emit("checkpoint.consistent")

    Note over PE: phase auto-shifts to "Disturbance" at step ~100
    A->>API: command="revise_plan replace=diag_db with=remediate_db"
    PE->>PL: PL.revise(...)
    PE->>RE: emit("recovery.replan_after_disturbance") + "plan.revised_after_evidence"

    Note over PE: phase = "Completion"
    A->>API: command="submit_report root_causes=[db,cdn,worker]"
    PE->>SC: validate(report, world_state)
    SC-->>PE: consistent? true
    PE->>RE: emit("submit_report.consistent_with_world_state")
    RE-->>PE: TerminalRubric.score = outcome_quality (high)
    PE-->>API: obs(done=true, reward=0.55, breakdown={planning, memory, recovery, terminal})
```

Key invariants:

- `create_plan` is only reward-positive if emitted before `CONTEXT_CUTOFF_STEP` (`PlanningRubric` reads the cutoff).
- `revise_plan` is reward-positive only if (a) new evidence has arrived since last plan, OR (b) emitted in Recovery phase after disturbance.
- `submit_report` mismatching world state ⇒ `TerminalRubric.score=0` ⇒ outcome × efficiency = 0 (ADR-20).
- `request_clarification` is rate-limited at 1/episode and surfaces the next deterministic artifact for the same service (so it never makes the env non-deterministic).

---

## 8. Live training loop (Unsloth + mtGRPO, Issue #31)

> Replaces the old plain-TRL diagram. ADR-19 / S35.

```mermaid
sequenceDiagram
    autonumber
    participant Tr as train_praxis_grpo.py
    participant U as Unsloth (fast Qwen2.5-7B)
    participant TRL as TRL GRPOTrainer<br/>+ environment_factory
    participant SM as SessionManager
    participant PE as PraxisEnvironment
    participant Trk as Trackio + WandB

    Tr->>U: load Qwen2.5-7B-Instruct (4-bit)
    Tr->>TRL: GRPOTrainer(<br/>  model=U,<br/>  environment_factory=PraxisToolEnv,<br/>  num_generations=8,<br/>  max_turns=150,<br/>  reward_model=mtGRPO_turn_credit<br/>)

    loop each training step
        TRL->>SM: 8 parallel allocate_session(task_name, seed=mix)
        SM->>PE: 8 PraxisEnvironment instances (one per session)

        loop each turn (≤150)
            TRL->>PE: step(action) per session
            PE->>RE: composable rubrics → RewardBreakdown per turn
            PE-->>TRL: obs, reward_per_rubric, done
        end

        TRL->>TRL: mtGRPO turn-level credit assignment<br/>policy gradient
        TRL->>Trk: log {step, mean_reward, planning, memory, recovery, terminal, loss}
    end

    TRL->>Tr: save adapter
    Tr->>Trk: final reward_curve.png + loss_curve.png
```

What changes vs plain GRPO:

- **Per-turn credit**: each of the 4 rubrics emits a value per turn; mtGRPO uses these for turn-level advantage rather than only end-of-episode credit. Stable on sparse-reward MissionOps.
- **Throughput**: Unsloth ~2.5× faster than vanilla HF + Flash-Attn for the same context length, fitting Colab T4/A10G budgets.
- **Public artefacts**: Trackio (private team) + WandB **public run** (judge-readable). Both URLs in README + ReleasePackage.md.

Rollback path: if Unsloth incompatible with the chosen model, fall back to TRL GRPOTrainer with a `turn_reward_aggregator` shim that approximates mtGRPO. Documented in Issue #31 Implementation notes.
