"""Smoke: run a hand-crafted Mission rollout end-to-end via the HTTP API.

Hits /reset, posts a sequence of investigation -> diagnose -> remediate
actions for the cascading-platform-failure mission, and verifies:
  * the Intake observation contains a vendored on-call note
  * /step query_logs surfaces a [VENDORED LOG EXCERPT: <svc>] banner
  * /step check_runbook surfaces a [VENDORED RUNBOOK EXCERPT: <svc>] banner
  * submit_report flips incident_resolved=True and final_score >= 0.50

Run with:
  python scripts/smoke_mission_rollout.py --base http://127.0.0.1:7872
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urlparse

import urllib.request


def _request(method: str, url: str, *, body: dict | None = None,
             headers: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:7872")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    # 1. /reset cascading-platform-failure with a deterministic seed.
    reset = _request(
        "POST",
        f"{args.base}/reset",
        body={"task_name": "cascading-platform-failure", "seed": args.seed},
    )
    session_id = reset["session_id"]
    intake = reset["observation"]["investigation_result"] or ""
    headers = {"X-Session-Id": session_id}

    print(f"[reset]  session_id={session_id}")
    print(f"[reset]  mission_id={reset['observation'].get('mission_id')}")
    print(f"[reset]  phase={reset['observation'].get('phase')}")
    print(f"[reset]  time_budget={reset['observation'].get('time_budget')}")
    assert "[INTAKE: most-recent on-call note for the impacted service]" in intake, (
        "intake observation must surface a vendored on-call note"
    )
    print(f"[reset]  intake on-call note OK")

    # 2. query_logs database -> expect vendored log excerpt
    out = _request(
        "POST",
        f"{args.base}/step",
        body={"command": "query_logs service=database timerange=5m"},
        headers=headers,
    )
    text = out["observation"]["investigation_result"]
    assert "[VENDORED LOG EXCERPT: database]" in text, text[:500]
    print(f"[step]   query_logs database -> reward={out['reward']:.4f}")

    # 3. check_runbook cdn -> expect vendored runbook excerpt
    out = _request(
        "POST",
        f"{args.base}/step",
        body={"command": "check_runbook service=cdn"},
        headers=headers,
    )
    text = out["observation"]["investigation_result"]
    assert "[VENDORED RUNBOOK EXCERPT: cdn]" in text, text[:500]
    print(f"[step]   check_runbook cdn      -> reward={out['reward']:.4f}")

    # 4. check_runbook worker kind=ticket -> expect vendored ticket excerpt
    out = _request(
        "POST",
        f"{args.base}/step",
        body={"command": "check_runbook service=worker kind=ticket"},
        headers=headers,
    )
    text = out["observation"]["investigation_result"]
    assert "[PRIOR TICKET EXCERPT: worker]" in text, text[:500]
    print(f"[step]   check_runbook worker ticket -> reward={out['reward']:.4f}")

    # 5. Drive the mission to resolution.
    actions = [
        "check_metrics service=database metric=connections",
        "check_metrics service=cdn metric=tls_handshake_failures",
        "check_metrics service=worker metric=memory",
        "check_config service=database",
        "check_config service=cdn",
        "check_config service=worker",
        "diagnose root_cause=db_pool_corrupted",
        "diagnose root_cause=cdn_tls_expired",
        "diagnose root_cause=worker_memory_leak",
        "rollback_deploy service=cdn",
        "scale_resource service=database resource=connection_pool",
        "rollback_deploy service=worker",
        (
            "submit_report root_causes=db_pool_corrupted,cdn_tls_expired,"
            "worker_memory_leak resolution=full_remediation_applied"
        ),
    ]
    last = None
    for cmd in actions:
        last = _request(
            "POST",
            f"{args.base}/step",
            body={"command": cmd},
            headers=headers,
        )
        marker = "OK" if last.get("reward", 0) >= 0 else "WARN"
        print(f"[step]   {cmd[:62]:<62} {marker} reward={last['reward']:.4f}")

    # 6. /state should now report incident_resolved + final_score >= 0.50.
    state = _request("GET", f"{args.base}/state", headers=headers)
    print(f"[state]  incident_resolved={state['incident_resolved']}")
    print(f"[state]  root_cause_identified={state['root_cause_identified']}")
    print(f"[state]  cumulative_reward={state['cumulative_reward']:.4f}")
    print(f"[state]  final_score={state['final_score']}")
    assert state["incident_resolved"], "submit_report did not resolve incident"
    assert state["root_cause_identified"]
    assert state["final_score"] is not None
    assert state["final_score"] >= 0.50, (
        f"final_score {state['final_score']} below 0.50 threshold"
    )

    print("\n[PASS] mission rollout smoke succeeded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
