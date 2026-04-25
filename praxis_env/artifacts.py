"""
praxis_env.artifacts - deterministic ArtifactStore (Issue #38, ADR-17).

The MissionScenario surfaces vendored production-style artifacts (logs,
runbooks, prior tickets, on-call notes) when the agent investigates the
incident. ``ArtifactStore`` indexes the on-disk fixtures by ``(kind,
service)`` and returns deterministic draws keyed off ``(seed, kind,
service, n, draw_count)`` so every replay sees identical content per the
ScenarioCatalog.md S7.3 contract.

Layout assumptions::

    data/artifacts/
    |- README.md
    |- NOTICE.md
    |- logs/<service>_<topic>.jsonl       # one JSON record per line
    |- runbooks/<service>_<topic>.md      # full-document markdown
    |- tickets/<service>_<topic>.md
    `- notes/<service>_<topic>.md

For ``.jsonl`` files each line becomes a separate :class:`Artifact`. For
``.md`` files the whole document is one artifact. Service membership is
derived from the leading token of the filename (`<service>_*`).

Note: the canonical Rootly-AI-Labs/logs-dataset referenced in ADR-17 was
not publicly available at vendoring time, so the shipped excerpts are
internally-authored Praxis fixtures (see ``data/artifacts/NOTICE.md``).
The ``Artifact.source`` provenance strings reflect that with the
``praxis:fixtures/...`` prefix.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

# ── Public types ──────────────────────────────────────────────────────────


_VALID_KINDS: frozenset[str] = frozenset({"log", "runbook", "ticket", "note"})

# Map plural directory names <-> singular Artifact.kind tags.
_KIND_TO_DIR: dict[str, str] = {
    "log": "logs",
    "runbook": "runbooks",
    "ticket": "tickets",
    "note": "notes",
}


@dataclass(frozen=True)
class Artifact:
    """Single excerpt returned by :meth:`ArtifactStore.draw`."""

    kind: str  # "log" | "runbook" | "ticket" | "note"
    service: str  # e.g. "api" | "database" | "cdn"
    body: str  # excerpt content (line / file)
    source: str  # provenance, e.g. "praxis:fixtures/logs/api_500s#L42"


@dataclass(frozen=True)
class _ArtifactSource:
    """Internal pre-indexed view of a single fixture file row."""

    kind: str
    service: str
    body: str
    source: str


class ArtifactStore:
    """Deterministic, in-memory index over the vendored fixtures.

    Parameters
    ----------
    root:
        Path to the ``data/artifacts/`` directory.
    seed:
        Per-episode seed. Same ``(seed, kind, service, n)`` returns the
        same artifacts in the same order across processes.

    Raises
    ------
    FileNotFoundError:
        If ``root`` does not exist or is empty for every kind.
    """

    PROVENANCE_PREFIX: str = "praxis:fixtures"

    def __init__(self, root: Path | str, *, seed: int = 0) -> None:
        self._root = Path(root)
        self._seed = int(seed)
        self._index: dict[tuple[str, str], list[_ArtifactSource]] = {}
        self._known_services: set[str] = set()
        self._all_sources: list[_ArtifactSource] = []
        self._load()

    # ── Loading ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._root.is_dir():
            raise FileNotFoundError(
                f"ArtifactStore root not found: {self._root!s}"
            )

        for kind, subdir in _KIND_TO_DIR.items():
            kind_dir = self._root / subdir
            if not kind_dir.is_dir():
                continue
            for path in sorted(kind_dir.iterdir()):
                if path.suffix.lower() not in {".jsonl", ".md", ".log", ".txt"}:
                    continue
                self._index_file(kind, path)

        if not self._all_sources:
            raise FileNotFoundError(
                f"ArtifactStore root contained no recognised fixtures: "
                f"{self._root!s}"
            )

    def _index_file(self, kind: str, path: Path) -> None:
        service = path.stem.split("_", 1)[0].lower()
        self._known_services.add(service)
        rel = path.relative_to(self._root).as_posix()

        if path.suffix.lower() == ".jsonl":
            text = path.read_text(encoding="utf-8")
            line_no = 0
            for raw_line in text.splitlines():
                line_no += 1
                line = raw_line.strip()
                if not line:
                    continue
                # Each JSONL row becomes one artifact; the whole line is
                # the body so callers can render it verbatim.
                source = (
                    f"{self.PROVENANCE_PREFIX}/{rel}#L{line_no}"
                )
                src = _ArtifactSource(
                    kind=kind, service=service, body=line, source=source
                )
                self._index.setdefault((kind, service), []).append(src)
                self._all_sources.append(src)
        else:
            body = path.read_text(encoding="utf-8").rstrip()
            if not body:
                return
            source = f"{self.PROVENANCE_PREFIX}/{rel}"
            src = _ArtifactSource(
                kind=kind, service=service, body=body, source=source
            )
            self._index.setdefault((kind, service), []).append(src)
            self._all_sources.append(src)

    # ── Public API ───────────────────────────────────────────────────────

    def draw(self, kind: str, service: str, n: int = 1) -> list[Artifact]:
        """Return up to ``n`` artifacts for ``(kind, service)``.

        The selection is deterministic per ``(seed, kind, service, n)``
        - same seed always yields the same ordered list. If fewer than
        ``n`` artifacts exist, the full list is returned (no padding).
        """
        if kind not in _VALID_KINDS:
            raise ValueError(
                f"Unknown artifact kind '{kind}'. "
                f"Expected one of {sorted(_VALID_KINDS)}."
            )
        if n < 0:
            raise ValueError(f"n must be non-negative; got {n}")
        if n == 0:
            return []

        candidates = self._index.get((kind, service.lower()), [])
        if not candidates:
            return []

        # Per-call RNG so repeated draw() calls stay reproducible.
        # ``random.Random`` only accepts hashable scalar seeds, so we
        # collapse the tuple into a stable string before seeding.
        seed_key = f"{self._seed}|{kind}|{service.lower()}|{n}"
        rng = random.Random(seed_key)
        # Sample without replacement up to n.
        ordering = list(range(len(candidates)))
        rng.shuffle(ordering)
        picks = ordering[: min(n, len(candidates))]
        return [
            Artifact(
                kind=src.kind,
                service=src.service,
                body=src.body,
                source=src.source,
            )
            for src in (candidates[i] for i in picks)
        ]

    def services(self) -> list[str]:
        """Sorted list of services that have at least one fixture."""
        return sorted(self._known_services)

    def attribution(self) -> str:
        """Single string surfaced from ``/metadata`` for compliance.

        The string lists the provenance prefix and the size + service
        coverage of the vendored fixtures. Callers can render it verbatim
        without parsing.
        """
        notice = self._root / "NOTICE.md"
        tagline = "Praxis vendored mission artifacts"
        if notice.is_file():
            for raw in notice.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if line.startswith("# "):
                    # First H1 only; drop heading marker.
                    tagline = line.lstrip("# ").strip()
                    break
        services = ", ".join(self.services())
        return (
            f"{tagline}; provenance prefix='{self.PROVENANCE_PREFIX}'; "
            f"services=[{services}]; "
            f"total_artifacts={len(self._all_sources)}"
        )

    # ── Introspection helpers (used by tests / metadata) ─────────────────

    def __len__(self) -> int:
        return len(self._all_sources)

    @property
    def root(self) -> Path:
        return self._root

    @property
    def seed(self) -> int:
        return self._seed


# ── Helpers ───────────────────────────────────────────────────────────────


def default_artifact_root() -> Path:
    """Return the canonical on-disk root for vendored mission artifacts."""
    return Path(__file__).resolve().parent.parent / "data" / "artifacts"


def load_default_store(*, seed: int = 0) -> ArtifactStore | None:
    """Load the repo's default ArtifactStore, returning None if absent.

    Scenarios use this so they can degrade gracefully (and run their
    legacy in-memory fixtures) when the environment is deployed without
    the vendored data directory.
    """
    root = default_artifact_root()
    if not root.is_dir():
        return None
    try:
        return ArtifactStore(root, seed=seed)
    except FileNotFoundError:
        return None


def parse_jsonl_artifact_body(body: str) -> dict[str, object]:
    """Best-effort JSON parse of a JSONL artifact body for downstream code."""
    try:
        loaded = json.loads(body)
    except json.JSONDecodeError:
        return {"raw": body}
    if isinstance(loaded, dict):
        return loaded
    return {"raw": body}
