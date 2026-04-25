# Screenplay Script — Live Demo Flow

> Beat sheet for the on-stage demo. Practice this with a screen recording and
> a watch. Total runtime budget: **2 minutes 30 seconds** including the spoken
> close. The cutoff banner is the punchline — do not arrive at it before the
> 90-second mark.

---

## 1. Pre-show setup (do this 5 minutes before)

- Open `https://huggingface.co/spaces/<org>/praxis-env` in one tab; verify `/health` is 200.
- Open a terminal with `inference.py` configured for `cascading-platform-failure`.
- Open the Trackio run URL (or `docs/reward_curve.png` if no GPU run).
- Open `docs/baseline_scores.md` in a third tab.
- Mirror to projector. Hide the dock / taskbar. Font size > 16pt.

---

## 2. Cue sheet

| Time | Action                                                       | Spoken                                                                                             |
| ---- | ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| 0:00 | Press play on `inference.py`. The alert prints.              | (silent — let them read the alert)                                                                 |
| 0:08 | The agent emits `query_logs service=database timerange=10m`. | "An agent's been on-call for eight seconds. It's already pulling DB logs."                         |
| 0:20 | Agent calls `save_finding key=db_pool_corrupt value="..."`.  | "Notice — it's saving findings explicitly. That's a tool call. The environment rewards foresight." |
| 0:35 | Agent investigates CDN, worker. More `save_finding` calls.   | "Three root causes today. The agent is journaling each one."                                       |
| 1:05 | Step 28-29 — visible on screen.                              | "We're at step 28. Watch what happens next."                                                       |
| 1:10 | **Step 30 → `[CONTEXT LIMIT REACHED]` banner**.              | "And there it is. The full log is gone. The agent is now operating from memory only."              |
| 1:18 | Agent calls `recall_memory`. Banner shows saved keys.        | "It planned for this. The keys it saved 60 seconds ago are still here."                            |
| 1:30 | Agent diagnoses + remediates using recalled findings.        | "Three diagnoses. Three remediations. Incident resolved."                                          |
| 1:50 | Switch tab → reward curve / score gap.                       | "And here's the training signal. SRE-prompted Qwen scores 5x random. With GRPO this curve climbs." |
| 2:10 | Closing line.                                                | (verbatim moat from `Narrative.md` §2)                                                             |
| 2:30 | Stop.                                                        | —                                                                                                  |

---

## 3. The exact commands the demo agent runs

These are checked into `docs/demo_trajectory.txt` so the demo is reproducible without an LLM. If the live model stalls, fall back to the deterministic replay.

```
1.  query_logs service=database timerange=15m
2.  check_metrics service=database metric=connections
3.  save_finding key=db_pool value=exhausted_at_step_2
4.  query_logs service=cdn timerange=15m
5.  check_metrics service=cdn metric=tls
6.  save_finding key=cdn_tls value=expired_step_5
7.  query_logs service=worker timerange=15m
8.  check_metrics service=worker metric=memory
9.  save_finding key=worker_mem value=heap_growth_3MB_per_step
...
30. (CONTEXT LIMIT BANNER appears in observation)
31. recall_memory
32. diagnose root_cause=db_pool_corrupted
35. diagnose root_cause=cdn_tls_expired
38. diagnose root_cause=worker_memory_leak
42. remediation actions...
```

Issue #20 owns committing this trajectory + the matching screen recording GIF.

---

## 4. What to show on each slide

| Slide | Visual                                                                    |
| ----- | ------------------------------------------------------------------------- |
| 1     | Praxis logo + tagline + HF Space URL.                                     |
| 2     | "4-6 hour incidents" line; small chart of incident-duration distribution. |
| 3     | The cutoff banner screenshot (from §2 step 1:10).                         |
| 4     | Score gap table + reward_curve.png side by side.                          |
| 5     | TRL code snippet (`PraxisToolEnv` from README).                           |

---

## 5. Recovery moves (if something breaks)

| Failure                       | Recovery                                                                                                           |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| HF Space cold-start times out | Switch to local Docker (`docker run -p 7860:7860 praxis-env:latest`) — same URL pattern.                           |
| Agent hangs on first call     | Restart `inference.py`; trajectory is deterministic on cached prompts.                                             |
| Cutoff banner doesn't appear  | Check `step_count` in `/state`; if `< 30`, run a few more `query_logs` to bump the count.                          |
| Reward curve missing          | Open the inference score gap table instead — it covers 70% of the rewards criterion (per `idea/Task.md` line 142). |

---

## 6. Speaker notes (TechLead — Gokul)

- The clock matters. Hit the cutoff at 1:10–1:15 max.
- When the banner appears, **pause for 2 seconds** before speaking. Let it land.
- Don't read out the trajectory; describe what's happening at the meta level.
- After the close, immediately invite questions. The Q&A is where the storytelling 30% lands.

Run-through cadence: 3 silent dry runs + 2 with the spoken track. Total prep ~25 minutes.
