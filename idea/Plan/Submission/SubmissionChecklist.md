# Submission Checklist — Phase 1 Auto-Validation + Beyond

> Everything that must be true before we click "Submit". Mirrors
> `idea/PROBLEM STATEMENT/How Judging works.md` (S3) and the external themes &
> criteria doc (S2).

---

## 1. Hard gates (DQ if any fail)

- [ ] **HF Space deploys** — automated ping returns 200; `/health` returns `{"status": "healthy"}`.
- [ ] **`openenv validate` passes** — `uv run openenv validate` exits 0 on the submitted commit.
- [ ] **Dockerfile builds** — `docker build .` succeeds on the submitted repo.
- [ ] **`inference.py` reproduces** — runs end-to-end without error and emits valid `[START]/[STEP]/[END]` lines.
- [ ] **3+ tasks with graders** — Praxis ships **6**: `single-service-alert`, `ambiguous-incident`, `cascading-failure`, `memory-leak`, `cascading-platform-failure`, `procedural-incident`. Each grader returns rewards in the open `(0.0, 1.0)` interval.
- [ ] **Graders are NOT constant** — `tests/test_scenarios.py` determinism + variance suite passes.
- [ ] **Runtime < 20 min** — `inference.py` for all 6 tasks totals under 20 min on `vCPU=2 / 8 GB`.
- [ ] **Mandatory env vars wired** — `API_BASE_URL`, `MODEL_NAME`, `HF_TOKEN` (S31).
- [ ] **OpenAI client used for LLM calls** — verified by `tests/test_inference.py`.
- [ ] **Stdout contract preserved** — `[START]/[STEP]/[END]` exactly per S3.
- [ ] **`inference.py` lives at repo root** — required by S31.

---

## 2. Required deliverables (S2 minimum submission)

- [ ] OpenEnv (latest release) used — `pyproject.toml` pins it.
- [ ] Training script using TRL (or Unsloth) — `train_praxis_grpo.py` (Issue #11).
- [ ] Evidence of training — reward curve OR score gap table (Issue #10/#12).
- [ ] Mini-blog on HuggingFace **OR** YouTube video < 2 minutes — Issue #20.
- [ ] HuggingFace Space (tagged `openenv`) — Issue #18.
- [ ] README that motivates the problem, explains the env, shows results — Issue #19.
- [ ] All additional materials (video, blog, slides) **linked from README** — Issue #19/#20.
- [ ] No big video files in the HF Hub repo — use URL references only.

---

## 3. README must contain (Issue #19 owns)

- [ ] One-line tagline + the "after step 30" hook.
- [ ] Problem statement (capability gap).
- [ ] Architecture diagram (mermaid — same one in [`DataFlow.md`](../Architecture/DataFlow.md)).
- [ ] Action / observation / state schemas (link to [`APIContract.md`](../Architecture/APIContract.md)).
- [ ] Task table (6 rows from [`ScenarioCatalog.md`](../Architecture/ScenarioCatalog.md)).
- [ ] Memory system explainer (link to [`MemoryModel.md`](../Architecture/MemoryModel.md)).
- [ ] 3-row score gap table inline.
- [ ] Reward curve image inline (or fallback note explaining S30 coverage).
- [ ] TRL `environment_factory` snippet (10–15 lines).
- [ ] arxiv citations (S28, S29, S30).
- [ ] Links: HF Space · Trackio run · mini-blog/video · slide deck.
- [ ] Quick-start: 5 commands from clone → running.

---

## 4. Pre-submission validation script

Run this from a clean clone before clicking submit:

```bash
# 1. Validate
uv sync
uv run openenv validate

# 2. Tests
pytest -q
# Expect: > 289 passed (existing) + memory/concurrent/scenario suites green.

# 3. Smoke
python -m uvicorn server.app:app --host 0.0.0.0 --port 7860 &
sleep 3
curl -s http://localhost:7860/health | grep healthy
curl -s -X POST http://localhost:7860/reset \
     -H "Content-Type: application/json" \
     -d '{"task_name":"cascading-platform-failure"}' | python -m json.tool
# Capture session_id, then exercise /step and /state with X-Session-Id header.

# 4. Inference
API_BASE_URL=... MODEL_NAME=... HF_TOKEN=... python inference.py

# 5. Docker
docker build -t praxis-env:submit .
docker run --rm -p 7860:7860 praxis-env:submit &
sleep 5
curl -s http://localhost:7860/health
```

All five steps must produce green output. Issue #17 packages this into `tests/smoke_test.py` so CI runs it.

---

## 5. Last-mile submission form

- [ ] HF Space URL: `https://huggingface.co/spaces/<org>/praxis-env`
- [ ] GitHub repo URL (with permanent commit hash, not just `main`).
- [ ] One mini-blog OR video link.
- [ ] Optional: slides URL.
- [ ] Team members: `@Gokul287`, `@GunaPalanivel`, `@snehasneha56526-arch`.

Per S2: _"Please make sure that the URL link of your environment is submitted as judges will pull the environment from the URL to evaluate it. Changes or commits after the submission deadline will not be considered."_ → freeze the commit hash; do not push fixes after submit.

---

## 6. Common failure modes we've already mitigated

| Risk                            | Mitigation in this repo                                                                     |
| ------------------------------- | ------------------------------------------------------------------------------------------- |
| Reward not bounded              | `clamp_reward` in `server/reward.py` and `BaseScenario.clamp_reward` (S11/S12).             |
| Grader non-deterministic        | No randomness in scenarios; procedural generator uses seeded `random.Random` (S11, ADR-07). |
| Docker build fails on HF        | Local `docker build` step in §4 is mandatory before submit.                                 |
| Stdout format wrong             | `tests/test_inference.py` enforces `[START]/[STEP]/[END]` (S31).                            |
| Concurrency corrupts state      | `SessionManager` + `SUPPORTS_CONCURRENT_SESSIONS=true` (Issue #1, ADR-04, S14).             |
| Hard task too easy for Nemotron | Mega-incident has 8 services, 3 root causes, 6 red herrings, 120 steps (Issue #7).          |
| Always-same grader              | Determinism receipt + per-task variance test in `tests/test_scenarios.py` (Issue #14).      |
