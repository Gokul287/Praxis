"""
praxis_env.scenarios.ambiguous_incident - Task 3: Ambiguous Incident.

Difficulty: Medium
Severity: P2
Max Steps: 25

Incident Summary:
  Intermittent failures are affecting multiple services at once. The pattern
  is noisy on purpose: a recent application deploy looks suspicious, auth
  memory is elevated but still within normal operating range, and a known
  search bug is also present. The actual root cause is an internal DNS
  misconfiguration introduced during maintenance.

Agent must:
  1. Correlate failures across several services.
  2. Inspect infrastructure signals, especially DNS resolution failures.
  3. Diagnose the issue as a DNS misconfiguration.
  4. Resolve it by restarting dns-resolver or escalating with evidence.

Calibrated optimal path (9 steps): ~0.71
Calibrated fallback path (6 steps): ~0.551

Evidence rules:
    - Diagnosis is only rewarded after at least 3 app services have been
        investigated and at least one infrastructure service has been checked.
  - Escalation is only rewarded after the same evidence threshold.
  - Blind remediation is penalized to discourage guesswork.
"""

from __future__ import annotations

from praxis_env.scenarios.base import (
    BaseScenario,
    ParsedCommand,
    StepOutcome,
    get_metric_param,
    get_service_param,
)


