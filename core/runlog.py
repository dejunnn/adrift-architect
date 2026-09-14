"""One run record for every kind of run: runs.jsonl (analysis), exchanges.jsonl (evidence), a directory each."""

from __future__ import annotations

import fcntl
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOGS_ROOT = Path(os.environ.get("ADRIFT_LOGS", REPO_ROOT / "logs"))

EXCHANGES = "exchanges.jsonl"
RUNS = "runs.jsonl"

#: The kinds of run this instrument performs. Each gets its own directory under logs/.
KINDS = ("generate", "probe", "execute", "mutate", "apply")


def _slug(value: str, limit: int = 60) -> str:
    """A filesystem-safe fragment for a directory name, with underscore reserved as the separator."""
    cleaned = re.sub(r"[^A-Za-z0-9.-]+", "-", str(value)).strip("-")
    return cleaned[:limit].rstrip("-") or "unknown"


def _total(exchanges: list[dict], field: str) -> int | None:
    """Sum one usage field across exchanges, returning None only when no exchange reported it."""
    seen = [e.get(field) for e in exchanges if e.get(field) is not None]
    return sum(seen) if seen else None


@dataclass
class Run:
    """One invocation: one logical unit of work, one directory, one record, created before any call."""

    kind: str                        # one of KINDS
    subject: str                     # what the run is about -- usually the ADR stem
    repo: str                        # repository basename
    provider: str = "-"
    model: str = "-"
    arm: str = "-"                   # tools-named | tool-free | mutator | execution
    flags: dict = field(default_factory=dict)

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    started: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    exchanges: list = field(default_factory=list)
    status: str = "started"
    error: str = ""
    _directory: Path | None = None

    # ------------------------------------------------------------------ location

    @property
    def root(self) -> Path:
        """The directory holding every run of this kind."""
        return LOGS_ROOT / self.kind

    @property
    def directory(self) -> Path:
        """`logs/<kind>/<subject>_<model>_<repo>_<timestamp>_<runId>/`, created on first use."""
        if self._directory is None:
            stamp = datetime.fromisoformat(self.started).strftime("%Y%m%dT%H%M%SZ")
            name = "_".join((_slug(self.subject, 70), _slug(self.model, 40),
                             _slug(self.repo, 40), stamp, self.run_id))
            self._directory = self.root / name
            self._directory.mkdir(parents=True, exist_ok=True)
        return self._directory

    def use_directory(self, path: Path) -> None:
        """Write into `path` instead of the generated name, for one stable directory per decision."""
        path.mkdir(parents=True, exist_ok=True)
        self._directory = path

    def path(self, name: str) -> Path:
        """A file inside this run's directory, creating the directory on first use."""
        return self.directory / name

    def write(self, name: str, text: str) -> Path:
        """Write one artefact into the run directory and return where it went."""
        target = self.path(name)
        target.write_text(text, encoding="utf-8")
        return target

    # ------------------------------------------------------------------ writing

    def exchange(self, kind: str, request: dict, response: dict,
                 usage: dict | None = None, elapsed_ms: int = 0,
                 http_status: int | None = None) -> str:
        """Record one request/response pair verbatim and return the exchange id."""
        usage = usage or {}
        exchange_id = f"{self.run_id}_{len(self.exchanges) + 1}"
        _append(self.root / EXCHANGES, {
            "exchangeId": exchange_id,
            "runId": self.run_id,
            "kind": kind,                       # completion | batch
            "provider": self.provider,
            "at": datetime.now(timezone.utc).isoformat(),
            "request": request,
            "response": response,
        })
        self.exchanges.append({
            "exchangeId": exchange_id,
            "kind": kind,
            "httpStatus": http_status,
            "elapsedMs": elapsed_ms,
            "inputTokens": usage.get("inputTokens"),
            "outputTokens": usage.get("outputTokens"),
            # Reasoning is a SUBSET of outputTokens; cache figures are input-side.
            "reasoningTokens": usage.get("reasoningTokens"),
            "cachedInputTokens": usage.get("cachedInputTokens"),
            "cacheWriteTokens": usage.get("cacheWriteTokens"),
        })
        # The run's own copy, so a directory is self-contained without the shared log.
        suffix = "" if len(self.exchanges) == 1 else f"_{len(self.exchanges)}"
        self.write(f"request{suffix}.json",
                   json.dumps(request, indent=2, ensure_ascii=False, default=str))
        self.write(f"response{suffix}.json",
                   json.dumps(response, indent=2, ensure_ascii=False, default=str))
        return exchange_id

    def finish(self, status: str, error: str = "", **extra) -> dict:
        """Close the run: append to runs.jsonl and drop the same record in the directory."""
        self.status, self.error = status, error
        finished = datetime.now(timezone.utc)
        record = {
            "runId": self.run_id,
            "kind": self.kind,
            "directory": self.directory.name,
            "arm": self.arm,
            "status": status,
            "error": error,
            "provider": self.provider,
            "model": self.model,
            "subject": self.subject,
            "repo": self.repo,
            "flags": self.flags,
            "started": self.started,
            "finished": finished.isoformat(),
            "elapsedMs": int((finished - datetime.fromisoformat(self.started)).total_seconds()
                             * 1000),
            "inputTokens": sum(e["inputTokens"] or 0 for e in self.exchanges) or None,
            "outputTokens": sum(e["outputTokens"] or 0 for e in self.exchanges) or None,
            # NOT `or None`: a reported zero is a fact, distinct from an unreported field.
            "reasoningTokens": _total(self.exchanges, "reasoningTokens"),
            "cachedInputTokens": _total(self.exchanges, "cachedInputTokens"),
            "cacheWriteTokens": _total(self.exchanges, "cacheWriteTokens"),
            "exchanges": self.exchanges,
            **extra,
        }
        _append(self.root / RUNS, record)
        self.write("run.json", json.dumps(record, indent=2, ensure_ascii=False, default=str))
        return record


def _append(path: Path, record: dict) -> None:
    """Append one JSON object as a line, locked so parallel runs cannot interleave into corruption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.write(line)
            handle.flush()
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def find_run(reference: str, kind: str | None = None) -> Path | None:
    """Locate a run directory by id, by full name, or by path -- the filesystem is the index."""
    candidate = Path(reference)
    if candidate.is_dir():
        return candidate.resolve()

    roots = [LOGS_ROOT / kind] if kind else [LOGS_ROOT / k for k in KINDS]
    matches: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        if (root / reference).is_dir():
            return root / reference
        matches += sorted(root.glob(f"*_{reference}"))
    if len(matches) > 1:
        # Ids are unique by construction, so this means a partial id was passed.
        raise SystemExit(f"{reference!r} matches {len(matches)} runs; use a full run id or "
                         "directory name:\n  " + "\n  ".join(m.name for m in matches))
    return matches[0] if matches else None
