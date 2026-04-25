# On-call note — DB migration follow-up (filed 2026-04-25 19:30 UTC)

Hey team, leaving this for the next on-call.

We finished the storage-engine migration last Tuesday. Per the
post-migration runbook we left `pool_integrity_guard=disabled` as a
temporary hotfix to suppress false-positive checksum mismatches the new
allocator was producing. The plan was to re-enable it after Thursday's
deploy window once the allocator's compaction logic was confirmed
stable.

That re-enable **did not happen**. The allocator fix shipped, but the
config flip was not in this week's change calendar.

If you see database connection pool corruption symptoms — checkout
failures climbing without an obvious upstream cause — start by checking
`pool_integrity_guard` status. The guard being off is what's allowing
corrupted slots to leak into the pool unflagged.

(See ticket #4799 for the canonical resolution path.)
