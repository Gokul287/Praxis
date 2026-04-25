# Screenplay Script — Live MissionOps Demo

> Beat sheet for the on-stage demo. Practice with a screen recording and a watch.
> Total runtime budget: **2 minutes 30 seconds** including the spoken close.
> The trophy moment is the **before-vs-after rollout chart at 1:30**.

---

## 1. Pre-show setup (5 minutes before)

- Open `https://huggingface.co/spaces/<org>/praxis-env` in tab 1; verify `/health` is 200.
- Open `docs/rollout_compare.png` in tab 2.
- Open `docs/demo.gif` (looping) in tab 3.
- Open the WandB **public** run URL in tab 4 (back-up: Trackio if WandB is private-only).
- Open `docs/baseline_scores.md` in tab 5 (4-row table: random / no-prompt / SRE-prompt / trained).
- Mirror to projector. Hide the dock / taskbar. Font ≥ 16pt.

---

## 2. Cue sheet

| Time  | Action                                                            | Spoken                                                                                                         |
| ----- | ----------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| 0:00  | Open with `docs/rollout_compare.png` on screen.                   | (silent — let the chart land for 2 seconds)                                                                    |
| 0:03  | Point at the two lines.                                           | Sentence 1: "Real incidents take hours and span artifacts. Praxis MissionOps is the only environment where agents have to plan, remember, and recover across the full mission." |
| 0:15  | Switch to `docs/demo.gif` (loop).                                 | Sentence 2: "Here is a baseline Qwen-7B agent. It wanders, queries logs after the cutoff, never plans — final score 0.04." |
| 0:30  | Stop the GIF on the trained-agent recall_memory frame.            | Sentence 3: "Same model after one mtGRPO run. It plans, saves three findings, recovers from a deploy disturbance, submits a consistent report — final score 0.31. A 7.7× lift." |
| 0:55  | Switch to live HF Space `/step` running `cascading-platform-failure`. | (silent — let the agent take 2 turns)                                                                          |
| 1:00  | Agent emits `create_plan milestones=...`.                         | "Notice — the agent creates a plan **before** the cutoff. That's the PlanningRubric firing."                   |
| 1:08  | `save_finding` × 3 around steps 12–22.                            | "Three findings saved while the log is still available."                                                       |
| 1:18  | Step 30 → `[CONTEXT LIMIT REACHED]` banner.                       | "And there it is — the full log is gone. Step 30."                                                             |
| 1:22  | Agent calls `recall_memory`.                                      | "It planned for this. The keys it saved 60 seconds ago are still here."                                        |
| 1:30  | Switch back to `docs/rollout_compare.png`.                        | Sentence 4: "Four composable rubrics — Planning, Memory, Recovery, Terminal — at 0.20, 0.20, 0.20, 0.40. Real Rootly logs feed the artifacts. Outcome × efficiency stops reward farming." |
| 1:55  | Switch to WandB public run.                                       | "And here's the training signal — public run on WandB. Trackio link is on the README."                        |
| 2:10  | Switch to `docs/baseline_scores.md`.                              | Sentence 5: "Anthropic's next Opus could literally train on this. Everything is in the README."                |
| 2:25  | Stop on the README link slide.                                    | (silent — invite questions)                                                                                    |
| 2:30  | End.                                                              | —                                                                                                              |

The trophy moment is the **chart at 1:30**, not the cutoff banner. The cutoff is supporting evidence; the chart is the proof.

---

## 3. The exact mission seed for the live demo

Reproducible without an LLM via `docs/rollout_trained.txt` and `docs/rollout_baseline.txt`. If the live model stalls, fall back to the deterministic replay (same `mission_id`, same `seed`, same observations + rewards).

```
TASK_NAME=cascading-platform-failure
SEED=2026
MISSION_ID=mission-2026-04-26-demo
MAX_STEPS=150
MEMORY_CUTOFF_OVERRIDE=30
```

The trajectory order shipped in `docs/rollout_trained.txt`:

```
1.   request_clarification topic=alert
2.   query_logs service=database timerange=15m         (Rootly excerpt #1 surfaces)
3.   check_runbook service=database                    (runbook hint #1 surfaces)
4.   save_finding key=db_pool_hint value=runbook_3.2_drain
5.   query_logs service=cdn timerange=15m              (Rootly excerpt #2)
6.   check_runbook service=cdn kind=ticket             (ticket hint #2)
7.   save_finding key=cdn_tls_hint value=ticket_4827
8.   query_logs service=worker timerange=15m
9.   check_metrics service=worker metric=memory
10.  save_finding key=worker_mem value=heap_growth_3MB_per_step
...
30.  [CONTEXT LIMIT REACHED] banner
31.  recall_memory
32.  create_plan milestones=[diag_db,diag_cdn,diag_worker,remediate_cdn,remediate_db,rollback_worker,restart_worker,submit]
33.  diagnose root_cause=cdn_tls_expired
40.  diagnose root_cause=db_pool_corrupted
50.  diagnose root_cause=worker_memory_leak
60.  restart_service cdn
70.  restart_service database
80.  rollback_deploy worker
85.  restart_service worker
~100 [DISTURBANCE] queue_backlog spike
105. revise_plan add=stabilize_queue
115. scale_resource service=queue
130. submit_report root_causes=[db_pool,cdn_tls,worker_memory] resolution=...
135. (mission resolves; final score 0.31)
```

---

## 4. What to show on each slide

| Slide | Visual                                                                      |
| ----- | --------------------------------------------------------------------------- |
| 1     | Praxis MissionOps logo + tagline + HF Space URL.                            |
| 2     | Mission shape diagram (8 phases) from `Architecture/ScenarioCatalog.md` §3.1. |
| 3     | `docs/rollout_compare.png` + `docs/demo.gif`.                               |
| 4     | The 4-rubric weight pie chart + outcome × efficiency formula.               |
| 5     | TRL `environment_factory` snippet + WandB + Trackio links.                  |

---

## 5. Recovery moves (if something breaks)

| Failure                       | Recovery                                                                                                              |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| HF Space cold-start times out | Switch to local Docker (`docker run -p 7860:7860 praxis-env:latest`) — same URL pattern.                              |
| Live agent hangs              | Switch to deterministic replay from `docs/rollout_trained.txt`; trajectory bytes-identical on cached prompts.         |
| Cutoff banner doesn't appear  | Check `step_count` in `/state`; if `< 30`, run `query_logs` a few times to bump the count.                            |
| WandB run link 404            | Show Trackio mirror; both URLs in `docs/training_links.md`.                                                           |
| Reward curve missing          | Show the 4-row baseline table from `docs/baseline_scores.md`; explain `FlawsToProduction` justified the formula change. |

---

## 6. Speaker notes (TechLead — Gokul)

- The chart at 1:30 is the trophy. Pause 2 seconds before speaking sentence 4.
- When the cutoff banner appears at 1:18, **pause 2 seconds**. Let it land.
- Don't read out the trajectory; describe the meta-level story.
- After sentence 5 immediately invite questions. The Q&A is where the storytelling 30% lands.

Run-through cadence: 3 silent dry runs + 2 with the spoken track. Total prep ~25 minutes.
