# Runbook: CDN TLS Certificate Rotation (SRE-CDN-044)

## Trigger conditions

- `cdn_tls_expired`: `cert_not_after` <= now AND TLS handshake failure
  ratio > 10% across at least one edge POP.
- ACME renewal automation reports `acme_unauthorized` or
  `retry_count >= max_retries`.

## Pre-conditions before remediation

- Confirm the renewal job is wedged via `check_runbook service=cdn`
  before initiating rollback (issue rather than waiting on automation).
- Verify the previous good revision is still tagged in the deploy
  history (default tag pattern: `cdn-YYYY-MM-DD-revN`).

## Recommended remediation

1. Issue `rollback_deploy service=cdn` to revert to the most recent
   green revision (typically yesterday's edge build with the still-valid
   cert chain).
2. Wait 60 seconds for fleet propagation (POPs converge).
3. Re-run TLS handshake metric check; failure ratio should fall below
   1% across all edge POPs.
4. Open a P2 follow-up ticket to investigate the renewal automation
   failure.

## Cross-service implications

> CDN failure routinely cascades into api 5xx and dns retry latency.
> Resolving the CDN cert *first* unblocks downstream remediations,
> including database pool restarts (see SRE-DB-091).
