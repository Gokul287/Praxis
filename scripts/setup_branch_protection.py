#!/usr/bin/env python3
"""
scripts/setup_branch_protection.py

Applies the Praxis main-branch protection rule via the GitHub REST API
(through the `gh` CLI), so nobody can merge into main without:

  - A PR (no direct pushes)
  - At least 1 approving review
  - CODEOWNERS-required reviewers (per .github/CODEOWNERS)
  - The `CI` status checks (lint / test / openenv-validate / http-smoke) green
  - Conversations resolved
  - Linear history (no merge commits) -- we squash or rebase
  - No force push, no branch delete

Usage:
  python scripts/setup_branch_protection.py                  # dry-run
  python scripts/setup_branch_protection.py --apply          # actually apply
  python scripts/setup_branch_protection.py --apply --branch release

Requires:
  - `gh` authenticated as a repo admin (Owner or Maintain+).
  - The CI workflow (.github/workflows/ci.yml) has run at least once on `main`,
    so GitHub knows the check names exist.

Why a script instead of clicking in the UI:
  - Reproducible; lives in the repo.
  - Can be re-run safely (PUT semantics on the protection endpoint = idempotent).
  - Documents the policy in code that the team can review.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys


# Required CI check names. Must match `name:` in .github/workflows/ci.yml.
REQUIRED_CHECKS = [
    "Lint (ruff)",
    "Test (Python 3.11)",
    "Test (Python 3.12)",
    "openenv validate",
    "HTTP smoke (uvicorn /health + /reset)",
]


def run(cmd: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    if capture:
        return subprocess.run(cmd, check=False, capture_output=True, text=True)
    return subprocess.run(cmd, check=False, text=True)


def gh_check_auth() -> None:
    if shutil.which("gh") is None:
        sys.exit("ERROR: `gh` CLI not found. Install: https://cli.github.com/")
    p = run(["gh", "auth", "status"], capture=True)
    if p.returncode != 0:
        sys.exit("ERROR: `gh auth status` failed. Run `gh auth login` first.")


def detect_repo() -> str:
    p = run(["gh", "repo", "view", "--json", "nameWithOwner"], capture=True)
    if p.returncode != 0:
        sys.exit(f"ERROR: `gh repo view` failed: {p.stderr.strip()}")
    return json.loads(p.stdout)["nameWithOwner"]


def build_payload(branch: str) -> dict:
    """The protection rule body. Tuned for a 3-person team (1 review minimum)."""
    return {
        "required_status_checks": {
            "strict": True,  # branches must be up to date before merging
            "contexts": REQUIRED_CHECKS,
        },
        "enforce_admins": False,  # allow admin override in emergencies
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": True,  # CODEOWNERS is the source of truth
            "required_approving_review_count": 1,
            "require_last_push_approval": True,
        },
        "restrictions": None,           # who can push -> no list = anyone w/ write
        "required_linear_history": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "required_conversation_resolution": True,
        "lock_branch": False,
        "allow_fork_syncing": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="Actually apply the protection rule.")
    ap.add_argument("--branch", default="main", help="Branch to protect (default: main).")
    ap.add_argument("--repo", help="OWNER/NAME (default: detect via `gh repo view`).")
    args = ap.parse_args()

    gh_check_auth()
    repo = args.repo or detect_repo()
    payload = build_payload(args.branch)
    endpoint = f"repos/{repo}/branches/{args.branch}/protection"

    print(f"Repo     : {repo}")
    print(f"Branch   : {args.branch}")
    print(f"Endpoint : PUT /{endpoint}")
    print("Required status checks:")
    for c in REQUIRED_CHECKS:
        print(f"  - {c}")
    print("Required reviews             : 1 approving + CODEOWNERS")
    print("Linear history               : enforced (squash/rebase only)")
    print("Force push / branch delete   : blocked")
    print("Conversation resolution      : required")
    print()

    if not args.apply:
        print("DRY-RUN. Re-run with --apply to push this rule to GitHub.")
        print()
        print("Equivalent gh command:")
        print(
            "  gh api -X PUT repos/{repo}/branches/{branch}/protection \\\n"
            "    --input -  <<< '{json}'".format(
                repo=repo, branch=args.branch,
                json=json.dumps(payload),
            )
        )
        return 0

    cmd = ["gh", "api", "-X", "PUT", endpoint, "--input", "-"]
    p = subprocess.run(cmd, input=json.dumps(payload), capture_output=True, text=True)
    if p.returncode != 0:
        print(f"FAIL: {p.stderr.strip()}")
        return 1
    print("Branch protection applied. Response:")
    try:
        print(json.dumps(json.loads(p.stdout), indent=2)[:1500])
    except Exception:
        print(p.stdout[:1500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
