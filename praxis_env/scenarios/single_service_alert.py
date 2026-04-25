"""
praxis_env.scenarios.single_service_alert — Task 1: Single Service Alert.

Difficulty: Easy
Severity: P2
Max Steps: 15

Incident Summary:
  Auth service error rate has spiked to 15% (from a healthy 0.1%).
  Root cause: a recent deployment introduced a bad database connection
  string (typo in the hostname — "auhdb" instead of "authdb").

Agent must:
  1. Investigate (query_logs + check_metrics OR check_config)
  2. Identify the root cause (bad_config OR config_typo)
  3. Remediate (rollback_deploy service=auth)

Red herrings:
  - Auth service looks like it could be a capacity issue (response times rising)
  - API service is also showing slightly elevated latency due to auth failures
    (symptom, not cause)

Scoring (optimal path = ~0.71):
  - First log query on auth:     +0.08
  - Check config (reveals typo): +0.10
  - Correct diagnosis:           +0.20
  - Correct remediation:         +0.25
    - Wrong diagnose:              0.00 (no credit)
    - Wrong remediation:           0.00 (no credit)
    - Escalate without evidence:   0.00 (no credit)
  - Escalate with evidence: +0.15 (alternative ending)
  - check_runbook:                +0.05 (institutional knowledge)
"""

from __future__ import annotations

from praxis_env.scenarios.base import (
    BaseScenario,
    ParsedCommand,
    StepOutcome,
    get_metric_param,
    get_service_param,
)


