"""
praxis_env.scenarios.cascading_failure — Task 2: Cascading Failure.

Difficulty: Hard
Severity: P1
Max Steps: 20

Incident Summary:
  Multiple services alerting simultaneously — API is returning 503s,
  Auth is timing out, Payment service is slow. Three alerts fired at once,
  which is the first sign this is a cascading failure, not isolated.

Root cause: A runaway analytics pipeline launched a full-table scan
  against the production database at 14:45 UTC. This exhausted the
  database connection pool (100/100 connections used), leaving nothing
  for API, Auth, and Payment to connect. All three degrade simultaneously.

Red herrings (by design):
  1. API deployment happened 30 minutes ago — looks suspicious but
     unrelated. Post-deploy health checks were green.
  2. Auth service memory at 85% — elevated but within threshold.
     Red herring because it looks like a memory leak.
  3. Cache hit rate dropped — downstream symptom, not cause.
  4. Notification service deploy at 14:35 — suspicious timing but
     notification errors are downstream of DB pool exhaustion.

Optimal path (7 steps, score ~ 0.458):
    1. query_logs service=api timerange=10m          -> 503s citing DB timeout    (+0.024)
    2. check_deps service=api                        -> api->database dependency  (+0.024)
    3. check_metrics service=database metric=connections -> pool 100/100!         (+0.074)
    4. query_logs service=database timerange=15m     -> slow query from analytics (+0.044)
    5. diagnose root_cause=db_connection_pool_exhausted -> CORRECT               (+0.134)
    6. kill_query service=database query_id=runaway_analytics                    (+0.084)
    7. scale_resource service=database resource=connection_pool                  (+0.074)
                                                                                                                                            Total:   ~0.458

Alternative valid ending:
    escalate with >=3 investigations -> +0.084
"""

from __future__ import annotations

from praxis_env.scenarios.base import (
    BaseScenario,
    ParsedCommand,
    StepOutcome,
    get_metric_param,
    get_service_param,
)


