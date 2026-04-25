# Runbook: Worker OOM / Crash-Loop (SRE-WORK-033)

## Trigger conditions

- `worker_memory_leak`: heap growth > 100 KiB/job sustained, AND
- two or more `OOMKilled` events within 5 minutes, AND
- crash-loop pattern (restart count >= 5 within last hour).

## Recent context

- Deploy `v5.9.0` raised `BATCH_SIZE` from 200 to 5000 at 01:40 UTC.
- `HEAP_LIMIT_MB` was unchanged at 2048; per-job retained heap growth
  pushes total residency above the limit roughly every 45 seconds.

## Recommended remediation

1. Issue `rollback_deploy service=worker` to revert v5.9.0 -> v5.8.x.
2. Once the rollout completes (typically 90 seconds), restart the
   worker fleet so the pre-fork pool comes up clean.
3. Verify queue consumer lag drops below 10 seconds within 5 minutes.

## Why a plain restart is not enough

Restarting v5.9.0 inherits the same `BATCH_SIZE=5000` configuration and
the OOM repeats within ~45 seconds. The crash-loop will not converge
until the deploy is rolled back.
