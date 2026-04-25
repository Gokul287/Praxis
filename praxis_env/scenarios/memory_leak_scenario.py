"""
praxis_env.scenarios.memory_leak_scenario — Task 4: Memory Leak under load.

Difficulty: Hard
Severity: P2
Max Steps: 25

Incident Summary:
  The async 'worker' service is experiencing periodic crashes and high latency processing jobs.

Root cause: A recent configuration change increased `batch_size` from 100 to 5000. Under peak
  load, this causes the Node.js event loop to block and exhaust the heap, leading to OOM
  crashes and severe GC pauses.

Red herrings:
  1. The DB latency is slightly elevated (caused by the worker holding connections during GC pauses).
  2. A memory leak in a different, low-priority 'metrics-agent' which is a known issue but not causing this.
  3. API service shows 502 Bad Gateway intermittently (because the worker pod is restarting).

Optimal path (score ~0.475):
    1. query_logs service=worker timerange=10m      -> See GC pauses and OOMKilled  (+0.035)
    2. check_metrics service=worker metric=memory    -> Sawtooth pattern at 99%      (+0.085)
    3. check_config service=worker                   -> Discovers batch_size=5000    (+0.035)
    4. diagnose root_cause=large_batch_size_oom     -> CORRECT                       (+0.135)
    5. rollback_deploy service=worker OR scale_resource service=worker resource=memory (+0.185)
"""

from __future__ import annotations

from praxis_env.scenarios.base import (
    BaseScenario,
    ParsedCommand,
    StepOutcome,
    get_metric_param,
    get_service_param,
)


