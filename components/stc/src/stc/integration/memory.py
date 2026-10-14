"""File-backed TraceMemoryProtocol implementation (P02).

Serves sourced semantic context and negative inhibitors from the versioned
``memory/`` corpus so ``TraceMemoryProtocol`` works without full TRACE. Every
returned string is retrieval, never generation: citation-first
(``[source:memory/<file>.md#<anchor>]``), single-line, and carrying a visible
``(as-of <REPO>@<sha>, <date>)`` stamp.

Corpus contract: ``inhibitors.md`` backs :meth:`query_negative_inhibitors`
and ``context-index.md`` backs :meth:`query_semantic_context`. Entries start
at ``## `` headings with a ``{#anchor}`` suffix; required fields are
``- component:``, ``- source:``, ``- as-of: <repo>@<40-hex-sha>, <date>``;
the body is one or more ``> `` quote lines joined to one excerpt line.
Optional fields: ``- keywords:`` (semantic ranking) and ``- stale: yes``
(curator override). A missing corpus (or partition file) behaves like
``TraceClient`` without a live DB: queries return ``[]``. A present but
malformed file raises :class:`TraceMemoryError` fail-closed at load.

TraceClient parity notes (``stc.memory.trace_client`` is the reference):
match-all on ``*``/empty/blank inhibitor queries, case-insensitive matching,
unknown component/keywords to ``[]``, and ``max(1, max_results)`` clamping.
Deliberate difference: no result cap (TraceClient caps at 5) — the versioned
corpus is small and completeness beats truncation here.

Staleness: an entry is flagged ``[STALE]`` (after the citation, stamp still
visible) when the curator marked ``stale: yes`` or when its as-of SHA is a
strict ancestor of the P00 pin of its repo, determined via git ancestry when
the sibling checkouts are available. Undeterminable ancestry never blocks
retrieval: the entry is returned fresh with its stamp visible. All P02 seed
entries are fresh by construction.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from stc.core.errors import TraceMemoryError
from stc.integration.lease_git import resolve_stc_root
from stc.protocols.interfaces import TraceMemoryProtocol

# STC repo root (R2c): the workspace root carries the repo at stc/ on
# harness layouts, while leases ARE stc trees. Evaluated at import;
# in-lease processes set STC_WORKSPACE_ROOT before importing.
REPO_ROOT = resolve_stc_root()
DEFAULT_CORPUS_DIR = REPO_ROOT / "docs" / "builds" / "stc-integration" / "memory"

INHIBITORS_FILE = "inhibitors.md"
CONTEXT_INDEX_FILE = "context-index.md"

P00_PINS: dict[str, str] = {
    "stc": "565b1ed58089df74088f06b6d44a7cac09c70f87",
    "sst": "df78f42894a65c48f524337a498032617689a013",
    "prompt-kit": "4f442a6c829bc06b60f9979fdc8d7585e30bac9a",
    "trace": "a24a937009fec41e6dcb6d2ca31d3c1783ac97f7",
}

_HEADING_RE = re.compile(r"^##\s+(?P<title>.+?)\s*\{#(?P<anchor>[A-Za-z0-9][A-Za-z0-9_-]*)\}\s*$")
_FIELD_RE = re.compile(r"^-\s+(?P<key>[A-Za-z-]+)\s*:\s*(?P<value>.*?)\s*$")
_ASOF_RE = re.compile(
    r"^(?P<repo>[A-Za-z][A-Za-z0-9_-]*)\s*@\s*(?P<sha>[0-9a-fA-F]{40})"
    r"\s*,\s*(?P<date>\d{4}-\d{2}-\d{2})\s*$"
)


@dataclass(frozen=True)
class CorpusEntry:
    """One parsed corpus entry with its citation identity."""

    anchor: str
    title: str
    components: tuple[str, ...]
    source: str
    repo: str
    sha: str
    date: str
    keywords: tuple[str, ...] = ()
    body: str = ""
    partition: str = ""
    stale_override: bool = False
    order: int = 0

    @property
    def citation(self) -> str:
        return f"[source:memory/{self.partition}#{self.anchor}]"

    @property
    def stamp(self) -> str:
        return f"(as-of {self.repo.upper()}@{self.sha}, {self.date})"


@dataclass
class _MutableEntry:
    title: str
    anchor: str
    fields: dict[str, str] = field(default_factory=dict)
    body_lines: list[str] = field(default_factory=list)


def _split_sections(text: str) -> list[_MutableEntry]:
    sections: list[_MutableEntry] = []
    current: _MutableEntry | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        heading = _HEADING_RE.match(line)
        if heading is not None:
            current = _MutableEntry(
                title=heading.group("title").strip(),
                anchor=heading.group("anchor"),
            )
            sections.append(current)
            continue
        if current is None:
            continue
        if line.startswith(">"):
            current.body_lines.append(line[1:].strip())
            continue
        field_match = _FIELD_RE.match(line)
        if field_match is not None:
            current.fields[field_match.group("key").lower()] = field_match.group("value").strip()
    return sections


def parse_corpus_file(path: Path, partition: str) -> list[CorpusEntry]:
    """Parse one corpus markdown file into entries (fail-closed on malformed)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TraceMemoryError(f"Cannot read memory corpus file {path}: {exc}") from exc
    entries: list[CorpusEntry] = []
    seen: set[str] = set()
    for order, section in enumerate(_split_sections(text)):
        if section.anchor in seen:
            raise TraceMemoryError(f"Duplicate anchor {section.anchor!r} in {path}")
        seen.add(section.anchor)
        component_raw = section.fields.get("component", "")
        components = tuple(c.strip() for c in component_raw.split(",") if c.strip())
        source = section.fields.get("source", "")
        asof_raw = section.fields.get("as-of", "")
        asof = _ASOF_RE.match(asof_raw)
        keywords_raw = section.fields.get("keywords", "")
        keywords = tuple(k.strip().lower() for k in keywords_raw.split(",") if k.strip())
        body = " ".join(ln for ln in section.body_lines if ln)
        missing = [
            name
            for name, ok in (
                ("component", bool(components)),
                ("source", bool(source)),
                ("as-of", asof is not None),
                ("body", bool(body)),
            )
            if not ok
        ]
        if missing:
            raise TraceMemoryError(
                f"Entry {section.anchor!r} in {path} is missing/invalid: {', '.join(missing)}"
            )
        assert asof is not None
        stale_raw = section.fields.get("stale", "").strip().lower()
        entries.append(
            CorpusEntry(
                anchor=section.anchor,
                title=section.title,
                components=components,
                source=source,
                repo=asof.group("repo").lower(),
                sha=asof.group("sha").lower(),
                date=asof.group("date"),
                keywords=keywords,
                body=body,
                partition=partition,
                stale_override=stale_raw in ("yes", "true", "1"),
                order=order,
            )
        )
    return entries


