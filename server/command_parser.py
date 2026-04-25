"""
server.command_parser — Parse action command strings into structured ParsedCommand objects.

This is the single place where raw agent text becomes structured data.
Centralised here so scenarios never need to do their own string parsing.

Grammar:
    <action_type> [key=value ...]

Special cases:
    - escalate: reason=<free text with spaces>
    - save_finding: key=<key> value=<free text with spaces>
    - diagnose:  root_cause=<value with underscores or hyphens>
    - timerange: value like "5m", "15m" (kept as-is, not parsed to int)
    - create_plan: milestones=<comma-separated list, may contain spaces>
    - revise_plan: replace=<old> with=<new> | add=<new> | remove=<old>
    - checkpoint: milestone=<free text with spaces>
    - submit_report: root_causes=<comma list> resolution=<free text>
    - request_clarification: topic=<single token>

Usage:
    cmd = parse_command("query_logs service=auth timerange=5m")
    assert cmd.action_type == "query_logs"
    assert cmd.params == {"service": "auth", "timerange": "5m"}
"""

from __future__ import annotations

import re
from praxis_env.models import ParsedCommand

# All known action types — anything else is treated as unknown
KNOWN_ACTIONS: frozenset[str] = frozenset(
    {
        "query_logs",
        "check_metrics",
        "check_deps",
        "check_config",
        "check_runbook",
        "diagnose",
        "restart_service",
        "rollback_deploy",
        "scale_resource",
        "kill_query",
        "escalate",
        "save_finding",
        "recall_memory",
        # Planning surface (Issue #36)
        "create_plan",
        "revise_plan",
        "checkpoint",
        "submit_report",
        "request_clarification",
    }
)

# Action types that planning rubric attributes credit to.
PLANNING_ACTIONS: frozenset[str] = frozenset(
    {"create_plan", "revise_plan", "checkpoint", "submit_report"}
)


def parse_command(raw: str) -> ParsedCommand:
    """
    Parse a raw command string into a ParsedCommand.

    Handles:
    - Standard "key=value" pairs split by whitespace
    - "escalate reason=<free text>" — everything after "reason=" is the reason
    - "save_finding key=<k> value=<free text>" — value captures remaining text
    - Empty or whitespace-only strings → empty ParsedCommand
    - Unknown action types → valid ParsedCommand with unknown action_type

    Args:
        raw: The raw command string from the agent

    Returns:
        ParsedCommand with action_type, params dict, and original raw string

    Examples:
        >>> parse_command("query_logs service=auth timerange=5m")
        ParsedCommand(action_type='query_logs', params={'service': 'auth', 'timerange': '5m'})

        >>> parse_command("diagnose root_cause=db_connection_pool_exhausted")
        ParsedCommand(action_type='diagnose', params={'root_cause': 'db_connection_pool_exhausted'})

        >>> parse_command("escalate reason=DNS is broken and I have evidence")
        ParsedCommand(action_type='escalate', params={'reason': 'DNS is broken and I have evidence'})

        >>> parse_command("")
        ParsedCommand(action_type='', params={})
    """
    raw = raw.strip()

    if not raw:
        return ParsedCommand(action_type="", params={}, raw=raw)

    # Split on first whitespace to get action type
    parts = raw.split(None, 1)
    action_type = parts[0].lower().strip()
    remainder = parts[1].strip() if len(parts) > 1 else ""

    params: dict[str, str] = {}

    if not remainder:
        return ParsedCommand(action_type=action_type, params=params, raw=raw)

    # Special case: escalate reason=<free text>
    # Everything after "reason=" is the reason value, spaces included
    if action_type == "escalate":
        reason_match = re.search(r"reason=(.+)", remainder, re.IGNORECASE)
        if reason_match:
            params["reason"] = reason_match.group(1).strip().strip("'\"")
        else:
            # No reason= key — treat whole remainder as reason
            params["reason"] = remainder.strip("'\"")
        return ParsedCommand(action_type=action_type, params=params, raw=raw)

    # Special case: save_finding key=<k> value=<free text>
    # Value can include spaces, so parse with a regex anchored on value=
    if action_type == "save_finding":
        finding_match = re.search(
            r"key=([^\s]+)\s+value=(.+)$", remainder, re.IGNORECASE
        )
        if finding_match:
            params["key"] = finding_match.group(1).strip().strip("'\"")
            params["value"] = finding_match.group(2).strip().strip("'\"")
        else:
            # Let environment-side validation reject malformed payloads
            params = {}
        return ParsedCommand(action_type=action_type, params=params, raw=raw)

    # Special case: create_plan milestones=<comma list, may contain spaces>
    if action_type == "create_plan":
        match = re.search(r"milestones=(.+)$", remainder, re.IGNORECASE)
        if match:
            raw_value = match.group(1).strip().strip("'\"")
            milestones = [m.strip() for m in raw_value.split(",") if m.strip()]
            if milestones:
                params["milestones"] = ",".join(milestones)
        return ParsedCommand(action_type=action_type, params=params, raw=raw)

    # Special case: revise_plan {replace=<old> with=<new> | add=<new> | remove=<old>}
    if action_type == "revise_plan":
        replace_match = re.search(
            r"replace=(.+?)\s+with=(.+)$", remainder, re.IGNORECASE
        )
        if replace_match:
            params["replace"] = replace_match.group(1).strip().strip("'\"")
            params["with"] = replace_match.group(2).strip().strip("'\"")
            return ParsedCommand(action_type=action_type, params=params, raw=raw)
        add_match = re.search(r"add=(.+)$", remainder, re.IGNORECASE)
        if add_match:
            params["add"] = add_match.group(1).strip().strip("'\"")
            return ParsedCommand(action_type=action_type, params=params, raw=raw)
        remove_match = re.search(r"remove=(.+)$", remainder, re.IGNORECASE)
        if remove_match:
            params["remove"] = remove_match.group(1).strip().strip("'\"")
            return ParsedCommand(action_type=action_type, params=params, raw=raw)
        return ParsedCommand(action_type=action_type, params=params, raw=raw)

    # Special case: checkpoint milestone=<free text>
    if action_type == "checkpoint":
        match = re.search(r"milestone=(.+)$", remainder, re.IGNORECASE)
        if match:
            params["milestone"] = match.group(1).strip().strip("'\"")
        return ParsedCommand(action_type=action_type, params=params, raw=raw)

    # Special case: submit_report root_causes=<comma list> resolution=<free text>
    if action_type == "submit_report":
        # root_causes is required; resolution is optional and consumes the tail
        rc_match = re.search(
            r"root_causes=([^\s]+)(?:\s+resolution=(.+))?$",
            remainder,
            re.IGNORECASE,
        )
        if rc_match:
            params["root_causes"] = rc_match.group(1).strip().strip("'\"")
            if rc_match.group(2):
                params["resolution"] = rc_match.group(2).strip().strip("'\"")
        return ParsedCommand(action_type=action_type, params=params, raw=raw)

    # Standard key=value parsing for all other commands
    # Tokens separated by whitespace, each token is key=value
    for token in remainder.split():
        if "=" in token:
            key, _, val = token.partition("=")
            params[key.lower().strip()] = val.strip().strip("'\"")

    return ParsedCommand(action_type=action_type, params=params, raw=raw)


def is_known_action(action_type: str) -> bool:
    """Return True if the action type is one the environment understands."""
    return action_type.lower() in KNOWN_ACTIONS
