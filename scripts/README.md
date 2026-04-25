# Praxis ops scripts

Read-only-by-default operational scripts. None of these mutate GitHub or the
repo unless you pass `--apply`.

| Script                       | What it does                                                                                                   | Idempotent?                                                        |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `create_github_issues.py`    | Reads `idea/Plan/github_issues.md` and creates/updates the 21 issues on GitHub via `gh`.                       | Yes — re-run to sync title/body/labels/assignee with the markdown. |
| `setup_branch_protection.py` | Applies the `main` branch protection rule (1 review + CODEOWNERS + CI green + linear history + no force push). | Yes — PUT semantics.                                               |

## Prereqs (one-time)

```bash
gh auth login                 # authenticate with GitHub
gh auth status                # confirm "Logged in to github.com account ..."
```

## Recommended sequence

```bash
# 1. Land the workflows + plan docs first so CI starts producing the
#    required check names (Lint (ruff), Test (Python 3.11), ...).
git push origin main

# 2. Apply branch protection. The check names match ci.yml job `name:` fields.
python scripts/setup_branch_protection.py            # dry-run
python scripts/setup_branch_protection.py --apply    # apply

# 3. Open the 21 issues. Dry-run first to inspect.
python scripts/create_github_issues.py               # dry-run
python scripts/create_github_issues.py --apply       # creates everything
python scripts/create_github_issues.py --apply --only 1   # just one
```

## Rollback

- Branch protection: `gh api -X DELETE repos/<owner>/<repo>/branches/main/protection`
- Issues: `gh issue close <num>` per number, or close them in the UI.

## Why generated, not hand-typed

`create_github_issues.py` reads `idea/Plan/github_issues.md` so the GitHub
issues stay in lock-step with the plan docs. Edit the markdown, re-run with
`--apply`, and the issues update. No copy-paste drift.

`setup_branch_protection.py` keeps the protection rule in code so the team
can review the policy diff like any other PR.