class AmbiguousIncidentScenario(BaseScenario):
    """Task 3: Multiple services fail intermittently because DNS is misconfigured."""

    NAME = "ambiguous-incident"
    SEVERITY = "P2"
    MAX_STEPS = 25

    ALERT_SUMMARY = """\
## INCIDENT ALERT

**Alert ID**: MULTI-001
**Severity**: P2 - intermittent multi-service degradation
**Triggered**: 16:45 UTC
**Duration**: ~10 minutes and fluctuating

**Active symptoms**:
- frontend: intermittent 504s and NXDOMAIN errors
- api: intermittent connection failures
- auth: intermittent timeouts
- search: intermittent slowdowns and lookup failures

**Context**:
- Failures are intermittent, not a full outage
- A recent application deploy looks suspicious but is healthy
- DNS maintenance happened at 16:30 UTC
- The likely root cause is in infrastructure, not in any one app service

Investigate the shared failure pattern and resolve the incident.\
"""

    INITIAL_SYSTEM_STATUS = {
        "frontend": "degraded",
        "api": "degraded",
        "auth": "degraded",
        "search": "degraded",
        "dns-resolver": "degraded",
        "load-balancer": "healthy",
        "cache": "healthy",
        "database": "healthy",
    }

    INITIAL_AFFECTED_SERVICES = [
        "frontend",
        "api",
        "auth",
        "search",
        "dns-resolver",
    ]

    APP_SERVICES = frozenset({"frontend", "api", "auth", "search"})
    INFRA_SERVICES = frozenset({"dns-resolver", "load-balancer"})

    CORRECT_ROOT_CAUSES = frozenset(
        {
            "dns_misconfiguration",
            "dns_failure",
            "dns_resolver_corrupted",
            "dns_resolver_misconfigured",
        }
    )

    RED_HERRING_CAUSES = frozenset(
        {
            "api_deployment",
            "network_latency",
            "search_bug",
            "auth_memory",
        }
    )

    _LOGS = {
        "frontend": """\
16:35:12 [ERROR] Failed to resolve api.internal: NXDOMAIN
16:36:45 [INFO] Request succeeded to api.internal after retry
16:38:02 [ERROR] Failed to resolve auth.internal: NXDOMAIN
16:39:15 [INFO] Request succeeded to auth.internal after retry
16:41:10 [ERROR] Failed to resolve search.internal: NXDOMAIN
16:42:00 [WARN] Frontend saw intermittent DNS retry storms
""",
        "api": """\
16:35:10 [WARN] Upstream auth lookup timed out
16:35:12 [ERROR] Connection failed: api.internal lookup returned NXDOMAIN
16:36:00 [INFO] Request succeeded after retry
16:37:20 [ERROR] Failed to resolve database.internal: NXDOMAIN
16:39:00 [WARN] Latency spike appears intermittent, not constant
""",
        "auth": """\
16:35:05 [ERROR] LDAP lookup timed out
16:36:14 [INFO] Token validation succeeded after retry
16:37:01 [ERROR] Failed to resolve database.internal: NXDOMAIN
16:38:40 [WARN] Memory 82% - within normal operating range
""",
        "search": """\
16:35:40 [WARN] Known slow query: JIRA-4521 (long-standing issue)
16:36:05 [ERROR] Search backend lookup failed: NXDOMAIN
16:37:55 [INFO] Query completed after retry
16:39:20 [WARN] Intermittent slowdown persists
""",
        "dns-resolver": """\
16:30:00 [INFO] Maintenance window started
16:30:02 [INFO] TTL changed: 300s -> 3s
16:30:05 [ERROR] Replica 3 zone file corruption detected
16:30:06 [WARN] Replica 3 returning NXDOMAIN for *.internal
16:34:00 [WARN] NXDOMAIN rate rising across internal lookups
16:45:00 [ERROR] Resolution failures reached 33%
""",
        "load-balancer": """\
16:35:00 [INFO] Health checks pass
16:36:10 [WARN] Upstream targets flapping due to DNS retries
16:37:30 [INFO] Load balancer itself remains healthy
""",
        "cache": """\
16:35:00 [INFO] Cache hit rate 88%
16:36:30 [WARN] Miss rate rising because services are retrying DNS lookups
16:37:40 [INFO] Cache remains operationally healthy
""",
    }

    _METRICS = {
        ("frontend", "error_rate"): """\
error_rate (frontend)
  Current:  2.1%
  1h avg:   0.2%
  24h avg:  0.1%
  Pattern: intermittent spikes, not a sustained outage
""",
        ("api", "error_rate"): """\
error_rate (api)
  Current:  1.9%
  1h avg:   0.3%
  24h avg:  0.1%
  Pattern: errors move around as DNS retries succeed or fail
""",
        ("auth", "error_rate"): """\
error_rate (auth)
  Current:  2.2%
  1h avg:   0.4%
  24h avg:  0.1%
  Pattern: intermittent timeouts, not a steady regression
""",
        ("auth", "memory"): """\
memory (auth)
  Current:  82%
  1h avg:   79%
  24h avg:  76%
  Threshold: 90%  - NOT IN BREACH
""",
        ("search", "latency_p95"): """\
latency_p95 (search)
  Current:  620ms
  1h avg:   180ms
  24h avg:  160ms
""",
        ("dns-resolver", "resolution_failures"): """\
resolution_failures (dns-resolver)
  Current:  33%
  1h avg:   1%
  24h avg:  0%
  Threshold: 5%  - BREACH
""",
        ("load-balancer", "latency_p95"): """\
latency_p95 (load-balancer)
  Current:  45ms
  1h avg:   31ms
  24h avg:  30ms
""",
        ("cache", "cache_hit_rate"): """\
cache_hit_rate
  Current:  88%
  1h avg:   95%
  24h avg:  96%
""",
    }

    _DEPS = {
        "frontend": """\
frontend dependencies:
  -> api          [https://api.internal]      degraded due to retries
  -> auth         [https://auth.internal]     degraded due to retries
  -> search       [https://search.internal]   degraded due to retries
  -> dns-resolver [resolver.internal]         failing intermittently
  -> cache        [redis://cache.internal]    healthy
""",
        "api": """\
api dependencies:
  -> auth         [https://auth.internal]     degraded due to retries
  -> database     [postgres://db.internal]    healthy
  -> dns-resolver [resolver.internal]         failing intermittently
""",
        "auth": """\
auth dependencies:
  -> database     [postgres://db.internal]    healthy
  -> ldap         [ldap://ldap.internal]      healthy
  -> dns-resolver [resolver.internal]         failing intermittently
""",
        "search": """\
search dependencies:
  -> database     [postgres://db.internal]    healthy
  -> dns-resolver [resolver.internal]         failing intermittently
""",
        "dns-resolver": """\
dns-resolver dependencies: none
Downstream consumers: frontend, api, auth, search, load-balancer
""",
        "load-balancer": """\
load-balancer dependencies:
  -> dns-resolver [resolver.internal]         intermittent resolution failures
""",
        "cache": """\
cache dependencies: none
Downstream consumers: frontend, api, auth, search
""",
    }

    _CONFIGS = {
        "api": """\
Recent config changes for api:
  16:00:00 UTC - Deploy v4.0.1 by ci-bot
    Changes: feature flag for dark mode rollout
    Health checks: green after deploy
""",
        "auth": """\
Recent config changes for auth:
  No changes in the last 4 hours.
""",
        "search": """\
Recent config changes for search:
  Known issue: JIRA-4521 slow queries under load
  Last touched: 2 weeks ago
""",
        "dns-resolver": """\
Recent config changes for dns-resolver:
  16:30:00 UTC - Maintenance started
  16:30:02 UTC - TTL changed: 300s -> 3s
  16:30:05 UTC - Replica 3 zone file sync failed
""",
        "load-balancer": """\
Recent config changes for load-balancer:
  No changes in the last 24 hours.
""",
        "cache": """\
Recent config changes for cache:
  No changes in the last 24 hours.
""",
    }

    def _reset_scenario_state(self) -> None:
        self._done_investigations: set[str] = set()
        self._unique_services: set[str] = set()
        self._app_services_seen: set[str] = set()
        self._infra_services_seen: set[str] = set()

    def get_initial_observation_text(self) -> str:
        return ""

    _RUNBOOKS = {
        "frontend": """\
RUNBOOK: frontend (SRE-DOC-060)

Triage steps:
  1. Check upstream dependency health
  2. Check for NXDOMAIN or resolution failures in logs
  3. If multiple upstreams show the same error, check shared infrastructure
  4. Check recent deploys
""",
        "api": """\
RUNBOOK: api (SRE-DOC-042)

Triage steps:
  1. Check upstream dependency health (auth, database)
  2. Check recent deploys
  3. If errors correlate with other services, check shared infrastructure
""",
        "dns-resolver": """\
RUNBOOK: dns-resolver (SRE-DOC-010)

Triage steps:
  1. Check recent maintenance or config changes
  2. Check zone file sync status across replicas
  3. Check resolution failure rate (threshold: 5%)
  4. If failures correlate with maintenance window, check TTL and replica health
""",
    }

    def step(self, command: ParsedCommand) -> StepOutcome:
        action = command.action_type

        if action == "query_logs":
            return self._handle_query_logs(command)
        if action == "check_metrics":
            return self._handle_check_metrics(command)
        if action == "check_deps":
            return self._handle_check_deps(command)
        if action == "check_config":
            return self._handle_check_config(command)
        if action == "check_runbook":
            return self._handle_check_runbook(command)
        if action == "diagnose":
            return self._handle_diagnose(command)
        if action == "restart_service":
            return self._handle_restart_service(command)
        if action == "escalate":
            return self._handle_escalate(command)
        if action in ("rollback_deploy", "scale_resource", "kill_query"):
            return self._handle_wrong_remediation(command)
        return self._handle_unknown_command(command.raw)

    def _has_sufficient_evidence(self) -> bool:
        return len(self._app_services_seen) >= 3 and len(self._infra_services_seen) >= 1

    def _remember_service(self, service: str) -> None:
        if (
            service in self._LOGS
            or service in self._METRICS
            or service in self._DEPS
            or service in self._CONFIGS
        ):
            self._unique_services.add(service)
            if service in self.APP_SERVICES:
                self._app_services_seen.add(service)
            if service in self.INFRA_SERVICES:
                self._infra_services_seen.add(service)

    def _handle_query_logs(self, command: ParsedCommand) -> StepOutcome:
        service = get_service_param(command.params, default="frontend")
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
            self._remember_service(service)

        if service in self.APP_SERVICES:
            event = "investigation.query_logs.app"
        elif service == "dns-resolver":
            event = "investigation.query_logs.dns-resolver"
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
        service = get_service_param(command.params, default="frontend")
        metric = get_metric_param(command.params, default="error_rate")
        data = self._METRICS.get((service, metric))

        if data is None:
            score = self._score_event("invalid_input")
            return StepOutcome(
                investigation_result=(
                    f"No metric '{metric}' available for service '{service}'.\n"
                    "Available metrics: error_rate, latency_p95, memory, resolution_failures, cache_hit_rate"
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
            self._remember_service(service)

        if service == "dns-resolver" and metric == "resolution_failures":
            event = "investigation.check_metrics.dns-resolver.resolution_failures"
        elif service in self.APP_SERVICES:
            event = "investigation.check_metrics.app"
        elif service == "load-balancer":
            event = "investigation.check_metrics.load-balancer"
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
        service = get_service_param(command.params, default="frontend")
        data = self._DEPS.get(service)

        if data is None:
            score = self._score_event("invalid_input")
            return StepOutcome(
                investigation_result=f"No dependency data available for service '{service}'.",
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=self._incident_resolved,
                root_cause_identified=self._root_cause_identified,
            )

        key = f"deps:{service}"
        duplicate = key in self._done_investigations
        if not duplicate:
            self._done_investigations.add(key)
            self._remember_service(service)

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
        service = get_service_param(command.params, default="frontend")
        data = self._CONFIGS.get(service)

        if data is None:
            score = self._score_event("invalid_input")
            return StepOutcome(
                investigation_result=f"No config history available for service '{service}'.",
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=self._incident_resolved,
                root_cause_identified=self._root_cause_identified,
            )

        key = f"config:{service}"
        duplicate = key in self._done_investigations
        if not duplicate:
            self._done_investigations.add(key)
            self._remember_service(service)

        if service == "dns-resolver":
            event = "investigation.check_config.dns-resolver"
        elif service in self.APP_SERVICES:
            event = "investigation.check_config.app"
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
        """Handle the check_runbook command -- returns institutional knowledge."""
        service = get_service_param(command.params, default="frontend")
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
            self._remember_service(service)

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
        normalised = raw_cause.replace("-", "_").replace(" ", "_")

        if normalised in self.CORRECT_ROOT_CAUSES:
            if self._has_sufficient_evidence():
                self._root_cause_identified = True
                score = self._score_event("diagnosis.correct")
                return StepOutcome(
                    investigation_result=(
                        "Correct diagnosis. DNS misconfiguration confirmed after maintenance.\n\n"
                        "Root cause summary: TTL was reduced too aggressively and a replica\n"
                        "zone file failed to sync, causing intermittent NXDOMAIN responses\n"
                        "across internal services.\n\n"
                        "Next step: restart dns-resolver or escalate with evidence."
                    ),
                    reward=score.reward,
                    done=self.is_done(),
                    incident_resolved=False,
                    root_cause_identified=True,
                )

            score = self._score_event("diagnosis.wrong", premature=True)
            return StepOutcome(
                investigation_result=(
                    f"Incorrect timing: '{raw_cause}' may be plausible, but the evidence is not sufficient yet.\n\n"
                    "Investigate at least three app services and inspect the DNS layer before diagnosing."
                ),
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=False,
                root_cause_identified=False,
            )

        if normalised in self.RED_HERRING_CAUSES:
            if normalised == "api_deployment":
                detail = (
                    "Incorrect diagnosis: the api deploy is healthy. The failures are intermittent and"
                    " correlate with DNS lookups, not the release."
                )
            elif normalised == "auth_memory":
                detail = (
                    "Incorrect diagnosis: auth memory at 82% is within the normal range for retry pressure."
                    " It is a symptom, not the root cause."
                )
            elif normalised == "search_bug":
                detail = (
                    "Incorrect diagnosis: the known search bug exists, but it does not explain the"
                    " shared NXDOMAIN pattern across frontend, api, and auth."
                )
            else:
                detail = "Incorrect diagnosis: network latency is a symptom of retries, not the root cause."

            score = self._score_event("diagnosis.wrong", premature=True)
            return StepOutcome(
                investigation_result=detail,
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=False,
                root_cause_identified=False,
            )

        score = self._score_event("diagnosis.wrong", premature=True)
        return StepOutcome(
            investigation_result=(
                f"Incorrect diagnosis: '{raw_cause}'. The evidence points to the DNS layer, not a service-specific bug."
            ),
            reward=score.reward,
            done=self.is_done(),
            incident_resolved=False,
            root_cause_identified=False,
        )

    def _handle_restart_service(self, command: ParsedCommand) -> StepOutcome:
        service = get_service_param(command.params)

        if service != "dns-resolver":
            score = self._score_event("remediation.wrong", destructive=True)
            return StepOutcome(
                investigation_result=(
                    f"Restarting '{service}' does not address the incident. The failures are caused by DNS resolution issues."
                ),
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=False,
                root_cause_identified=self._root_cause_identified,
            )

        if not self._has_sufficient_evidence():
            score = self._score_event("remediation.wrong", premature=True)
            return StepOutcome(
                investigation_result=(
                    "Restarting dns-resolver now would be premature. Gather evidence from multiple services first."
                ),
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=False,
                root_cause_identified=self._root_cause_identified,
            )

        self._incident_resolved = True
        self._current_system_status = {
            service_name: "healthy" for service_name in self._current_system_status
        }
        score = self._score_event(
            "remediation.restart_service.dns-resolver", resolved=True
        )
        return StepOutcome(
            investigation_result=(
                "dns-resolver restarted successfully.\n\n"
                "- TTL cache reloaded\n"
                "- Replica 3 resynced its zone file\n"
                "- NXDOMAIN rate dropped and services recovered\n\n"
                "Incident resolved."
            ),
            reward=score.reward,
            done=True,
            incident_resolved=True,
            root_cause_identified=self._root_cause_identified,
            info={"resolution": "restart_dns_resolver"},
        )

    def _handle_escalate(self, command: ParsedCommand) -> StepOutcome:
        reason = command.params.get("reason", "")

        if not self._has_sufficient_evidence():
            score = self._score_event("escalation.no_evidence", premature=True)
            return StepOutcome(
                investigation_result=(
                    "Escalation filed without sufficient evidence. Gather at least three app services and an\n"
                    "infrastructure signal before escalating."
                ),
                reward=score.reward,
                done=True,
                incident_resolved=False,
                root_cause_identified=self._root_cause_identified,
            )

        self._incident_resolved = True
        self._current_system_status = {
            service_name: "healthy" for service_name in self._current_system_status
        }
        score = self._score_event("escalation.with_evidence", resolved=True)
        return StepOutcome(
            investigation_result=(
                f"Escalation accepted with evidence.\n\nReason: {reason}\n"
                f"App services investigated: {len(self._app_services_seen)}\n"
                f"Unique services investigated: {len(self._unique_services)}\n"
                f"Infrastructure services investigated: {len(self._infra_services_seen)}\n\n"
                "On-call has enough context to act on the DNS issue."
            ),
            reward=score.reward,
            done=True,
            incident_resolved=True,
            root_cause_identified=self._root_cause_identified,
            info={"resolution": "escalated_with_evidence"},
        )

    def _handle_wrong_remediation(self, command: ParsedCommand) -> StepOutcome:
        service = get_service_param(command.params)
        score = self._score_event("remediation.wrong", destructive=True)
        return StepOutcome(
            investigation_result=(
                f"Action '{command.action_type}' on '{service}' does not address the DNS outage pattern."
            ),
            reward=score.reward,
            done=self.is_done(),
            incident_resolved=False,
            root_cause_identified=self._root_cause_identified,
        )