class SingleServiceAlertScenario(BaseScenario):
    """Task 1: A single auth service has elevated errors due to a bad deploy."""

    NAME = "single-service-alert"
    SEVERITY = "P2"
    MAX_STEPS = 15

    ALERT_SUMMARY = """\
## INCIDENT ALERT

**Alert ID**: AUTH-001
**Severity**: P2 -- Partial degradation (some users affected)
**Triggered**: 14:27 UTC
**Duration**: ~3 minutes and rising

**Alert**: Auth service error rate elevated
- Current: 15.2% errors (threshold: 5%)
- Affected operations: login, token validation, session refresh
- Impact: Approximately 15% of active users unable to authenticate

**Initial signals**:
- Auth service: critical
- API gateway: degraded (elevated 5xx responses)
- Payment service: healthy
- Database: healthy

Use the available commands to investigate and resolve the incident.\
"""

    INITIAL_SYSTEM_STATUS = {
        "auth": "critical",
        "api": "degraded",
        "payment": "healthy",
        "database": "healthy",
    }

    INITIAL_AFFECTED_SERVICES = ["auth", "api"]

    # ── Pre-computed investigation data ───────────────────────────────────────
    # All data is defined here — zero runtime randomness.

    _LOGS = {
        # Auth service logs — the key evidence is here
        "auth": """\
14:27:01 [ERROR] Connection refused: postgres://auhdb.internal:5432/authdb
14:27:02 [ERROR] Connection refused: postgres://auhdb.internal:5432/authdb
14:27:04 [ERROR] Connection refused: postgres://auhdb.internal:5432/authdb
14:27:06 [WARN]  Health check: database connectivity failing
14:27:10 [ERROR] Connection refused: postgres://auhdb.internal:5432/authdb
14:27:15 [ERROR] Token validation failed — database unreachable
14:27:22 [ERROR] Login attempt failed — database unreachable
14:27:30 [WARN]  Retrying database connection (attempt 3/3)... failed
14:27:31 [ERROR] Max retries exceeded. Authentication service degraded.
14:27:45 [ERROR] Connection refused: postgres://auhdb.internal:5432/authdb
14:28:00 [ERROR] Connection refused: postgres://auhdb.internal:5432/authdb
14:28:15 [WARN]  Auth service response time: 2340ms (threshold: 500ms)
""",
        # API gateway logs — symptom, not cause
        "api": """\
14:27:05 [WARN]  Upstream auth service returning 503
14:27:08 [WARN]  Upstream auth service returning 503
14:27:12 [ERROR] Failed to validate bearer token — auth service unavailable
14:27:20 [WARN]  Circuit breaker opened for auth service
14:27:35 [WARN]  5xx error rate elevated: 12.4%
14:28:00 [INFO]  Health check: auth → UNHEALTHY, payment → HEALTHY, db → HEALTHY
""",
        "payment": """\
14:27:00 [INFO]  Payment service operating normally
14:28:00 [INFO]  All systems healthy
""",
        "database": """\
14:27:00 [INFO]  Database: 23 active connections (pool: 100)
14:27:30 [INFO]  No new connections from auth service since 14:26:58
14:28:00 [INFO]  Database operating normally. No errors.
""",
    }

    _METRICS = {
        ("auth", "error_rate"): """\
error_rate
  Current (1m):  15.2%
  1h average:     8.1%
  24h average:    0.12%
  Threshold:      5.0%  BREACH
""",
        ("auth", "latency_p95"): """\
latency_p95
  Current:  2340ms
  1h avg:    890ms
  24h avg:   145ms
  SLO:       500ms  BREACH
""",
        ("auth", "connections"): """\
connections
  DB connections current: 0
  DB connections 1h ago:  18
""",
        ("api", "error_rate"): """\
error_rate (api-gateway)
  Current:  12.4%
  1h avg:    4.8%
  24h avg:   0.09%
""",
        ("api", "latency_p95"): """\
latency_p95 (api-gateway)
  Current:  1820ms
  1h avg:    312ms
  24h avg:   198ms
""",
        ("database", "connections"): """\
connections (database)
  Total active: 23
  From auth:     0
  From api:      4
  From payment:  8
  Max pool:    100 (utilisation: 23%)
""",
        ("database", "error_rate"): """\
error_rate (database)
  Current: 0.0%
  1h avg:  0.0%
""",
    }

    _DEPS = {
        "auth": """\
auth service dependencies:
  -> database  [postgres://auhdb.internal:5432/authdb]  FAILING -- host unreachable
  -> redis     [redis://cache.internal:6379]             healthy
  -> config    [vault://config.internal/auth]            healthy
""",
        "api": """\
api-gateway dependencies:
  -> auth     [http://auth.internal:8080]   UNHEALTHY (circuit breaker open)
  -> payment  [http://pay.internal:8080]    healthy
  -> database [not a direct dependency]
""",
        "database": """\
database has no upstream service dependencies.
Downstream consumers: auth, api (indirect), payment
""",
    }

    _CONFIGS = {
        "auth": """\
Recent config changes for auth service:

  14:23:15 UTC — Deploy v2.4.1 by deploy-bot
  Change: DATABASE_URL updated
    - Before: postgres://authdb.internal:5432/authdb
    + After:  postgres://auhdb.internal:5432/authdb   ← TYPO in hostname

  13:45:00 UTC -- Config: LOG_LEVEL changed INFO -> DEBUG (no impact)
  12:00:00 UTC -- Routine secret rotation (no impact)

Last known-good version: v2.4.0
""",
        "api": """\
Recent config changes for api-gateway:
  No changes in last 2 hours.
""",
        "database": """\
Recent config changes for database:
  No changes in last 24 hours.
""",
    }

    # ── Accepted answers ───────────────────────────────────────────────────────

    CORRECT_ROOT_CAUSES = frozenset(
        {
            "bad_config",
            "config_typo",
            "deploy_bad_config",
            "misconfiguration",
            "typo",
            "bad_deploy",
        }
    )

    CORRECT_REMEDIATION_ACTION = "rollback_deploy"
    CORRECT_REMEDIATION_SERVICE = "auth"

    # ── Per-episode state (reset each time) ───────────────────────────────────

    def _reset_scenario_state(self) -> None:
        self._done_investigations: set[str] = set()  # tracks unique rewarded queries
        self._wrong_diagnoses: int = 0

    # ── Step dispatch ─────────────────────────────────────────────────────────

    # ── Runbook data (institutional knowledge) ────────────────────────────

    _RUNBOOKS = {
        "auth": """\
RUNBOOK: auth (SRE-DOC-028)

Triage steps:
  1. Check recent deploys or config changes
  2. Check database connectivity (auth depends on DB for sessions)
  3. Check error rate and response times
  4. If DB-related, verify connection string and credentials

Common failure modes:
  - Bad deploy: errors start shortly after a release
  - Database connectivity: connection string misconfiguration
  - Memory pressure: GC pauses cause timeouts (only above 90%)
""",
        "api": """\
RUNBOOK: api-gateway (SRE-DOC-042)

Triage steps:
  1. Check upstream dependency health (auth, payment)
  2. If auth is unhealthy, follow auth runbook
  3. Check recent deploys
  4. Check rate limiting configuration
""",
    }

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
        elif action in (
            "restart_service",
            "rollback_deploy",
            "scale_resource",
            "kill_query",
        ):
            return self._handle_remediation(command)
        elif action == "escalate":
            return self._handle_escalate(command)
        else:
            return self._handle_unknown_command(command.raw)

    def get_initial_observation_text(self) -> str:
        return ""  # No prior investigation on first step

    # ── Command handlers ──────────────────────────────────────────────────────

    def _handle_query_logs(self, command: ParsedCommand) -> StepOutcome:
        service = get_service_param(command.params, default="auth")
        logs = self._LOGS.get(service)

        if logs is None:
            score = self._score_event("invalid_input")
            return StepOutcome(
                investigation_result=f"No log data available for service '{service}'.",
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=self._incident_resolved,
                root_cause_identified=self._root_cause_identified,
            )

        key = f"logs:{service}"
        duplicate = key in self._done_investigations
        if not duplicate:
            self._done_investigations.add(key)

        event = (
            "investigation.query_logs.auth"
            if service == "auth"
            else "investigation.query_logs.default"
        )
        score = self._score_event(event, duplicate=duplicate)

        return StepOutcome(
            investigation_result=logs,
            reward=score.reward,
            done=self.is_done(),
            incident_resolved=self._incident_resolved,
            root_cause_identified=self._root_cause_identified,
        )

    def _handle_check_metrics(self, command: ParsedCommand) -> StepOutcome:
        service = get_service_param(command.params, default="auth")
        metric = get_metric_param(command.params, default="error_rate")
        data = self._METRICS.get((service, metric))

        if data is None:
            score = self._score_event("invalid_input")
            return StepOutcome(
                investigation_result=(
                    f"No metric '{metric}' available for service '{service}'.\n"
                    f"Available metrics: error_rate, latency_p95, connections, "
                    f"memory, cpu, throughput"
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

        event = (
            "investigation.check_metrics.connections"
            if metric == "connections"
            else "investigation.check_metrics.default"
        )
        score = self._score_event(event, duplicate=duplicate)

        return StepOutcome(
            investigation_result=data,
            reward=score.reward,
            done=self.is_done(),
            incident_resolved=self._incident_resolved,
            root_cause_identified=self._root_cause_identified,
        )

    def _handle_check_deps(self, command: ParsedCommand) -> StepOutcome:
        service = get_service_param(command.params, default="auth")
        data = self._DEPS.get(service, f"No dependency data for service '{service}'.")

        key = f"deps:{service}"
        duplicate = key in self._done_investigations
        if not duplicate:
            self._done_investigations.add(key)

        score = self._score_event(
            "investigation.check_deps.default", duplicate=duplicate
        )

        return StepOutcome(
            investigation_result=data,
            reward=score.reward,
            done=self.is_done(),
            incident_resolved=self._incident_resolved,
            root_cause_identified=self._root_cause_identified,
        )

    def _handle_check_config(self, command: ParsedCommand) -> StepOutcome:
        service = get_service_param(command.params, default="auth")
        data = self._CONFIGS.get(service, f"No config history for service '{service}'.")

        key = f"config:{service}"
        duplicate = key in self._done_investigations
        if not duplicate:
            self._done_investigations.add(key)

        event = (
            "investigation.check_config.auth"
            if service == "auth"
            else "investigation.check_config.default"
        )
        score = self._score_event(event, duplicate=duplicate)

        return StepOutcome(
            investigation_result=data,
            reward=score.reward,
            done=self.is_done(),
            incident_resolved=self._incident_resolved,
            root_cause_identified=self._root_cause_identified,
        )

    def _handle_check_runbook(self, command: ParsedCommand) -> StepOutcome:
        """Handle the check_runbook command -- returns institutional knowledge."""
        service = get_service_param(command.params, default="auth")
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
        raw_cause = command.params.get("root_cause", "").lower().strip()
        # Normalise: hyphens → underscores, strip spaces
        normalised = raw_cause.replace("-", "_").replace(" ", "_")

        if normalised in self.CORRECT_ROOT_CAUSES:
            self._root_cause_identified = True
            score = self._score_event("diagnosis.correct")
            return StepOutcome(
                investigation_result=(
                    "✅ Correct diagnosis!\n\n"
                    "Root cause confirmed: A bad deployment at 14:23 UTC introduced "
                    "a typo in the database hostname (auhdb.internal instead of "
                    "authdb.internal). The auth service cannot connect to its database.\n\n"
                    "Next step: roll back the deployment."
                ),
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=False,  # Not resolved until remediation
                root_cause_identified=True,
            )
        else:
            self._wrong_diagnoses += 1
            score = self._score_event("diagnosis.wrong", premature=True)
            return StepOutcome(
                investigation_result=(
                    f"❌ Incorrect diagnosis: '{raw_cause}'.\n\n"
                    "The investigation data doesn't support this conclusion. "
                    "Review the logs and config changes more carefully."
                ),
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=False,
                root_cause_identified=False,
            )

    def _handle_remediation(self, command: ParsedCommand) -> StepOutcome:
        action = command.action_type
        service = get_service_param(command.params)

        # Correct: rollback the auth deployment
        if (
            action == self.CORRECT_REMEDIATION_ACTION
            and service == self.CORRECT_REMEDIATION_SERVICE
        ):
            self._incident_resolved = True
            self._current_system_status["auth"] = "healthy"
            self._current_system_status["api"] = "healthy"
            score = self._score_event(
                "remediation.rollback_deploy.auth",
                resolved=True,
            )
            return StepOutcome(
                investigation_result=(
                    "✅ Deployment rolled back successfully.\n\n"
                    "auth v2.4.1 → v2.4.0 (rollback complete)\n"
                    "- Database connection string restored: postgres://authdb.internal:5432/authdb\n"
                    "- Auth service reconnecting to database...\n"
                    "- Auth error rate: recovering → 0.8% and falling\n"
                    "- API gateway: circuit breaker closed, upstream healthy\n\n"
                    "Incident resolved. Auth service operating normally."
                ),
                reward=score.reward,
                done=True,
                incident_resolved=True,
                root_cause_identified=self._root_cause_identified,
                info={"resolution": "rollback", "version_restored": "v2.4.0"},
            )

        # Wrong service remediation
        elif action == self.CORRECT_REMEDIATION_ACTION:
            score = self._score_event("remediation.wrong", destructive=True)
            return StepOutcome(
                investigation_result=(
                    f"⚠️ Rolled back deployment on '{service}', but auth service is still "
                    f"critical. That wasn't the root cause service."
                ),
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=False,
                root_cause_identified=self._root_cause_identified,
            )

        # Restart instead of rollback — won't fix a config typo
        elif action == "restart_service" and service == "auth":
            score = self._score_event("remediation.wrong", destructive=True)
            return StepOutcome(
                investigation_result=(
                    "Auth service restarted, but it's immediately failing again.\n"
                    "Error: Connection refused: postgres://auhdb.internal:5432/authdb\n\n"
                    "Restart doesn't fix the underlying issue — the config typo persists."
                ),
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=False,
                root_cause_identified=self._root_cause_identified,
            )

        # Scale resource — irrelevant to this problem
        elif action == "scale_resource":
            score = self._score_event("remediation.wrong", destructive=True)
            return StepOutcome(
                investigation_result=(
                    "Scaling had no effect on auth error rate. "
                    "The problem isn't capacity — it's connectivity."
                ),
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=False,
                root_cause_identified=self._root_cause_identified,
            )

        else:
            score = self._score_event("remediation.wrong", destructive=True)
            return StepOutcome(
                investigation_result=f"Action '{action}' had no effect on the incident.",
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=False,
                root_cause_identified=self._root_cause_identified,
            )

    def _handle_escalate(self, command: ParsedCommand) -> StepOutcome:
        reason = command.params.get("reason", "")
        num_investigations = len(self._done_investigations)

        if num_investigations >= 3:
            # Escalated with reasonable evidence
            self._incident_resolved = True
            score = self._score_event("escalation.with_evidence", resolved=True)
            return StepOutcome(
                investigation_result=(
                    f"✅ Incident escalated to on-call lead with evidence.\n\n"
                    f"Reason provided: {reason}\n"
                    f"Investigations completed: {num_investigations}\n\n"
                    "Escalation accepted — on-call lead will drive resolution."
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
                    "⚠️ Escalation filed, but without sufficient evidence "
                    f"({num_investigations} investigation(s) completed, need ≥3).\n"
                    "On-call lead will have to investigate from scratch.\n\n"
                    "Tip: gather more evidence before escalating."
                ),
                reward=score.reward,
                done=True,
                incident_resolved=False,
                root_cause_identified=self._root_cause_identified,
            )