def _is_strict_ancestor(repo_path: Path, maybe_older: str, maybe_newer: str) -> bool | None:
    """True if maybe_older is a strict ancestor of maybe_newer; None if unknowable."""
    if maybe_older == maybe_newer:
        return False
    try:
        proc = subprocess.run(
            ["git", "merge-base", "--is-ancestor", maybe_older, maybe_newer],
            cwd=repo_path,
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    return None


class FileBackedMemory(TraceMemoryProtocol):
    """TraceMemoryProtocol served from the versioned ``memory/`` corpus."""

    def __init__(
        self,
        corpus_dir: Path | str | None = None,
        pins: dict[str, str] | None = None,
    ) -> None:
        self.corpus_dir = Path(corpus_dir) if corpus_dir is not None else DEFAULT_CORPUS_DIR
        self.pins = dict(P00_PINS) if pins is None else dict(pins)
        self._inhibitors: list[CorpusEntry] = []
        self._context: list[CorpusEntry] = []
        self._loaded = False
        self._load()

    @property
    def has_live_corpus(self) -> bool:
        """Whether the corpus directory with at least one partition exists."""
        return self.corpus_dir.is_dir() and (
            (self.corpus_dir / INHIBITORS_FILE).is_file()
            or (self.corpus_dir / CONTEXT_INDEX_FILE).is_file()
        )

    def _load(self) -> None:
        if not self.corpus_dir.is_dir():
            return
        inhibitors_path = self.corpus_dir / INHIBITORS_FILE
        if inhibitors_path.is_file():
            self._inhibitors = parse_corpus_file(inhibitors_path, INHIBITORS_FILE)
        context_path = self.corpus_dir / CONTEXT_INDEX_FILE
        if context_path.is_file():
            self._context = parse_corpus_file(context_path, CONTEXT_INDEX_FILE)
        self._loaded = True

    def _repo_path(self, repo: str) -> Path | None:
        if self.corpus_dir != DEFAULT_CORPUS_DIR:
            return None
        if repo == "stc":
            return REPO_ROOT
        if repo in ("sst", "prompt-kit", "trace"):
            return REPO_ROOT.parent / repo
        return None

    def _is_stale(self, entry: CorpusEntry) -> bool:
        if entry.stale_override:
            return True
        pin = self.pins.get(entry.repo)
        if pin is None:
            return False
        if entry.sha == pin.lower():
            return False
        repo_path = self._repo_path(entry.repo)
        if repo_path is None or not (repo_path / ".git").exists():
            return False
        return _is_strict_ancestor(repo_path, entry.sha, pin.lower()) is True

    def _render(self, entry: CorpusEntry) -> str:
        stale_mark = " [STALE]" if self._is_stale(entry) else ""
        return f"{entry.citation}{stale_mark} {entry.body} {entry.stamp}"

    def query_semantic_context(self, keywords: list[str], max_results: int = 3) -> list[str]:
        """Keyword search over the context index; unknown/empty keywords give []."""
        if not self._loaded or not keywords:
            return []
        terms = [kw.strip().lower() for kw in keywords if kw.strip()]
        if not terms:
            return []
        scored: list[tuple[int, int, int, CorpusEntry]] = []
        for entry in self._context:
            haystack = " ".join(
                [entry.title, entry.body, " ".join(entry.keywords), " ".join(entry.components)]
            ).lower()
            matched = sum(1 for term in terms if term in haystack)
            if matched == 0:
                continue
            hits = sum(haystack.count(term) for term in terms)
            scored.append((matched, hits, -entry.order, entry))
        scored.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return [self._render(entry) for _, _, _, entry in scored[: max(1, max_results)]]

    def query_negative_inhibitors(self, component: str) -> list[str]:
        """Inhibitors for a component; */empty matches all, unknown gives []."""
        if not self._loaded:
            return []
        query = component.strip().lower()
        if query in ("", "*"):
            return [self._render(entry) for entry in self._inhibitors]
        matched: list[str] = []
        for entry in self._inhibitors:
            haystacks = (
                [tag.lower() for tag in entry.components]
                + [entry.title.lower(), entry.body.lower()]
                + list(entry.keywords)
            )
            if any(query in hay for hay in haystacks):
                matched.append(self._render(entry))
        return matched


__all__ = [
    "CONTEXT_INDEX_FILE",
    "DEFAULT_CORPUS_DIR",
    "INHIBITORS_FILE",
    "P00_PINS",
    "CorpusEntry",
    "FileBackedMemory",
    "parse_corpus_file",
]
