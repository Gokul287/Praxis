# Demo Narrative — The 5-Sentence MissionOps Pitch

> Verbatim, judge-ready. Memorise this. Beat: **mission → before-rollout → after-rollout → numbers → ask**.
>
> Source: `FlawsToProduction/Verdict.md` ("Praxis MissionOps"), ADR-16 (MissionOps pivot), ADR-19 (Unsloth/mtGRPO), ADR-20 (outcome × efficiency).

---

## 1. The 5-sentence pitch (verbatim, ~50 seconds)

> **Sentence 1 — Mission.** "Real production incidents take 4 to 6 hours and span runbooks, tickets, and on-call notes. Praxis MissionOps is the only environment where agents have to plan, remember, and recover across that full mission — not just answer one alert."
>
> **Sentence 2 — Before rollout.** "Here is a baseline Qwen-7B agent. It wanders, queries logs after the context window collapses, never plans, and gets a final score of 0.04."
>
> **Sentence 3 — After rollout.** "Here is the same model after one mtGRPO training run on Praxis. It calls `create_plan` early, saves three findings before the cutoff, recovers from a deploy disturbance, submits a consistent post-incident report, and scores 0.31 — a 7.7× lift."
>
> **Sentence 4 — How.** "Four composable rubrics — Planning, Memory, Recovery, Terminal — score the trajectory. Real Rootly production logs feed the artifacts. Outcome × efficiency stops the agent reward-farming."
>
> **Sentence 5 — Ask.** "Anthropic's next Opus could literally train on this. Everything is in the README — Trackio, WandB, the rollouts, and the HF Space."

Time it: aim for **48 seconds** spoken, leaving 12 seconds of breath / pause around the cutoff banner.

---

## 2. The before-and-after rollout (the trophy moment)

This is the moment judges remember. We render the comparison live or pre-recorded; either way, both rollouts land in `docs/`:

| Artifact | What's in it |
| --- | --- |
| `docs/rollout_baseline.txt` | Full text trajectory of baseline Qwen-7B — wandering, no plan, no save_finding, illegal_log_after_cutoff penalty, final score `0.04`. |
| `docs/rollout_trained.txt`  | Same seed, same mission, after Issue #32 mtGRPO training — `create_plan`, `save_finding` × 3, `[CONTEXT LIMIT]`, `recall_memory`, disturbance hit at step 100, `revise_plan`, `submit_report`, final score `0.31`. |
| `docs/rollout_compare.png`  | Side-by-side per-turn reward chart, both lines on same axes, baseline flat near 0, trained climbing to ~0.55 cumulative. |
| `docs/demo.gif`             | 8-second GIF of the moment when `[CONTEXT LIMIT REACHED]` banner appears and the trained agent calls `recall_memory` while baseline panics. |

The README opens with `docs/rollout_compare.png` then `docs/demo.gif` — no slide deck before the visual.

---

## 3. The slide deck (5 slides max)

| #   | Title                              | One-line takeaway                                                                                        |
| --- | ---------------------------------- | -------------------------------------------------------------------------------------------------------- |
| 1   | Praxis MissionOps                  | Long-horizon SRE missions: 80–150 turns, 8 phases, scattered instructions, real Rootly artifacts.        |
| 2   | The Capability Gap                 | Real incidents are missions. Agents collapse at step 30 from context bloat (memory) and from no plan.    |
| 3   | The Trophy: before vs after        | `docs/rollout_compare.png` + `docs/demo.gif`. 0.04 → 0.31 after one mtGRPO run.                          |
| 4   | Composable Rubrics                 | Planning / Memory / Recovery / Terminal at 0.20 / 0.20 / 0.20 / 0.40 weights. Score = outcome × efficiency. |
| 5   | What's Next + How To Train         | TRL `environment_factory`. Trackio + WandB public run links. ∞ tasks via procedural seed + Rootly draws. |

Slide assets live in [`EvidencePackage.md`](./EvidencePackage.md).

---

## 4. The README headline

```
# Praxis MissionOps: long-horizon SRE agent training
### Plan. Remember. Recover. Score = outcome × efficiency.
```

Followed immediately by `docs/rollout_compare.png` and `docs/demo.gif`. No paragraphs above the fold.

---

## 5. Anti-patterns (do not say these)

- ❌ "It's an SRE chatbot." — undersells; we are _training_ infrastructure.
- ❌ "It's like LangChain memory." — we control memory inside the env, not the framework.
- ❌ "Score is average reward." — judges read `FlawsToProduction`; we use outcome × efficiency now.
- ❌ "We made up the logs." — say "real Rootly production logs (Apache-2.0)" with attribution.
- ❌ "Reward is one number." — show the 4-rubric breakdown; that's the moat.

---

## 6. Q&A drill (rehearse three answers)

**Q1: "What changed from your old plan?"**

> "Three things. We rewrote `cascading-platform-failure` from a 120-step incident into a true 150-turn mission with planning, scattered instructions, hidden dependencies, and a disturbance phase that forces recovery. We split the monolithic reward into four composable rubrics. And we shipped real Rootly production logs as the artifact corpus. Everything is documented in `idea/Plan/Project/DecisionLog.md` ADR-16 to ADR-20."

**Q2: "Why mtGRPO instead of plain GRPO?"**

> "Mission rewards are sparse and the trajectory is 80 to 300 turns. Plain GRPO collapses without turn-level credit assignment. mtGRPO with Unsloth gives 2.5× throughput and stable gradients on long-horizon sparse-reward tasks. The reward curve in `docs/reward_curve.png` shows the gap."

**Q3: "Show me numbers."**

> "Open the README. Three baseline rows — random, no-prompt, SRE-prompt — score 0.02 / 0.06 / 0.18 under outcome × efficiency. The trained-agent row scores 0.31. Ratio is 7.7×. Same mission, same seed. The Trackio + WandB public run links are right under the table."

---

## 7. The first 10 seconds (visual-first)

Don't open with a slide. Open with `docs/rollout_compare.png` already on the projector.

1. Point at the **baseline** line — flat near zero.
2. Point at the **trained** line — climbs to ~0.55 cumulative.
3. Then start sentence 1 of the pitch.

The visual is what wins the room.

---

## 8. Speaker notes

- The clock matters. Hit the 5 sentences in 50 seconds. Pause 2 seconds after sentence 3 ("a 7.7× lift").
- When the cutoff banner appears in the live demo, **pause 2 seconds** before speaking.
- After sentence 5, immediately invite questions — Q&A is where the storytelling 30% lands.

Run-through cadence: 3 silent dry runs of the slide flow + 2 with the spoken track. Total prep ≤ 25 minutes.
