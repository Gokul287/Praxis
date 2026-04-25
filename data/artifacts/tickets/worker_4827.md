# Ticket #4827 — Worker memory leak after BATCH_SIZE bump (v5.9.0)

**Status**: closed (resolved)
**Severity**: P0
**Opened**: 2026-04-23 02:47 UTC
**Closed**: 2026-04-23 03:35 UTC

## Summary

Deploy `v5.9.0` raised `BATCH_SIZE` from 200 to 5000 to improve
throughput on the order-fulfilment topic. Per-job retained heap grew
~380 KiB beyond what the prior batch size produced, pushing worker
processes over the 2 GiB heap limit roughly every 45 seconds. Resulting
crash-loop wedged consumer fleet (0 healthy workers) and queue backlog
spiked to 243 k jobs.

## Resolution

1. Issued `rollback_deploy service=worker` to revert to v5.8.x.
2. After fleet propagation (~90 s), worker pool came up healthy and
   queue backlog drained at ~6 k jobs/min.
3. Filed follow-up to instrument per-job heap delta as a release-gate
   metric (FOLLOW-UP #4831).

## Lessons learned

- **A plain restart cannot recover from a batch-size-driven OOM.** The
  rollout inherits the same configuration; the OOM repeats within
  ~45 seconds. Rollback is mandatory.
- BATCH_SIZE changes need a heap-residency canary before fleet
  rollout.

## Tags

`worker_memory_leak`, `batch_size_regression`, `rollback_deploy`
