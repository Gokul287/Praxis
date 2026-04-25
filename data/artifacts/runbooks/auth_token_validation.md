# Runbook: Auth Token Validation Failures (SRE-AUTH-019)

## Use this when

- `auth` login timeout rate > 10% sustained for 60 seconds AND
- token validation latency p95 > 1 second.

## Cross-service correlation

Token validation depends on the database session table. When auth
latency rises with database checkout failures, prioritise the database
remediation (SRE-DB-091) - auth recovers automatically once the pool
returns to healthy state.

## Auth-only remediation

If the database is healthy:

1. Check `check_config service=auth` for recent secret rotations.
2. If rotation is in flight, force-roll the cluster's JWT signing keys
   back to the previous keypair.
3. Otherwise, scale auth replicas to absorb retries while the upstream
   degradation clears.
