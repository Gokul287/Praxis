# Runbook: API 5xx Dependency Triage (SRE-API-021)

## Use this when

- `api` service shows 5xx error rate > 5% AND no recent `api` deploy
  is in progress (otherwise see deploy-rollback runbook).

## Triage order

API 5xx is almost always a downstream symptom. Check upstreams in this
order before diagnosing api itself:

1. **CDN** — `query_logs service=cdn` and look for TLS handshake errors
   or expired certs. CDN failures present at api as 502/503.
2. **Database** — `check_metrics service=database metric=connections`
   and look for pool checkout failures. DB pool corruption presents at
   api as 5xx with `db_session_init_failed` traces.
3. **Auth** — token-validation timeouts upstream of api show as login
   timeouts and `auth_verify_timeout` traces.

## When the cause is api itself

Open `check_config service=api` for recent deploys and feature flag
flips. Roll back the most recent change before scaling.
