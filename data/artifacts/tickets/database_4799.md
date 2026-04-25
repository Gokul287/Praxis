# Ticket #4799 — DB pool corruption resolved by integrity guard

**Status**: closed (resolved)
**Severity**: P1
**Opened**: 2026-04-12 03:14 UTC
**Closed**: 2026-04-12 04:02 UTC

## Summary

Database connection pool entered a `DEGRADED` state after a routine
maintenance patch flipped `pool_integrity_guard=disabled` as a temporary
hotfix. With the guard off, the allocator failed to detect corrupted
slots; client checkout failure rate climbed from 0% to 78% within 4
minutes.

## Resolution

1. Re-enabled `pool_integrity_guard=enabled` (config rollback).
2. Issued `scale_resource service=database resource=connection_pool`
   to drain corrupted slots and restore healthy pool size.
3. Pool checkout success returned to 99.4% within 90 seconds.

## Lessons learned

- **Never disable the integrity guard except as part of a coordinated
  storage migration.** The guard catches allocator bugs that the slow
  query log cannot.
- **Rolling restart of the database is unsafe while CDN TLS errors are
  active** — see runbook SRE-DB-091, hidden-dependency section.

## Tags

`db_pool_corrupted`, `integrity_guard`, `hotfix_rollback`
