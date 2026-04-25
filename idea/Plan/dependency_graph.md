# Dependency Graph -- 21-Issue Wave Plan

> Three lanes (Guna / Gokul / Sneha) so the leads ship in parallel after #1
> lands. Quality > parallelism: a reviewer can hold a lane indefinitely. See
> `Project/DecisionLog.md` ADR-11 for the review policy.

---

## 1. Issue dependency DAG

```mermaid
graph TD
    I1[#1 Sessions] --> I2[#2 Schema]
    I1 --> I3[#3 PraxisMemory]
    I3 --> I4[#4 Parser actions]
    I3 --> I5[#5 Reward memory events]
    I3 --> I6[#6 Env hook + cutoff]
    I4 --> I6
    I5 --> I6
    I1 --> I7[#7 Mega-incident]
    I6 --> I7
    I1 --> I8[#8 Procedural generator]
    I7 --> I9[#9 Registry + openenv.yaml]
    I8 --> I9
    I1 --> I10[#10 SRE prompt + score gap]
    I10 --> I11[#11 GRPO training script]
    I11 --> I12[#12 50-step run + reward_curve.png]
    I3 --> I13[#13 Memory tests]
    I7 --> I14[#14 Mega + procedural tests]
    I8 --> I14
    I1 --> I15[#15 Concurrent-session tests]
    I16[#16 mock_validator cleanup]
    I9 --> I17[#17 Full server validation]
    I13 --> I17
    I14 --> I17
    I15 --> I17
    I17 --> I18[#18 Dockerfile + HF deploy]
    I18 --> I19[#19 README rewrite]
    I12 --> I19
    I19 --> I20[#20 Demo + blog/video + slides]
    I1 --> I21[#21 GET /benchmark]
    I10 --> I21
    I21 --> I19
```

---

## 2. Lane assignment (parallel-safe)

```mermaid
flowchart TB
    subgraph Guna[Guna lane -- Architect, reviewed by Gokul]
        G1[#1 Sessions]
        G2[#2 Schema]
        G3[#3 PraxisMemory]
        G6[#6 Env hook]
        G19[#19 README rewrite]
    end

    subgraph Gokul[Gokul lane -- TechLead, reviewed by Guna]
        K7[#7 Mega-incident]
        K8[#8 Procedural]
        K10[#10 SRE prompt]
        K11[#11 GRPO script]
        K12[#12 Reward curve]
        K18[#18 HF deploy]
        K20[#20 Demo + media]
        K21[#21 GET /benchmark]
    end

    subgraph Sneha[Sneha lane -- SDE, reviewed by Guna + Gokul + auto PR]
        S4[#4 Parser actions]
        S5[#5 Reward events]
        S9[#9 Registry + yaml]
        S13[#13 Memory tests]
        S14[#14 Scenario tests]
        S15[#15 Concurrent tests]
        S16[#16 Cleanup]
        S17[#17 Server validation]
    end

    G1 --> G2
    G1 --> G3
    G3 --> G6
    G19 --> Submit

    G1 --> K7
    K7 --> K8
    K8 --> K10
    K10 --> K11
    K11 --> K12
    K18 --> K20
    K10 --> K21
    K21 --> G19

    G3 --> S4
    G3 --> S5
    K8 --> S9
    G6 --> S13
    K8 --> S14
    G6 --> S15
    S14 --> S17
    S17 --> K18
    K12 --> G19
```

---

## 3. Critical path (single longest chain)

```
#1 -> #3 -> #6 -> #7 -> #9 -> #17 -> #18 -> #19 -> #20
```

Roughly 9 hours wall-clock with buffer. Anything off this chain is parallel-safe.

---

## 4. Wave-by-wave assignment table

| Wave | Time slot      | Guna (Architect)          | Gokul (TechLead)                  | Sneha (SDE)                        |
| ---- | -------------- | ------------------------- | --------------------------------- | ---------------------------------- |
| 1    | T+0:00 -> 1:00 | **#1 Sessions (BLOCKER)** | --                                | --                                 |
| 2    | T+1:00 -> 2:00 | #2 Schema                 | #7 Mega-incident (start)          | --                                 |
| 3    | T+2:00 -> 3:30 | #3 PraxisMemory           | #7 Mega-incident (finish)         | #4 Parser actions                  |
| 4    | T+3:30 -> 4:30 | #6 Env hook               | #8 Procedural generator           | #5 Reward events                   |
| 5    | T+4:30 -> 5:30 | --                        | #10 SRE prompt + score gap        | #9 Registry + yaml; #13 Mem tests  |
| 6    | T+5:30 -> 6:30 | --                        | #11 GRPO script                   | #14 Scenario tests; #15 Concurrent |
| 7    | T+6:30 -> 7:30 | --                        | #12 Reward curve (if GPU)         | #16 Cleanup; #17 Server validation |
| 8    | T+7:30 -> 8:30 | #19 README rewrite        | #18 HF deploy; #21 GET /benchmark | --                                 |
| 9    | T+8:30 -> 9:00 | --                        | #20 Demo + media                  | --                                 |

Sneha's PRs are reviewed by **both leads + auto PR review**; Guna's by Gokul; Gokul's by Guna.

`#21 GET /benchmark` is a thin read-only endpoint (depends on `#10` for `docs/baseline_scores.md` content and `#1` for the FastAPI app shape); it parallel-runs with `#18` in Gokul's Wave-8 tail and unblocks the README link block in `#19`. Quality > parallelism still applies.

---

## 5. Hard rules

- A PR cannot merge until its **Depends on** issues are closed.
- A PR cannot merge until required reviewers approve (per ADR-11).
- A PR cannot merge unless the **Plan docs to update** checklist in its body is satisfied (plan == reality).
- A PR cannot merge if it regresses the existing 289-test baseline.
