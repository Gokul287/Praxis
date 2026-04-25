#!/usr/bin/env python3
"""
scripts/create_github_issues.py

Reads idea/Plan/github_issues.md as the single source of truth and creates
(or updates) all 21 GitHub issues via the `gh` CLI.

Behaviour:
  - Default mode: dry-run. Prints the gh commands that would be executed.
  - --apply: actually executes `gh issue create` (or `gh issue edit` if the
    issue with the same title already exists, idempotent).
  - --repo OWNER/NAME: target repo. Default = `gh repo view --json nameWithOwner`.

Usage:
  python scripts/create_github_issues.py                  # dry-run
  python scripts/create_github_issues.py --apply          # creates issues
  python scripts/create_github_issues.py --apply --start 5 --end 10
  python scripts/create_github_issues.py --apply --only 7,8,21

Why we generate from github_issues.md instead of hard-coding bodies here:
  - Plan == reality. The issue file is the canonical body. If it changes,
    re-running this script updates the issues.
  - No copy-paste drift between the markdown plan and what lands on GitHub.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
ISSUES_FILE = REPO_ROOT / "idea" / "Plan" / "github_issues.md"

# Static metadata per issue: number -> (assignee, reviewers, label_extras)
# Mirrors idea/Plan/Project/DecisionLog.md ADR-11.
ARCHITECT = "GunaPalanivel"
TECHLEAD = "Gokul287"
SDE = "snehasneha56526-arch"

ISSUE_META: dict[int, dict] = {
    1:  {"assignee": ARCHITECT, "labels": ["P0", "blocker", "server", "concurrency"]},
    2:  {"assignee": ARCHITECT, "labels": ["P0", "models", "schema"]},
    3:  {"assignee": ARCHITECT, "labels": ["P0", "feature", "memory", "theme-2"]},
    4:  {"assignee": SDE,        "labels": ["P0", "parser", "memory"]},
    5:  {"assignee": SDE,        "labels": ["P0", "reward", "memory"]},
    6:  {"assignee": ARCHITECT, "labels": ["P0", "env", "memory"]},
    7:  {"assignee": TECHLEAD,  "labels": ["P0", "feature", "scenario", "theme-2"]},
    8:  {"assignee": TECHLEAD,  "labels": ["P0", "feature", "scenario", "procedural"]},
    9:  {"assignee": SDE,        "labels": ["P1", "manifest", "registry"]},
    10: {"assignee": TECHLEAD,  "labels": ["P1", "inference", "evidence"]},
    11: {"assignee": TECHLEAD,  "labels": ["P1", "training", "pipeline"]},
    12: {"assignee": TECHLEAD,  "labels": ["P1", "training", "evidence"]},
    13: {"assignee": SDE,        "labels": ["P1", "tests", "memory"]},
    14: {"assignee": SDE,        "labels": ["P1", "tests", "scenario"]},
    15: {"assignee": SDE,        "labels": ["P1", "tests", "concurrency"]},
    16: {"assignee": SDE,        "labels": ["P2", "cleanup"]},
    17: {"assignee": SDE,        "labels": ["P2", "validation", "submission"]},
    18: {"assignee": TECHLEAD,  "labels": ["P2", "deployment"]},
    19: {"assignee": ARCHITECT, "labels": ["P2", "documentation", "submission"]},
    20: {"assignee": TECHLEAD,  "labels": ["P2", "demo", "submission"]},
    21: {"assignee": TECHLEAD,  "labels": ["P2", "server", "benchmark", "submission"]},
}

# Universal labels added to every plan-v2.1 issue
COMMON_LABELS = ["plan-v2.1"]


# ---------------------------------------------------------------------------
# Parser: split idea/Plan/github_issues.md into per-issue (title, body) chunks
# ---------------------------------------------------------------------------

ISSUE_HEADER = re.compile(r"^# Issue #(\d+) — (.+)$", re.MULTILINE)


def parse_issues(md_path: Path) -> list[dict]:
    """Yield {number, title, body} for each `# Issue #N — Title` heading."""
    text = md_path.read_text(encoding="utf-8")
    matches = list(ISSUE_HEADER.finditer(text))
    if not matches:
        sys.exit(f"ERROR: no `# Issue #N` headings found in {md_path}")

    issues: list[dict] = []
    for i, m in enumerate(matches):
        number = int(m.group(1))
        title = m.group(2).strip()
        # Body starts right after the heading line. Stop at the next heading
        # OR at the `## Index` summary block at the bottom of the file.
        body_start = m.end()
        if i + 1 < len(matches):
            body_end = matches[i + 1].start()
        else:
            # Last issue: stop at the Index header that follows.
            idx = text.find("\n## Index", body_start)
            body_end = idx if idx != -1 else len(text)
        body = text[body_start:body_end].strip("\n")

        # Drop the trailing `---` separator if present
        body = re.sub(r"\n---\s*$", "", body)
        issues.append({"number": number, "title": title, "body": body})
    return issues


# ---------------------------------------------------------------------------
# gh CLI helpers
# ---------------------------------------------------------------------------


def run(cmd: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    if capture:
        return subprocess.run(cmd, check=False, capture_output=True, text=True)
    return subprocess.run(cmd, check=False, text=True)


def gh_check_auth() -> None:
    if shutil.which("gh") is None:
        sys.exit("ERROR: `gh` CLI not found on PATH. Install: https://cli.github.com/")
    p = run(["gh", "auth", "status"], capture=True)
    if p.returncode != 0:
        sys.exit("ERROR: `gh auth status` failed. Run `gh auth login` first.")


def detect_repo() -> str:
    p = run(["gh", "repo", "view", "--json", "nameWithOwner"], capture=True)
    if p.returncode != 0:
        sys.exit(f"ERROR: `gh repo view` failed: {p.stderr.strip()}")
    return json.loads(p.stdout)["nameWithOwner"]


def find_existing_issue(repo: str, title: str) -> int | None:
    """Return the issue number if an open or closed issue with this exact title exists."""
    p = run(
        ["gh", "issue", "list",
         "--repo", repo,
         "--state", "all",
         "--search", f'in:title "{title}"',
         "--json", "number,title",
         "--limit", "100"],
        capture=True,
    )
    if p.returncode != 0:
        sys.exit(f"ERROR: `gh issue list` failed: {p.stderr.strip()}")
    for row in json.loads(p.stdout):
        if row["title"].strip() == title:
            return int(row["number"])
    return None


def ensure_labels(repo: str, labels: Iterable[str], *, apply: bool) -> None:
    """Make sure each label exists; create with a neutral colour if not."""
    p = run(["gh", "label", "list", "--repo", repo, "--json", "name", "--limit", "200"], capture=True)
    if p.returncode != 0:
        # Older gh versions: just try and let create fail gracefully.
        existing = set()
    else:
        existing = {row["name"] for row in json.loads(p.stdout)}
    palette = {
        "P0": "B60205", "P1": "D93F0B", "P2": "FBCA04",
        "blocker": "B60205", "plan-v2.1": "5319E7",
        "memory": "1D76DB", "scenario": "0E8A16", "concurrency": "0052CC",
        "tests": "C2E0C6", "documentation": "0075CA", "deployment": "0E8A16",
        "demo": "8E44AD", "submission": "FF9F1C", "evidence": "B60205",
        "server": "0052CC", "schema": "5319E7", "models": "1D76DB",
        "feature": "A2EEEF", "training": "FB6A2B", "pipeline": "FB6A2B",
        "manifest": "C5DEF5", "registry": "C5DEF5", "validation": "0E8A16",
        "cleanup": "BFBFBF", "parser": "1D76DB", "reward": "B60205",
        "inference": "FB6A2B", "theme-2": "B60205", "env": "0052CC",
        "procedural": "0E8A16", "benchmark": "FF9F1C",
    }
    for lbl in labels:
        if lbl in existing:
            continue
        color = palette.get(lbl, "EDEDED")
        cmd = ["gh", "label", "create", lbl, "--repo", repo, "--color", color]
        if apply:
            run(cmd)
        else:
            print(" DRY  $", " ".join(cmd))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="Actually run gh commands. Without this flag, dry-run only.")
    ap.add_argument("--repo", help="Target repo as OWNER/NAME (default: current `gh repo view`).")
    ap.add_argument("--only", help="Comma-separated issue numbers to (re)create, e.g. `1,5,21`.")
    ap.add_argument("--start", type=int, default=1, help="First issue to process (inclusive).")
    ap.add_argument("--end", type=int, default=21, help="Last issue to process (inclusive).")
    args = ap.parse_args()

    gh_check_auth()
    repo = args.repo or detect_repo()
    print(f"Target repo: {repo}")
    print(f"Source     : {ISSUES_FILE.relative_to(REPO_ROOT)}")
    print(f"Mode       : {'APPLY' if args.apply else 'DRY-RUN'}")

    only = {int(x) for x in args.only.split(",")} if args.only else None
    issues = parse_issues(ISSUES_FILE)
    if {i["number"] for i in issues} != set(range(1, 22)):
        missing = sorted(set(range(1, 22)) - {i["number"] for i in issues})
        sys.exit(f"ERROR: github_issues.md missing issue numbers {missing}; expected 1..21.")

    # Pre-create labels exactly once.
    all_labels = set(COMMON_LABELS)
    for meta in ISSUE_META.values():
        all_labels.update(meta["labels"])
    ensure_labels(repo, sorted(all_labels), apply=args.apply)

    n_created = n_updated = n_skipped = 0
    for issue in issues:
        n = issue["number"]
        if only and n not in only:
            continue
        if n < args.start or n > args.end:
            continue

        meta = ISSUE_META[n]
        title = f"[#{n}] {issue['title']}"
        body = issue["body"]
        labels = sorted(set(meta["labels"]) | set(COMMON_LABELS))
        assignee = meta["assignee"]

        existing = find_existing_issue(repo, title)
        if existing is not None:
            cmd = [
                "gh", "issue", "edit", str(existing),
                "--repo", repo,
                "--body", body,
                "--add-label", ",".join(labels),
                "--add-assignee", assignee,
            ]
            if args.apply:
                p = run(cmd, capture=True)
                if p.returncode != 0:
                    print(f"  FAIL update #{n} -> existing {existing}: {p.stderr.strip()}")
                else:
                    print(f"  upd  #{n:02d} -> existing GitHub issue {existing}")
                    n_updated += 1
            else:
                print(f" DRY  upd  #{n:02d} -> #{existing}: " + " ".join(cmd[:4]))
                n_skipped += 1
            continue

        cmd = [
            "gh", "issue", "create",
            "--repo", repo,
            "--title", title,
            "--body", body,
            "--label", ",".join(labels),
            "--assignee", assignee,
        ]
        if args.apply:
            p = run(cmd, capture=True)
            if p.returncode != 0:
                print(f"  FAIL create #{n}: {p.stderr.strip()}")
            else:
                print(f"  new  #{n:02d} -> {p.stdout.strip()}")
                n_created += 1
        else:
            preview = " ".join(cmd[:6]) + f" ... ({len(body)} body chars)"
            print(f" DRY  new  #{n:02d} -> {preview}")
            n_skipped += 1

    print()
    print(f"Done. created={n_created} updated={n_updated} dry-run-only={n_skipped}")
    if not args.apply:
        print("Re-run with --apply to actually push these issues to GitHub.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