class CascadingFailureScenario(BaseScenario):
    """Task 2: Multiple services fail due to a runaway analytics query exhausting the DB pool."""

    NAME = "cascading-failure"
    SEVERITY = "P1"
    MAX_STEPS = 20

    ALERT_SUMMARY = """\
## MULTI-SERVICE INCIDENT

**Alert ID**: MULTI-001
**Severity**: P1 -- Major degradation (significant user impact)
**Triggered**: 14:47 UTC (3 alerts fired within 90 seconds)
**Duration**: ~5 minutes and worsening

**Active Alerts**:
- api-gateway:     HTTP 503 error rate 34% (threshold: 10%)
- auth:            Response timeout rate 28% (threshold: 5%)
- payment-service: Latency P95 = 8.4s (threshold: 2s)

**System status**:
- api:           critical
- auth:          critical
- payment:       degraded
- database:      degraded
- notification:  degraded
- analytics:     healthy (self-reported)
- cache:         degraded

**Context**:
- All 3 services began degrading within 90 seconds of each other
- API deployment v3.2.1 was released 30 minutes ago at 14:15 UTC
- Notification service was redeployed at 14:35 UTC
- This pattern (multi-service simultaneous degradation) suggests a shared dependency

Investigate the root cause. Multiple services are affected -- follow the dependency graph.\
"""

    INITIAL_SYSTEM_STATUS = {
        "api": "critical",
        "auth": "critical",
        "payment": "degraded",
        "database": "degraded",
        "notification": "degraded",
        "analytics": "healthy",
        "cache": "degraded",
    }

    INITIAL_AFFECTED_SERVICES = [
        "api",
        "auth",
        "payment",
        "database",
        "notification",
        "cache",
    ]

    # ── Pre-computed investigation data ───────────────────────────────────────
    # IMPORTANT DESIGN NOTE: Log and metric data intentionally omit explicit
    # "Note:" hints that reveal the root cause.  Agents must REASON across
    # multiple services and correlate timestamps, not just read a summary.

    _LOGS = {
        "api": """\
14:47:02 [ERROR] Upstream timeout: database connection refused
14:47:03 [ERROR] Upstream timeout: database connection refused
14:47:05 [ERROR] POST /api/login -> 503 (upstream auth timeout)
14:47:07 [ERROR] POST /api/payments -> 503 (upstream payment timeout)
14:47:10 [ERROR] DB connection pool timeout after 5000ms
14:47:12 [WARN]  Circuit breaker opening for database upstream
14:47:15 [ERROR] DB connection pool timeout after 5000ms
14:47:30 [ERROR] 503 rate: 34.2% (all routes affected)
14:47:45 [WARN]  Health check: database -> UNHEALTHY
14:48:00 [ERROR] Reject request: no DB connections available

Last healthy checkpoint: 14:45:30 UTC
""",
        "auth": """\
14:46:55 [WARN]  Database query timeout: SELECT * FROM sessions WHERE... (took 12s)
14:47:00 [ERROR] Auth: Cannot acquire database connection (pool full)
14:47:05 [ERROR] Token validation failed: database unreachable
14:47:10 [ERROR] Session lookup failed: database unreachable
14:47:15 [WARN]  Memory: 85% (threshold: 90%)
14:47:20 [ERROR] Login attempt rejected: database unavailable
14:47:30 [WARN]  Auth response time P95: 9200ms (SLO: 500ms)
14:47:45 [ERROR] Cannot acquire database connection
""",
        "payment": """\
14:46:58 [WARN]  Database connection slow: took 4200ms to acquire
14:47:05 [WARN]  Payment gateway latency elevated: 8400ms
14:47:10 [ERROR] Payment: database connection pool timeout
14:47:20 [WARN]  Retrying failed DB connection (1/3)
14:47:30 [WARN]  Retrying failed DB connection (2/3)
14:47:40 [ERROR] Payment: database all retries exhausted -- degraded mode
14:48:00 [WARN]  Payment operating in degraded mode (read-only cached data)
""",
        "database": """\
14:44:30 [INFO]  New long-running query started: PID 8847 (user: analytics)
14:44:35 [WARN]  Query PID 8847: full table scan on events table (3.2B rows)
14:45:00 [WARN]  Connection pool utilization: 45/100
14:45:30 [WARN]  Connection pool utilization: 72/100
14:46:00 [WARN]  Connection pool utilization: 91/100
14:46:30 [ERROR] Connection pool utilization: 100/100 -- FULL
14:46:45 [ERROR] Connection refused: pool exhausted -- new requests failing
14:47:00 [ERROR] Multiple services reporting connection timeouts
14:47:30 [ERROR] 38 queries queued waiting for connections
""",
        "notification": """\
14:35:10 [INFO]  Deploy v2.1.0 started (config: new SMTP relay endpoint)
14:35:25 [INFO]  Deploy v2.1.0 completed, health checks passing
14:46:50 [WARN]  Email notification: database connection timeout
14:47:02 [ERROR] Push notification: failed to write delivery receipt to DB
14:47:15 [ERROR] SMS gateway: delivery confirmation write failed (DB timeout)
14:47:30 [WARN]  Notification backlog growing: 142 undelivered
14:47:45 [ERROR] Batch delivery job failed: cannot acquire DB connection
14:48:00 [WARN]  Falling back to async retry queue
""",
        "analytics": """\
14:44:25 [INFO]  Analytics pipeline job started: weekly_event_aggregation
14:44:30 [INFO]  Connecting to production database
14:45:00 [INFO]  Running query: SELECT * FROM events WHERE date >= '2020-01-01'
14:45:30 [WARN]  Query running long (60s)
14:46:00 [WARN]  Query still running (90s)
14:46:30 [WARN]  Query still running (120s)
""",
        "cache": """\
14:46:45 [WARN]  Cache hit rate dropping: 94% -> 71%
14:47:00 [WARN]  Cache miss spike: elevated database retry traffic observed
14:47:30 [WARN]  Cache hit rate: 58% (normal: 95%)
14:48:00 [INFO]  Cache memory: 42% utilisation (healthy)
""",
    }

    _METRICS = {
        ("api", "error_rate"): """\
error_rate (api-gateway)
  Current (1m):  34.2%
  1h avg:         2.1%
  24h avg:        0.18%
  Threshold:     10.0%  BREACH
  Pattern: Error rate began rising at exactly 14:46:45 UTC.
""",
        ("api", "latency_p95"): """\
latency_p95 (api-gateway)
  Current:  9800ms
  1h avg:    180ms
  24h avg:   172ms
""",
        ("auth", "error_rate"): """\
error_rate (auth)
  Current:  28.4%
  1h avg:    0.9%
  24h avg:   0.12%
  Pattern: Errors began at 14:46:50 UTC.
""",
        ("auth", "memory"): """\
memory (auth)
  Current:  85%
  1h avg:   72%
  24h avg:  68%
  Threshold: 90%  NOT IN BREACH (but approaching)
""",
        ("auth", "connections"): """\
connections (auth -> database)
  Active DB connections:  0 (all requests failing to acquire)
  Failed connection attempts (last 5m): 847
  Pool wait timeout: 5000ms
""",
        ("payment", "latency_p95"): """\
latency_p95 (payment)
  Current:  8400ms
  1h avg:    310ms
  24h avg:   290ms
  SLO:       2000ms  BREACH
""",
        ("database", "connections"): """\
connections (database)
  POOL STATUS: 100/100 (FULL -- EXHAUSTED)
  Breakdown by client:
    analytics (PID 8847): 100 connections held
    api:                    0  (waiting)
    auth:                   0  (waiting)
    payment:                0  (waiting)
    notification:           0  (waiting)
  Max pool size: 100
  Queued requests: 38
""",
        ("database", "error_rate"): """\
error_rate (database)
  Connection refused rate: 38 req/min (from api, auth, payment, notification)
  Query error rate: 0.0% (queries execute fine once they get a connection)
""",
        ("database", "cpu"): """\
cpu (database)
  Current: 89%
  1h avg:  24%
  24h avg: 18%
""",
        ("notification", "error_rate"): """\
error_rate (notification)
  Current:  42.1%
  1h avg:    1.2%
  24h avg:   0.8%
  Pattern: Errors started at 14:46:50 UTC, shortly after 14:35 deploy.
""",
        ("analytics", "throughput"): """\
throughput (analytics)
  Current: 1 active job (weekly_event_aggregation)
  Status: RUNNING -- started 14:44:30 UTC
  Duration: 3m 45s (and still running)
""",
        ("cache", "cache_hit_rate"): """\
cache_hit_rate
  Current:  58%  (normal: 95%)
  1h avg:   91%
  24h avg:  94%
""",
    }

    _DEPS = {
        "api": """\
api-gateway dependencies:
  -> auth      [http://auth.internal:8080]         UNHEALTHY
  -> database  [postgres://db.internal:5432]       POOL EXHAUSTED
  -> payment   [http://payment.internal:8080]      DEGRADED
  -> cache     [redis://cache.internal:6379]       DEGRADED
  -> analytics [internal -- no direct dependency]  healthy
""",
        "auth": """\
auth dependencies:
  -> database  [postgres://db.internal:5432]  POOL EXHAUSTED
  -> cache     [redis://cache.internal:6379]  DEGRADED
""",
        "payment": """\
payment dependencies:
  -> database  [postgres://db.internal:5432]  POOL EXHAUSTED (fallback to cache)
  -> cache     [redis://cache.internal:6379]  DEGRADED (partially available)
""",
        "database": """\
database upstream dependencies: none (root data layer)
Downstream consumers:
  -> api          (connection failures)
  -> auth         (connection failures)
  -> payment      (connection failures, using cache fallback)
  -> notification (connection failures)
  -> analytics    (holding connections)
""",
        "notification": """\
notification dependencies:
  -> database  [postgres://db.internal:5432]  POOL EXHAUSTED
  -> smtp      [smtp://relay.internal:587]    healthy
""",
        "analytics": """\
analytics dependencies:
  -> database  [postgres://db.internal:5432]  holding connections
""",
        "cache": """\
cache dependencies: none (uses memory only)
Downstream consumers: api, auth, payment, notification
""",
    }

    _CONFIGS = {
        "api": """\
Recent config changes for api-gateway:
  14:15:00 UTC -- Deploy v3.2.1 by ci-bot
    Changes: Updated OAuth2 token refresh logic, dependency version bumps
    Health checks: All green post-deploy (verified at 14:20, 14:30, 14:40 UTC)

  13:00:00 UTC -- Config: Rate limit thresholds updated (no issues)
""",
        "notification": """\
Recent config changes for notification:
  14:35:00 UTC -- Deploy v2.1.0 by ci-bot
    Changes: Updated SMTP relay endpoint, added SMS delivery receipts
    Health checks: Green post-deploy (verified at 14:36, 14:37, 14:38 UTC)
    Errors started: ~14:47 UTC (12 minutes after deploy)
""",
        "database": """\
Recent config changes for database:
  No config changes in last 48 hours.

  ACTIVE SESSIONS:
  PID 8847 -- connected at 14:44:30 UTC (user: analytics)
    Query: SELECT * FROM events WHERE date >= '2020-01-01'
    No connection limit configured for analytics user.
    No query timeout configured.
""",
        "analytics": """\
Recent config changes for analytics:
  14:44:20 UTC -- Job triggered: weekly_event_aggregation (scheduled job)
  Config: No connection_limit set, no query_timeout set, no circuit breaker

  This job has always run against the production database.
""",
        "auth": """\
Recent config changes for auth:
  No changes in last 4 hours.
  Memory at 85% -- has been trending upward this week.
""",
    }

    # ── Runbook data (P1 feature: institutional knowledge) ────────────────────

    _RUNBOOKS = {
        "api": """\
RUNBOOK: api-gateway (SRE-DOC-042)

Triage steps:
  1. Check if deploy happened in last 2 hours -- if yes, check post-deploy health
  2. Check upstream dependency health (auth, database, payment)
  3. If multiple upstreams are unhealthy, investigate shared dependencies
  4. Check database connection pool status

Common failure modes:
  - Bad deploy: errors start immediately after release
  - Upstream cascade: errors follow upstream dependency failures
  - Rate limiting: errors concentrated on specific routes
""",
        "database": """\
RUNBOOK: database (SRE-DOC-015)

Triage steps:
  1. Check connection pool utilization (threshold: 80%)
  2. Check for long-running queries: pg_stat_activity
  3. Check CPU and memory -- sustained >85% needs attention
  4. Check recent config changes or schema migrations

Common failure modes:
  - Pool exhaustion: usually caused by long-running queries or connection leaks
  - Lock contention: blocked transactions pile up
  - Disk I/O: slow queries under heavy write load
""",
        "auth": """\
RUNBOOK: auth (SRE-DOC-028)

Triage steps:
  1. Check database connectivity (auth depends on DB for sessions)
  2. Check memory -- threshold is 90%, normal range is 60-80%
  3. Check recent deploys or config changes
  4. If DB-dependent, follow database runbook

Common failure modes:
  - Database unavailable: session lookups fail
  - Memory pressure: GC pauses cause timeouts (only above 90%)
  - Token cache miss storms: rare, check cache hit rate
""",
        "notification": """\
RUNBOOK: notification (SRE-DOC-055)

Triage steps:
  1. Check SMTP relay connectivity
  2. Check database connectivity (delivery receipts)
  3. Check recent deploys
  4. If errors correlate with other services, check shared dependencies

Common failure modes:
  - SMTP timeout: check relay health
  - DB connection failure: cannot write delivery receipts
  - Deploy regression: errors start immediately after release
""",
    }

    # ── Accepted answers ───────────────────────────────────────────────────────

    CORRECT_ROOT_CAUSES = frozenset(
        {
            "db_connection_pool_exhausted",
            "database_connection_pool_exhausted",
            "connection_pool_exhaustion",
            "runaway_query",
            "analytics_query",
            "runaway_analytics_query",
            "db_pool_exhausted",
            "database_pool_exhausted",
        }
    )

    # Red herring wrong answers the scenario anticipates
    RED_HERRING_CAUSES = frozenset(
        {
            "api_deployment",
            "bad_deploy",
            "deploy_issue",
            "api_deploy",
            "memory_pressure",
            "auth_memory",
            "cache_failure",
            "cache_miss",
            "notification_failure",
            "notification_deploy",
        }
    )

    # ── Per-episode state ──────────────────────────────────────────────────────

    def _reset_scenario_state(self) -> None:
        self._done_investigations: set[str] = set()
        self._query_killed: bool = False
        self._pool_scaled: bool = False

    # ── Step dispatch ─────────────────────────────────────────────────────────

    def step(self, command: ParsedCommand) -> StepOutcome:
        action = command.action_type

        if action == "query_logs":
            return self._handle_query_logs(command)
        elif action == "check_metrics":
            return self._handle_check_metrics(command)
        elif action == "check_deps":
            return self._handle_check_deps(command)
        elif action == "check_config":
            return self._handle_check_config(command)
        elif action == "check_runbook":
            return self._handle_check_runbook(command)
        elif action == "diagnose":
            return self._handle_diagnose(command)
        elif action == "kill_query":
            return self._handle_kill_query(command)
        elif action == "scale_resource":
            return self._handle_scale_resource(command)
        elif action == "restart_service":
            return self._handle_restart_service(command)
        elif action == "rollback_deploy":
            return self._handle_rollback_deploy(command)
        elif action == "escalate":
            return self._handle_escalate(command)
        else:
            return self._handle_unknown_command(command.raw)

    def get_initial_observation_text(self) -> str:
        return ""

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _handle_query_logs(self, command: ParsedCommand) -> StepOutcome:
        service = get_service_param(command.params, default="api")
        logs = self._LOGS.get(service)

        if logs is None:
            score = self._score_event("invalid_input")
            return StepOutcome(
                investigation_result=f"No log data for service '{service}'.",
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=self._incident_resolved,
                root_cause_identified=self._root_cause_identified,
            )

        key = f"logs:{service}"
        duplicate = key in self._done_investigations
        if not duplicate:
            self._done_investigations.add(key)

        if service == "api":
            event = "investigation.query_logs.api"
        elif service == "database":
            event = "investigation.query_logs.database"
        elif service == "analytics":
            event = "investigation.query_logs.analytics"
        else:
            event = "investigation.query_logs.default"
        score = self._score_event(event, duplicate=duplicate)

        return StepOutcome(
            investigation_result=logs,
            reward=score.reward,
            done=self.is_done(),
            incident_resolved=self._incident_resolved,
            root_cause_identified=self._root_cause_identified,
        )

    def _handle_check_metrics(self, command: ParsedCommand) -> StepOutcome:
        service = get_service_param(command.params, default="database")
        metric = get_metric_param(command.params, default="connections")
        data = self._METRICS.get((service, metric))

        if data is None:
            score = self._score_event("invalid_input")
            return StepOutcome(
                investigation_result=(
                    f"No metric '{metric}' for service '{service}'.\n"
                    "Available: error_rate, latency_p95, connections, memory, cpu, "
                    "throughput, cache_hit_rate"
                ),
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=self._incident_resolved,
                root_cause_identified=self._root_cause_identified,
            )

        key = f"metric:{service}:{metric}"
        duplicate = key in self._done_investigations
        if not duplicate:
            self._done_investigations.add(key)

        if service == "database" and metric == "connections":
            event = "investigation.check_metrics.database.connections"
        else:
            event = "investigation.check_metrics.default"
        score = self._score_event(event, duplicate=duplicate)

        return StepOutcome(
            investigation_result=data,
            reward=score.reward,
            done=self.is_done(),
            incident_resolved=self._incident_resolved,
            root_cause_identified=self._root_cause_identified,
        )

    def _handle_check_deps(self, command: ParsedCommand) -> StepOutcome:
        service = get_service_param(command.params, default="api")
        data = self._DEPS.get(service, f"No dependency data for '{service}'.")

        key = f"deps:{service}"
        duplicate = key in self._done_investigations
        if not duplicate:
            self._done_investigations.add(key)

        event = (
            "investigation.check_deps.core"
            if service in ("api", "auth", "payment")
            else "investigation.check_deps.default"
        )
        score = self._score_event(event, duplicate=duplicate)

        return StepOutcome(
            investigation_result=data,
            reward=score.reward,
            done=self.is_done(),
            incident_resolved=self._incident_resolved,
            root_cause_identified=self._root_cause_identified,
        )

    def _handle_check_config(self, command: ParsedCommand) -> StepOutcome:
        service = get_service_param(command.params, default="api")
        data = self._CONFIGS.get(service, f"No config history for '{service}'.")

        key = f"config:{service}"
        duplicate = key in self._done_investigations
        if not duplicate:
            self._done_investigations.add(key)

        if service == "database":
            event = "investigation.check_config.database"
        elif service == "analytics":
            event = "investigation.check_config.analytics"
        else:
            event = "investigation.check_config.default"
        score = self._score_event(event, duplicate=duplicate)

        return StepOutcome(
            investigation_result=data,
            reward=score.reward,
            done=self.is_done(),
            incident_resolved=self._incident_resolved,
            root_cause_identified=self._root_cause_identified,
        )

    def _handle_check_runbook(self, command: ParsedCommand) -> StepOutcome:
        """Handle the check_runbook command — returns institutional knowledge."""
        service = get_service_param(command.params, default="api")
        data = self._RUNBOOKS.get(service)

        if data is None:
            score = self._score_event("invalid_input")
            return StepOutcome(
                investigation_result=f"No runbook available for service '{service}'.",
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=self._incident_resolved,
                root_cause_identified=self._root_cause_identified,
            )

        key = f"runbook:{service}"
        duplicate = key in self._done_investigations
        if not duplicate:
            self._done_investigations.add(key)

        score = self._score_event(
            "investigation.check_runbook.default", duplicate=duplicate
        )

        return StepOutcome(
            investigation_result=data,
            reward=score.reward,
            done=self.is_done(),
            incident_resolved=self._incident_resolved,
            root_cause_identified=self._root_cause_identified,
        )

    def _handle_diagnose(self, command: ParsedCommand) -> StepOutcome:
        raw = command.params.get("root_cause", "").lower().strip()
        normalised = raw.replace("-", "_").replace(" ", "_")

        if normalised in self.CORRECT_ROOT_CAUSES:
            self._root_cause_identified = True
            score = self._score_event("diagnosis.correct")
            return StepOutcome(
                investigation_result=(
                    "Correct diagnosis.\n\n"
                    "Root cause confirmed: database connection pool exhaustion caused "
                    "by a runaway query.\n\n"
                    "Next steps: kill the runaway query and scale the connection pool."
                ),
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=False,
                root_cause_identified=True,
            )
        elif normalised in self.RED_HERRING_CAUSES:
            score = self._score_event("diagnosis.wrong", premature=True)
            if "api_deployment" in normalised or "deploy" in normalised:
                detail = (
                    "Incorrect diagnosis: the API deployment has been healthy with clean "
                    "post-deploy checks. API errors started 31 minutes after the deployment."
                )
            elif "memory" in normalised:
                detail = (
                    "Incorrect diagnosis: auth memory is elevated but within operating "
                    "parameters (below 90% threshold)."
                )
            elif "notification" in normalised:
                detail = (
                    "Incorrect diagnosis: notification service errors started at the same time "
                    "as other services. The notification deploy at 14:35 was healthy for 12 "
                    "minutes before errors began."
                )
            elif "cache" in normalised:
                detail = (
                    "Incorrect diagnosis: cache hit rate dropped but cache itself is "
                    "operationally healthy (memory at 42%)."
                )
            else:
                detail = f"Incorrect diagnosis: '{raw}'. The evidence doesn't support this conclusion."

            return StepOutcome(
                investigation_result=detail,
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=False,
                root_cause_identified=False,
            )
        else:
            score = self._score_event("diagnosis.wrong", premature=True)
            return StepOutcome(
                investigation_result=(
                    f"Incorrect diagnosis: '{raw}'.\n"
                    "Review the evidence across affected services."
                ),
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=False,
                root_cause_identified=False,
            )

    def _handle_kill_query(self, command: ParsedCommand) -> StepOutcome:
        service = get_service_param(command.params, default="database")
        query_id = command.params.get("query_id", "").lower().strip()

        if service != "database":
            score = self._score_event("remediation.wrong", destructive=True)
            return StepOutcome(
                investigation_result=f"kill_query: service '{service}' doesn't support this command.",
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=False,
                root_cause_identified=self._root_cause_identified,
            )

        # Accept any query_id that suggests the runaway analytics query
        analytics_ids = {
            "runaway_analytics",
            "8847",
            "analytics",
            "analytics_pipeline",
            "weekly_event_aggregation",
            "runaway",
            "8847pid",
        }
        query_id_norm = query_id.replace("-", "_").replace(" ", "_")

        if (
            query_id_norm in analytics_ids
            or "analytic" in query_id_norm
            or "runway" in query_id_norm
        ):
            self._query_killed = True
            # Update system status partially
            if self._current_system_status.get("api") == "critical":
                self._current_system_status["api"] = "degraded"
            if self._current_system_status.get("auth") == "critical":
                self._current_system_status["auth"] = "degraded"

            # If pool was already scaled AND query killed, resolve
            done_now = self._pool_scaled  # fully resolved only if both done
            if done_now:
                self._incident_resolved = True
                self._current_system_status = {
                    k: "healthy" for k in self._current_system_status
                }

            score = self._score_event(
                "remediation.kill_query.database",
                resolved=done_now,
            )

            return StepOutcome(
                investigation_result=(
                    "Runaway query killed.\n\n"
                    "PID 8847 (analytics_pipeline) terminated.\n"
                    "- Database connection pool: 100/100 -> 0/100 (all connections freed)\n"
                    "- Services are recovering\n\n"
                    + (
                        "Incident fully resolved. Services recovering to healthy state."
                        if done_now
                        else "Services are partially recovering (Critical -> Degraded). Consider scaling the connection pool to prevent recurrence."
                    )
                ),
                reward=score.reward,
                done=done_now,
                incident_resolved=done_now,
                root_cause_identified=self._root_cause_identified,
            )
        else:
            # Wrong query ID but right service — no reward, no penalty
            score = self._score_event("invalid_input")
            return StepOutcome(
                investigation_result=(
                    f"Query '{query_id}' not found or already completed.\n"
                    "Check database logs for active long-running queries."
                ),
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=False,
                root_cause_identified=self._root_cause_identified,
            )

    def _handle_scale_resource(self, command: ParsedCommand) -> StepOutcome:
        service = get_service_param(command.params, default="database")
        resource = command.params.get("resource", "").lower().strip()

        if service == "database" and resource in (
            "connection_pool",
            "connections",
            "pool",
            "db_connections",
        ):
            self._pool_scaled = True
            done_now = self._query_killed  # only resolve if both done
            if done_now:
                self._incident_resolved = True
                self._current_system_status = {
                    k: "healthy" for k in self._current_system_status
                }

            score = self._score_event(
                "remediation.scale_resource.database.connection_pool",
                resolved=done_now,
            )

            return StepOutcome(
                investigation_result=(
                    "Database connection pool scaled.\n\n"
                    "Connection pool: 100 -> 200 (doubled)\n"
                    "- Future analytics jobs limited to 50 connections\n"
                    "- Production services guaranteed minimum 150 connections\n\n"
                    + (
                        "Incident fully resolved. All services recovered to healthy state."
                        if done_now
                        else "Pool scaled. The runaway query is still holding connections."
                    )
                ),
                reward=score.reward,
                done=done_now,
                incident_resolved=done_now,
                root_cause_identified=self._root_cause_identified,
            )
        else:
            score = self._score_event("remediation.wrong", destructive=True)
            return StepOutcome(
                investigation_result=(
                    f"scale_resource: '{resource}' on '{service}' had no effect on the incident."
                ),
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=False,
                root_cause_identified=self._root_cause_identified,
            )

    def _handle_restart_service(self, command: ParsedCommand) -> StepOutcome:
        service = get_service_param(command.params)
        score = self._score_event("remediation.wrong", destructive=True)
        return StepOutcome(
            investigation_result=(
                f"Restarted '{service}', but it immediately begins failing again.\n"
                "The underlying issue persists."
            ),
            reward=score.reward,
            done=self.is_done(),
            incident_resolved=False,
            root_cause_identified=self._root_cause_identified,
        )

    def _handle_rollback_deploy(self, command: ParsedCommand) -> StepOutcome:
        service = get_service_param(command.params)
        if service == "api":
            message = (
                "API deployment v3.2.1 rolled back to v3.2.0. "
                "But api, auth, and payment are still failing — the incident continues."
            )
        elif service == "notification":
            message = (
                "Notification v2.1.0 rolled back to v2.0.9. "
                "But notification errors persist along with other services."
            )
        else:
            message = f"Rolled back '{service}' but the incident continues."
        score = self._score_event("remediation.wrong", destructive=True)
        return StepOutcome(
            investigation_result=message,
            reward=score.reward,
            done=self.is_done(),
            incident_resolved=False,
            root_cause_identified=self._root_cause_identified,
        )

    def _handle_escalate(self, command: ParsedCommand) -> StepOutcome:
        reason = command.params.get("reason", "")
        num_investigations = len(self._done_investigations)

        if num_investigations >= 3:
            self._incident_resolved = True
            score = self._score_event("escalation.with_evidence", resolved=True)
            return StepOutcome(
                investigation_result=(
                    f"Escalated with evidence to on-call lead.\n\n"
                    f"Reason: {reason}\n"
                    f"Evidence gathered: {num_investigations} investigation(s)\n\n"
                    "On-call lead will drive resolution with full context provided."
                ),
                reward=score.reward,
                done=True,
                incident_resolved=True,
                root_cause_identified=self._root_cause_identified,
            )
        else:
            score = self._score_event("escalation.no_evidence", premature=True)
            return StepOutcome(
                investigation_result=(
                    f"Escalated without sufficient evidence ({num_investigations} investigation(s), need >=3).\n"
                    "On-call lead will have to start from scratch."
                ),
                reward=score.reward,
                done=True,
                incident_resolved=False,
                root_cause_identified=self._root_cause_identified,
            )
