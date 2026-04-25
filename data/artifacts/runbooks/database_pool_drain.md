# Runbook: Database Connection Pool Drain (SRE-DB-091)

## Trigger conditions

- `db_pool_corrupted` symptom: client checkout failure rate sustained > 50%
  for at least 60 seconds, AND
- pool_integrity_guard reported `INVALID` or `DISABLED` AND
- corrupted_slots > 5% of pool size.

## Pre-conditions before remediation

> **HIDDEN DEPENDENCY** — do NOT restart the database while CDN TLS
> handshake failures are active on the same edge POPs. The restart
> sequence opens fresh TLS sessions to upstream replicas; if cdn certs
> are expired the restarting primary will fail handshake and re-enter
> a degraded state. Resolve `cdn_tls_expired` (rollback_deploy cdn) or
> wait for cert renewal before draining the database pool.

## Recommended remediation

1. Re-enable `pool_integrity_guard=enabled` (config-only change).
2. Issue `scale_resource service=database resource=connection_pool`
   to drain corrupted slots and grow the healthy pool by 50%.
3. Verify checkout success rate returns to >= 95% within 90 seconds.
4. If failures persist, escalate to DB on-call lead.

## Anti-patterns

- `restart_service service=database` is unsafe while cdn_tls_expired
  is active (see hidden dependency above). Use `scale_resource` instead.
- Avoid `kill_query` during pool corruption; killing in-flight queries
  while the allocator is in DEGRADED state can corrupt additional
  slots.
