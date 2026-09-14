"""Conftest: evaluate a Rego policy against parsed configuration documents."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from core.result import ERROR, PASS, SKIP, VIOLATION, Result

#: Any of Rego's load-time complaints, each meaning the policy never ran -- ERROR, not a violation.
_BROKEN = re.compile(
    r"rego_(parse|compile|type|unsafe_var)_error|loading policies|get compiler|"
    r"no policies found", re.I)

#: Names and extensions Conftest can parse into `input`. Used only to enumerate CANDIDATES.
SUFFIXES = (".yaml", ".yml", ".json", ".toml", ".xml", ".hcl", ".ini", ".properties")
NAMES = ("Dockerfile",)

#: Directories holding build output or vendored code, skipped when enumerating documents.
_SKIP = {".git", "target", "build", "node_modules", ".venv", ".gradle", ".idea"}


def structured_documents(tree: Path) -> list[str]:
    """Every document Conftest could parse in `tree`, relative to its root, found by walking."""
    tree = Path(tree)
    found = []
    for path in sorted(tree.rglob("*")):
        if not path.is_file() or _SKIP & set(path.relative_to(tree).parts):
            continue
        if path.name in NAMES or path.suffix in SUFFIXES:
            found.append(str(path.relative_to(tree)))
    return found


def _test(executable: str, policy: Path, targets: list[Path]) -> tuple[str, str]:
    """Run one policy over some documents. Returns (status, output)."""
    done = subprocess.run([executable, "test", "--policy", str(policy),
                           *[str(t) for t in targets]],
                          capture_output=True, text=True, timeout=900)
    output = (done.stdout or done.stderr).strip()
    if done.returncode == 0:
        return PASS, output
    if _BROKEN.search(output):
        return ERROR, output
    return VIOLATION, output


def _targets(patterns: list[str], repo: Path) -> tuple[list[Path], list[tuple[str, str]]]:
    """The files these patterns select, and the patterns that could not be applied at all."""
    targets: set[Path] = set()
    rejected: list[tuple[str, str]] = []
    for pattern in patterns:
        if not isinstance(pattern, str) or not pattern:
            rejected.append((str(pattern), "not a path"))
            continue
        try:
            targets.update(p for p in repo.glob(pattern) if p.is_file())
        except (NotImplementedError, ValueError, OSError) as error:
            rejected.append((pattern, f"{type(error).__name__}: {error}"))
    return sorted(targets), rejected


def run(rules: list[dict], run_dir: Path, repo: Path, tools: dict | None = None) -> Result:
    """Evaluate each policy against the files its own `files` globs select."""
    if not rules:
        return Result(SKIP, "no conftest rules generated")
    executable = (tools or {}).get("conftest")
    if not executable:
        return Result(SKIP, "conftest is not installed")

    lines, violated, errored, findings = [], False, False, 0
    for rule in rules:
        policy = run_dir / f"conftest_{rule['id']}.rego"
        targets, rejected = _targets(rule.get("files") or [], repo)
        for pattern, why in rejected:
            # An unusable pattern reads very differently from a valid glob that matched nothing.
            lines.append(f"  {rule['id']}  unusable path {pattern!r}: {why}")
        if not targets:
            lines.append(f"  {rule['id']}  no files matched {rule.get('files')}")
            continue

        status, output = _test(executable, policy, targets)
        if status == PASS:
            lines.append(f"  {rule['id']}  PASS over {len(targets)} file(s)")
        elif status == ERROR:
            # A policy that does not COMPILE has checked nothing, so it is never a violation.
            errored = True
            lines.append(f"  {rule['id']}  ERROR -- policy did not compile")
            lines += [f"    {line}" for line in output.splitlines()[:8]]
        else:
            violated, findings = True, findings + 1
            lines.append(f"  {rule['id']}  FAIL over {len(targets)} file(s)")
            lines += [f"    {line}" for line in output.splitlines()[:20]]

    status = ERROR if errored else (VIOLATION if violated else PASS)
    return Result(status, "\n".join([f"{len(rules)} policy(ies)"] + lines), findings)


def evaluate(policy: Path, tree: Path, targets: list[str],
             tools: dict | None = None) -> Result:
    """Evaluate one policy against named documents, relative to `tree`; the targets are passed in."""
    executable = (tools or {}).get("conftest")
    if not executable:
        return Result(SKIP, "conftest is not installed")
    present = [Path(tree) / t for t in targets if (Path(tree) / t).is_file()]
    if not present:
        return Result(ERROR, f"none of {list(targets)[:4]} exist here -- nothing was examined")
    status, output = _test(executable, policy, present)
    return Result(status, output[:400], 1 if status == VIOLATION else 0)
