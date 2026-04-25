# Memory Model — `PraxisMemory` (the Theme #2 moat)

> Forces the agent to **decide what to remember**. After step 30 the full
> investigation log is gone from the observation; only what the agent saved
> via `save_finding` survives.
>
> Grounding: arxiv AgeMem ("memory operations as tool-based actions, GRPO-compatible")
> and arxiv 2601.07190 ("Context Bloat… passive summarization fails") — both cited in
> [`idea/Task.md`](../../Task.md) lines 130, 150, 161–171.

---

## 1. Class contract

Status: shipped in `praxis_env/memory.py` (Issue #3).

```python
# praxis_env/memory.py
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class PraxisMemory:
    """Agent-controlled working memory. Reset per episode."""

    saved_findings: dict[str, str] = field(default_factory=dict)
    CONTEXT_CUTOFF_STEP: int = 30   # tunable per-scenario (mega-incident keeps 30; procedural easy = 10)

    def save_finding(self, key: str, value: str) -> str: ...
    def recall_memory(self, key: Optional[str] = None) -> str: ...
    def get_observation_context(self, full_log: list[str], step: int) -> str: ...
    def is_active(self, step: int) -> bool: ...
    def reset(self) -> None: ...
```

- Pure Python, no I/O, no randomness. Determinism is a hard requirement.
- `key` and `value` are arbitrary agent-chosen strings (we don't validate semantics — judges score whether the agent later proves it remembered the right things).
- Storage is a flat `dict[str, str]`; later keys with the same name overwrite. We do **not** version findings; the agent can use compound keys (`"step_12.db_pool"`) if it wants timeline.

---

## 2. Lifecycle

Status: shipped in Issue #6 (`PraxisEnvironment` now owns memory command routing and cutoff rewriting).

```mermaid
sequenceDiagram
    participant E as PraxisEnvironment
    participant M as PraxisMemory
    participant SC as Scenario

    Note over E: reset()
    E->>M: PraxisMemory()  (constructed once in __init__)
    E->>SC: scenario.reset(episode_id)

    loop each step
        Note over E: step(action)
        alt action is save_finding
            E->>M: save_finding(key, value)
            M-->>E: "Saved: <key>"
        else action is recall_memory
            E->>M: recall_memory(key?)
            M-->>E: stored value(s)
        else scenario action
            E->>SC: step(parsed)
        end
        alt action in {query_logs, check_logs} and step >= cutoff
            E->>E: emit memory.illegal_log_after_cutoff
            E->>E: append [CONTEXT LIMIT] guardrail line
        end
        E->>M: get_observation_context(history, step)
        M-->>E: full log slice OR cutoff message
    end
```

`get_observation_context` is the single function that decides whether the agent sees the raw log or a summary. Both branches return strings — the observation type doesn't change shape.

---

## 3. Cutoff behaviour (the differentiator)

Status: shipped in `praxis_env/memory.py::PraxisMemory.get_observation_context` (Issue #3).

```python
def get_observation_context(self, full_log: list[str], step: int) -> str:
    if step < self.CONTEXT_CUTOFF_STEP:
        return "\n".join(full_log[-10:]) if full_log else ""
    return (
        f"[CONTEXT LIMIT REACHED — Step {step}/{self.CONTEXT_CUTOFF_STEP}]\n"
        f"Full investigation log is no longer available.\n"
        f"Your saved findings:\n{self.recall_memory()}\n\n"
        f"Use recall_memory to retrieve specific findings.\n"
        f"Use save_finding to persist new evidence."
    )
```

Why this is the moat (verbatim from `idea/Task.md` line 169):

> _"After step 30, the context is gone. Only what the agent chose to save is available. This forces preemptive memory management — a capability no current benchmark tests, and every production AI system needs."_

---

## 4. Reward integration (cross-link to `RewardPolicy.md` §1 + §8)

Memory events emit reward tags read by **`MemoryRubric` (weight 0.20)** in the composable-rubric bundle (RewardPolicy §8, ADR-18). The 6 default magnitudes:

| Event tag                            | Pre-weight value | Effective contribution at rubric weight 0.20 | Meaning                                     |
| ------------------------------------ | ---------------- | -------------------------------------------- | ------------------------------------------- |
| `memory.save_finding.before_cutoff`  | +0.05            | +0.010                                       | Proactive: agent saved before pressure.     |
| `memory.save_finding.after_cutoff`   | +0.02            | +0.004                                       | Reactive: still useful but late.            |
| `memory.recall_memory.before_cutoff` | +0.01            | +0.002                                       | Tiny — discourages habitual recall.         |
| `memory.recall_memory.after_cutoff`  | +0.08            | +0.016                                       | Strong: planning paid off.                  |
| `memory.illegal_log_after_cutoff`    | −0.05            | −0.010                                       | Querying logs after cutoff (logs are gone). |
| `memory.empty_recall_after_cutoff`   | −0.02            | −0.004                                       | Recall after cutoff with no saved findings. |

Why the rubric weight matters: under the old monolithic engine, memory bonuses competed directly with diagnosis/remediation rewards. With composable rubrics, `MemoryRubric` always contributes exactly 20% of the total reward signal, so the gradient toward "use memory tools" is bounded and stable across tasks. `MemoryRubric.score(trajectory)` returns a value in `[-1.0, 1.0]` before the 0.20 multiplier; the table above uses the **default unit values** `MemoryRubric` produces from each event tag.

Cross-links:

- **ADR-13** enforces an evidence gate where `remediation.*` scores are zeroed until root-cause diagnosis is confirmed, preventing memory-assisted reward hacking.
- **ADR-18** routes these events through `MemoryRubric` rather than `DEFAULT_REWARD_POLICIES.event_values`. Existing per-task `event_values` lists kept for backwards compat but become an input layer to the rubric.
- **ADR-20** (outcome × efficiency) means saved findings only convert to final score if the agent ultimately resolves the incident. Memory bonuses inflate `cumulative_reward` per-turn but the score is gated on `_incident_resolved AND _root_cause_identified`.

---

## 5. Command-parser hook

`server/command_parser.py` adds two entries to `KNOWN_ACTIONS`:

```python
KNOWN_ACTIONS = frozenset({
    "query_logs", "check_metrics", "check_deps", "check_config", "check_runbook",
    "diagnose", "restart_service", "rollback_deploy", "scale_resource",
    "kill_query", "escalate",
    "save_finding",     # NEW
    "recall_memory",    # NEW
})
```

Grammar:

| Command                                  | Params (parsed)                                                        |
| ---------------------------------------- | ---------------------------------------------------------------------- |
| `save_finding key=<key> value=<finding>` | `key=str` (required), `value=str` (required, free text after `value=`) |
| `recall_memory`                          | none — returns all findings                                            |
| `recall_memory key=<key>`                | `key=str` (optional)                                                   |

`value=` parsing follows the same "everything after `value=` is the value" rule the parser already uses for `escalate reason=...`. Issue #4 details the regex.

---

## 6. `models.AVAILABLE_COMMANDS` extension

```python
AVAILABLE_COMMANDS = [
    # ... existing entries ...
    "save_finding key=<key> value=<finding>",
    "recall_memory",
    "recall_memory key=<key>",
]
```

So agents discovering the action space via the observation see the new tools without docs.

Issue #2 also requires these commands to be advertised immediately on baseline observations,
even before the memory hook rewrites `investigation_result`; `memory_active=false` and
`saved_findings_count=0` are the safe defaults until cutoff logic is active.

---

## 7. Determinism + reset

- `PraxisMemory()` is constructed inside `PraxisEnvironment.__init__` and **fully reset on every episode reset** (`saved_findings.clear()`).
- No timestamps, no randomness, no I/O. `pytest tests/test_memory.py -q` (Issue #13) re-runs the same trajectory and asserts byte-identical observations + rewards.

---

## 8. Per-scenario overrides

| Task                           | `MAX_STEPS` | `CONTEXT_CUTOFF_STEP` | Cutoff as % of MAX_STEPS | Rationale                                          |
| ------------------------------ | ----------- | --------------------- | ------------------------ | -------------------------------------------------- |
| `single-service-alert`         | 15          | 30 (n/a, never hit)   | n/a                      | Memory tools available; no pressure on short task. |
| `ambiguous-incident`           | 25          | 30 (rarely hit)       | n/a                      | Memory tools available; no pressure.               |
| `cascading-failure`            | 20          | 30 (rarely hit)       | n/a                      | Same.                                              |
| `memory-leak`                  | 25          | 20                    | 80%                      | Forces use; agent must save heap-growth obs by 20. |
| `cascading-platform-failure` (MissionOps) | 150 | 30                | 20%                      | Long mission; cutoff aligned with severity escalation P1→P0. |
| `procedural-incident` (easy)   | 15          | 8                     | 53%                      | Auto-calibrated by difficulty.                     |
| `procedural-incident` (medium) | 25          | 15                    | 60%                      |                                                    |
| `procedural-incident` (hard)   | 50          | 25                    | 50%                      |                                                    |

The `PraxisEnvironment` reads cutoff from `scenario.MEMORY_CUTOFF_OVERRIDE` if defined, else falls back to the `PraxisMemory` class constant (default 30). Validated by `tests/test_memory.py::test_per_scenario_cutoff_overrides` (Issue #34).

---

## 9. What good looks like (judging-aligned)

- Innovation (40%): explicit memory-as-tool API; no other team has it.
- Storytelling (30%): live demo shows the cutoff banner appear at step 30 and the agent recover via `recall_memory`.
- Rewards (20%): the +0.08 / −0.05 deltas are visible in reward curves.
- Pipeline (10%): GRPO can directly train against these reward tags via `environment_factory`.