class MemoryLeakScenario(BaseScenario):
    """Task 4: A worker service crashes repeatedly due to an OOM leak from a bad config."""

    NAME = "memory-leak"
    SEVERITY = "P2"
    MAX_STEPS = 25

    ALERT_SUMMARY = """\
## ASYNC PIPELINE DEGRADATION

**Alert ID**: MEM-042
**Severity**: P2 -- Significant degradation
**Triggered**: 08:30 UTC
**Duration**: Intermittent over the last 4 hours, now continuous

**Active Alerts**:
- worker:         Job processing latency P95 > 15s (threshold: 3s)
- worker:         Pod restart loop detected (CrashLoopBackOff)
- api-gateway:    HTTP 502 Bad Gateway rate 2.4% (threshold: 1%)

**System status**:
- api:           degraded
- worker:        critical
- database:      healthy
- metrics-agent: degraded
- cache:         healthy

**Context**:
- The worker service processes async jobs from the API.
- Customer support reports jobs are taking several minutes to complete or failing silently.
- 502 errors on the API coincide with worker instances dropping off the network.

Investigate the root cause and remediate the worker instability.\
"""

    INITIAL_SYSTEM_STATUS = {
        "api": "degraded",
        "worker": "critical",
        "database": "healthy",
        "metrics-agent": "degraded",
        "cache": "healthy",
    }

    INITIAL_AFFECTED_SERVICES = ["api", "worker", "metrics-agent"]

    _LOGS = {
        "worker": """\
08:29:10 [INFO]  Processing job batch...
08:29:12 [WARN]  [WARN] memory threshold reached: 92%
08:29:15 [WARN]  GC pause: 2.4s (allocation failed)
08:29:20 [WARN]  GC pause: 4.1s (allocation failed)
08:29:26 [ERROR] FATAL ERROR: Ineffective mark-compacts near heap limit Allocation failed - JavaScript heap out of memory
08:29:26 [ERROR] Worker process died (signal: SIGKILL, OOMKilled)
08:29:45 [INFO]  --- Pod restart ---
08:29:50 [INFO]  Worker starting up... connected to DB
08:30:10 [INFO]  Processing job batch...
08:30:15 [WARN]  [WARN] memory threshold reached: 94%
08:30:20 [WARN]  GC pause: 3.2s
""",
        "api": """\
08:29:26 [ERROR] Upstream worker disconnected unexpectedly: connection reset by peer
08:29:26 [ERROR] POST /v1/jobs -> 502 Bad Gateway
08:29:30 [WARN]  Worker pool size reduced to 2 instances
08:29:40 [ERROR] Request timeout polling job status
08:29:50 [INFO]  Worker pool recovered instance
""",
        "database": """\
08:29:20 [WARN]  Client 'worker' holding transaction open for 15s
08:29:26 [WARN]  Client 'worker' connection closed unexpectedly (EOF)
08:29:30 [INFO]  Cleaning up orphaned transactions...
""",
        "metrics-agent": """\
08:20:00 [WARN]  Memory leak detected in local buffer
08:25:00 [WARN]  Buffer capacity at 80%
08:30:00 [WARN]  Buffer capacity at 99%, dropping telemetry frames
(Note: this is a known low-severity issue, unrelated to the worker crashes)
""",
    }

    _METRICS = {
        ("worker", "memory"): """\
memory (worker)
  Current:  99% (Container limit: 2GB)
  Pattern:  SAWTOOTH. Memory climbs linearly over 60 seconds from 30% to 99%, followed by a sharp drop to 0% (container restart).
  OOMKills last 1h: 18
""",
        ("worker", "cpu"): """\
cpu (worker)
  Current:  85%
  Pattern:  Spikes to 100% during GC pauses, otherwise 40%.
""",
        ("worker", "latency_p95"): """\
latency_p95 (worker)
  Current:  16.4s
  1h avg:   12.1s
  24h avg:  2.1s
""",
        ("api", "error_rate"): """\
error_rate (api)
  Current:  2.4% (502 Bad Gateway)
  Matches exact timestamps of worker OOMKills.
""",
        ("metrics-agent", "memory"): """\
memory (metrics-agent)
  Current:  88%
  Pattern:  Slow leak over 2 weeks. Known issue.
""",
    }

    _DEPS = {
        "api": "api -> worker, database",
        "worker": "worker -> database, cache",
        "metrics-agent": "Standalone daemonset on all nodes.",
    }

    _CONFIGS = {
        "worker": """\
Recent config changes for worker:
  4 hours ago -- Deploy v4.1.0
    No code changes. Config update only:
    - BATCH_SIZE: 100 -> 5000
    - CONCURRENCY: 4 -> 4
    Reason: Attempting to optimize throughput for end-of-month reporting.
""",
        "api": "No config changes.",
        "metrics-agent": "No config changes.",
    }

    _RUNBOOKS = {
        "worker": """\
RUNBOOK: worker (SRE-DOC-012)
Typical issues:
1. OOMKilled: Check memory metrics. If sawtooth, it's an app memory leak or payload too large. 
   Remediation: rollback_deploy to last known good config OR scale_resource memory to give it breathing room.
2. Latency: Check DB dependencies.
""",
        "api": "Check upstream services.",
    }

    CORRECT_ROOT_CAUSES = frozenset(
        {
            "large_batch_size",
            "large_batch_size_oom",
            "batch_size",
            "batch_size_too_large",
            "oom",
            "oom_killed",
            "memory_leak",
            "worker_memory_leak",
        }
    )

    RED_HERRING_CAUSES = frozenset(
        {
            "metrics_agent",
            "metrics_agent_leak",
            "database_timeout",
            "db_timeout",
            "api_deploy",
        }
    )

    def _reset_scenario_state(self) -> None:
        self._done_investigations: set[str] = set()

    def step(self, command: ParsedCommand) -> StepOutcome:
        action = command.action_type

        if action == "query_logs":
            return self._handle_investigate(command, "logs", self._LOGS)
        elif action == "check_metrics":
            return self._handle_metrics(command)
        elif action == "check_deps":
            return self._handle_investigate(command, "deps", self._DEPS)
        elif action == "check_config":
            return self._handle_investigate(command, "config", self._CONFIGS)
        elif action == "check_runbook":
            return self._handle_investigate(command, "runbook", self._RUNBOOKS)
        elif action == "diagnose":
            return self._handle_diagnose(command)
        elif action == "rollback_deploy":
            return self._handle_rollback(command)
        elif action == "scale_resource":
            return self._handle_scale(command)
        elif action == "restart_service":
            # Worker is already restarting constantly
            score = self._score_event("remediation.wrong", destructive=False)
            return StepOutcome(
                investigation_result="Service restarted, but crashes immediately resumed. This did not fix the root cause.",
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=False,
                root_cause_identified=self._root_cause_identified,
            )
        elif action == "escalate":
            return self._handle_escalate(command)
        else:
            return self._handle_unknown_command(command.raw)

    def get_initial_observation_text(self) -> str:
        return ""

    def _handle_investigate(
        self, command: ParsedCommand, inv_type: str, source: dict
    ) -> StepOutcome:
        service = get_service_param(command.params, default="worker")
        data = source.get(service)

        if data is None:
            score = self._score_event("invalid_input")
            return StepOutcome(
                investigation_result=f"No {inv_type} data for service '{service}'.",
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=self._incident_resolved,
                root_cause_identified=self._root_cause_identified,
            )

        key = f"{inv_type}:{service}"
        duplicate = key in self._done_investigations
        if not duplicate:
            self._done_investigations.add(key)

        event = f"investigation.{action_to_event(inv_type)}.{service if service == 'worker' else 'default'}"
        score = self._score_event(event, duplicate=duplicate)

        return StepOutcome(
            investigation_result=data,
            reward=score.reward,
            done=self.is_done(),
            incident_resolved=self._incident_resolved,
            root_cause_identified=self._root_cause_identified,
        )

    def _handle_metrics(self, command: ParsedCommand) -> StepOutcome:
        service = get_service_param(command.params, default="worker")
        metric = get_metric_param(command.params, default="memory")
        data = self._METRICS.get((service, metric))

        if data is None:
            score = self._score_event("invalid_input")
            return StepOutcome(
                investigation_result=f"No metric '{metric}' for '{service}'.",
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=self._incident_resolved,
                root_cause_identified=self._root_cause_identified,
            )

        key = f"metric:{service}:{metric}"
        duplicate = key in self._done_investigations
        if not duplicate:
            self._done_investigations.add(key)

        score = self._score_event(
            "investigation.check_metrics.worker.memory"
            if service == "worker" and metric == "memory"
            else "investigation.check_metrics.default",
            duplicate=duplicate,
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

        if any(cause in normalised for cause in self.CORRECT_ROOT_CAUSES):
            self._root_cause_identified = True
            score = self._score_event("diagnosis.correct")
            return StepOutcome(
                investigation_result="Correct diagnosis.\nThe batch size increase caused OOMs. You can rollback_deploy worker or scale_resource memory.",
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=False,
                root_cause_identified=True,
            )
        elif any(cause in normalised for cause in self.RED_HERRING_CAUSES):
            score = self._score_event("diagnosis.wrong", premature=True)
            return StepOutcome(
                investigation_result="Incorrect diagnosis. The metrics-agent leak is slow and known; the DB timeouts are symptoms of the worker pausing.",
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=False,
                root_cause_identified=False,
            )
        else:
            score = self._score_event("diagnosis.wrong", premature=True)
            return StepOutcome(
                investigation_result=f"Incorrect diagnosis: '{raw}'.",
                reward=score.reward,
                done=self.is_done(),
                incident_resolved=False,
                root_cause_identified=False,
            )

    def _handle_rollback(self, command: ParsedCommand) -> StepOutcome:
        service = get_service_param(command.params)
        if service == "worker":
            score = self._score_event(
                "remediation.rollback_deploy.worker", resolved=True
            )
            self._incident_resolved = True
            self._current_system_status = {
                k: "healthy" for k in self._current_system_status
            }
            return StepOutcome(
                investigation_result="Rollback successful. BATCH_SIZE reverted to 100. Worker stopped crashing. Incident resolved.",
                reward=score.reward,
                done=True,
                incident_resolved=True,
                root_cause_identified=self._root_cause_identified,
            )
        score = self._score_event("remediation.wrong", destructive=True)
        return StepOutcome(
            investigation_result=f"rollback_deploy on '{service}' had no effect.",
            reward=score.reward,
            done=self.is_done(),
            incident_resolved=False,
            root_cause_identified=self._root_cause_identified,
        )

    def _handle_scale(self, command: ParsedCommand) -> StepOutcome:
        service = get_service_param(command.params)
        resource = command.params.get("resource", "").lower()
        if service == "worker" and resource == "memory":
            score = self._score_event(
                "remediation.scale_resource.worker.memory", resolved=True
            )
            self._incident_resolved = True
            self._current_system_status = {
                k: "healthy" for k in self._current_system_status
            }
            return StepOutcome(
                investigation_result="Worker memory scaled to 8GB. OOMs have ceased, batch size of 5000 is now sustainable. Incident resolved.",
                reward=score.reward,
                done=True,
                incident_resolved=True,
                root_cause_identified=self._root_cause_identified,
            )
        score = self._score_event("remediation.wrong", destructive=True)
        return StepOutcome(
            investigation_result=f"Scaling '{resource}' on '{service}' did not fix the issue.",
            reward=score.reward,
            done=self.is_done(),
            incident_resolved=False,
            root_cause_identified=self._root_cause_identified,
        )

    def _handle_escalate(self, command: ParsedCommand) -> StepOutcome:
        reason = command.params.get("reason", "")
        investigations = len(self._done_investigations)

        if investigations >= 3:
            self._incident_resolved = True
            self._current_system_status = {
                k: "healthy" for k in self._current_system_status
            }
            score = self._score_event("escalation.with_evidence", resolved=True)
            return StepOutcome(
                investigation_result=(
                    "Escalation accepted with sufficient evidence.\n\n"
                    f"Reason: {reason}\n"
                    f"Investigations completed: {investigations}\n"
                    "On-call lead has enough context to execute remediation."
                ),
                reward=score.reward,
                done=True,
                incident_resolved=True,
                root_cause_identified=self._root_cause_identified,
                info={"resolution": "escalated_with_evidence"},
            )

        score = self._score_event("escalation.no_evidence", premature=True)
        return StepOutcome(
            investigation_result=(
                "Escalation filed without enough evidence.\n"
                f"Investigations completed: {investigations} (need >=3)."
            ),
            reward=score.reward,
            done=True,
            incident_resolved=False,
            root_cause_identified=self._root_cause_identified,
        )


def action_to_event(inv_type: str) -> str:
    if inv_type == "logs":
        return "query_logs"
    if inv_type == "deps":
        return "check_deps"
    if inv_type == "config":
        return "check_config"
    if inv_type == "runbook":
        return "check_runbook"
    return inv_type
