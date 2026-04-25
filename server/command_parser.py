"""
server.command_parser — Parse action command strings into structured ParsedCommand objects.

This is the single place where raw agent text becomes structured data.
Centralised here so scenarios never need to do their own string parsing.

Grammar:
    <action_type> [key=value ...]

Special cases:
    - escalate: reason=<free text with spaces>
    - diagnose:  root_cause=<value with underscores or hyphens>
    - timerange: value like "5m", "15m" (kept as-is, not parsed to int)

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
    }
)


def parse_command(raw: str) -> ParsedCommand:
    """
    Parse a raw command string into a ParsedCommand.

    Handles:
    - Standard "key=value" pairs split by whitespace
    - "escalate reason=<free text>" — everything after "reason=" is the reason
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
