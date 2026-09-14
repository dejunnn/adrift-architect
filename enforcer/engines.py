"""Dispatch to the three engines -- ArchUnit, Semgrep, Conftest -- with no engine-specific logic here."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from core.result import SKIP, Result
from enforcer.archunit import runner as archunit
from enforcer.conftest import runner as conftest
from enforcer.semgrep import runner as semgrep

REPO_ROOT = Path(__file__).resolve().parents[1]

TOOLS = ("archunit", "semgrep", "conftest")

#: The response field carrying each engine's rule body, and the extension its artefact takes.
BODY_FIELD = {"archunit": "rule", "semgrep": "yaml", "conftest": "rego"}
SUFFIX = {"archunit": ".java", "semgrep": ".yaml", "conftest": ".rego"}

#: Which engine reads a saved check file, by extension. `.txt` and `.java` are both ArchUnit.
ENGINE_OF_SUFFIX = {".txt": "archunit", ".java": "archunit",
                    ".yaml": "semgrep", ".yml": "semgrep", ".rego": "conftest"}

#: Executables each engine needs. Looked up once per command rather than per rule.
_EXECUTABLES = ("mvn", "java", "semgrep", "conftest")


def tool_path(name: str) -> str | None:
    """Locate an executable: ADRIFT_<NAME>, then the project venv, then PATH."""
    override = os.environ.get(f"ADRIFT_{name.upper()}")
    if override:
        return override
    in_venv = REPO_ROOT / ".venv" / "bin" / name
    if in_venv.exists():
        return str(in_venv)
    return shutil.which(name)


def available() -> dict[str, str | None]:
    """Where each engine's executable is, or None. Passed down so no runner looks it up."""
    return {name: tool_path(name) for name in _EXECUTABLES}


def run_all(rules: dict, run_dir: Path, repo: Path, classes: list[Path] | None = None,
            only: list[str] | None = None) -> dict[str, Result]:
    """Execute a run's rules against a repository, returning one Result per engine."""
    wanted = only or list(TOOLS)
    tools = available()
    results: dict[str, Result] = {}
    if "semgrep" in wanted:
        results["semgrep"] = semgrep.run(run_dir, repo, tools)
    if "conftest" in wanted:
        results["conftest"] = conftest.run(rules.get("conftest") or [], run_dir, repo, tools)
    if "archunit" in wanted:
        results["archunit"] = archunit.run(rules.get("archunit") or [], repo, classes, tools)
    return results


def evaluate(check: Path, tree: Path, classes: Path | None = None,
             targets: list[str] | None = None, scratch: Path | None = None) -> Result:
    """Evaluate ONE check file against ONE tree, with the engine chosen by extension."""
    check = Path(check)
    engine = ENGINE_OF_SUFFIX.get(check.suffix)
    if engine is None:
        return Result(SKIP, f"{check.name}: not a check file "
                            f"({', '.join(sorted(ENGINE_OF_SUFFIX))})")
    tools = available()
    if engine == "semgrep":
        return semgrep.evaluate(check, tree, tools)
    if engine == "conftest":
        return conftest.evaluate(check, tree, targets or [], tools)
    scratch = scratch or (tree.parent / f".adrift-scratch-{check.stem}")
    return archunit.evaluate(check.read_text(encoding="utf-8"), classes, tree, scratch)
