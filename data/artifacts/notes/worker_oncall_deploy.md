# On-call note — worker BATCH_SIZE deploy follow-up (filed 2026-04-23 04:12 UTC)

Closing the loop on tonight's incident (#4827).

Deploy v5.9.0 raised `BATCH_SIZE` from 200 to 5000. Per-job retained
heap grew enough that workers OOM'd ~every 45 seconds. Plain restarts
re-inherited the bad config, so the only path that converged was
`rollback_deploy service=worker` to revert to v5.8.x.

If you see worker crash-loops with the v5.9.x deploy tag, do **not**
restart — you'll just burn time on a loop that can't break out of
itself. Roll back first, then file a follow-up to investigate the heap
delta before re-attempting v5.9.x with smaller BATCH_SIZE deltas
(target: 200 -> 800 -> 2000 over three deploys instead of 200 -> 5000
in one).

The follow-up is FOLLOW-UP #4831 — please link any related findings
there.
