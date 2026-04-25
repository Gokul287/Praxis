# Demo Narrative — The 60–90 Second Pitch

> Verbatim, judge-ready. Memorise this. Beat: problem → environment → moat → evidence → ask.
>
> Source: `idea/Task.md` lines 152–154 (the merged pitch) plus the moat statement at line 169.

---

## 1. Spoken pitch (verbatim)

> **"Production incidents can take 4 to 6 hours. Current AI agents fail at step 30 because their context fills up with noise.**
>
> **Praxis forces the agent to manage its own memory — save the important finding, discard the noise, recall what matters when you need it. After step 30, the full log is gone. Only what you chose to remember remains.**
>
> **And we reward the agent for thinking correctly through the whole trajectory, not just solving the final step.**
>
> **No other environment in this room tests preemptive memory management — and every production AI system needs it."**

Time: ~55 seconds spoken at moderate pace. Rehearse to land at 60.

---

## 2. The "after step 30" close (the moat)

After the live demo (see [`ScreenplayScript.md`](./ScreenplayScript.md)), close with:

> **"After step 30, the context is gone. Only what the agent chose to save is available. This forces preemptive memory management — a capability no current benchmark tests, and every production AI system needs."**

This is the line that makes Meta judges remember Praxis when they reconvene.

---

## 3. The slide deck (5 slides max)

| #   | Title                            | One-line takeaway                                                          |
| --- | -------------------------------- | -------------------------------------------------------------------------- |
| 1   | Praxis — Long-Horizon SRE Triage | Agents diagnose 120-step incidents under context pressure.                 |
| 2   | The Capability Gap               | Real incidents = 4-6 hrs. Agents collapse at step 30 from context bloat.   |
| 3   | Memory As A Tool                 | `save_finding` + `recall_memory` + cutoff at step 30. Show the banner.     |
| 4   | Evidence                         | Score gap table (random / no-prompt / SRE-prompt) + reward curve.          |
| 5   | What's Next                      | PyTorch-native via TRL `environment_factory`; ∞ tasks via procedural seed. |

Slide assets live in [`EvidencePackage.md`](./EvidencePackage.md).

---

## 4. The README headline

The home page must echo the same beats:

```
# Praxis: Long-Horizon SRE Agent Training
### Where plans span more steps than context windows
```

Followed by the "after step 30" demo GIF (Issue #20).

---

## 5. Anti-patterns (do not say these)

- ❌ "It's an SRE chatbot" — undersells; we are _training_ infrastructure.
- ❌ "It's like LangChain memory" — we control memory inside the env, not the framework.
- ❌ "We'll figure out training later" — the GRPO script + reward curve are the proof.
- ❌ "We're inspired by AgentBench / SWE-Bench" — judges have those memorised; differentiate on memory cutoff.

---

## 6. Three-question Q&A drill

**Q1: "Why is this PyTorch-native?"**

> "We expose a TRL `environment_factory` — a single import gives `GRPOTrainer` parallel rollouts on Praxis. The reward function is process-aware, so the gradient is informative every step, not just at episode end."

**Q2: "How is this not just another SRE benchmark?"**

> "Other SRE envs extend the number of steps. We _remove_ information at step 30. Either the agent planned its memory or it fails. That capability gap doesn't exist in any other public env."

**Q3: "Show me reward curves."**

> Pull up the Trackio dashboard. If GPU credits didn't arrive, show the 3-row inference score gap from `docs/baseline_scores.md` — it's a legitimate 20%-criterion proof per the GRPO survey ("process rewards are more informative than terminal rewards", `idea/Task.md` line 142).

---

## 7. Do this in the first 10 seconds of the pitch

Start with the live demo running on the projector. Don't open with a slide. Show:

1. The `cascading-platform-failure` alert firing.
2. The agent investigating, calling `save_finding key=db_pool value=exhausted`.
3. Step 30 → the **`[CONTEXT LIMIT REACHED]`** banner appears.
4. The agent calls `recall_memory` and uses the saved key.

Then start the spoken pitch over the live screen. The visual is what wins the room.
