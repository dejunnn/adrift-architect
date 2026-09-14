"""Semgrep: pattern-match Java source, reading rule-load failures out of the JSON report itself."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from core.result import ERROR, PASS, SKIP, VIOLATION, Result


def _scan(executable: str, configs: list[str], target: Path) -> tuple[dict | None, str]:
    """Run semgrep and return its parsed report, or None and the raw output."""
    done = subprocess.run(
        [executable, "--quiet", "--json", *configs, str(target)],
        capture_output=True, text=True, timeout=900)
    if not (done.stdout or "").strip():
        return None, (done.stderr or done.stdout).strip()[:2000]
    try:
        return json.loads(done.stdout), ""
    except json.JSONDecodeError:
        return None, (done.stderr or done.stdout).strip()[:2000]


def _errors(report: dict) -> str:
    """The rule-load failures a report carries, named. Empty when there are none."""
    errors = report.get("errors") or []
    if not errors:
        return ""
    lines = [f"{len(errors)} rule(s) did not load"]
    for error in errors[:8]:
        reason = error.get("long_msg") or error.get("short_msg") or error.get("message") or ""
        lines.append(f"  {error.get('type', 'error')}: {str(reason).splitlines()[0][:160]}")
    return "\n".join(lines)


def run(run_dir: Path, repo: Path, tools: dict | None = None) -> Result:
    """Scan the repository with every generated rule at once, each passed as an explicit --config."""
    rules = sorted(run_dir.glob("semgrep_*.yaml"))
    if not rules:
        return Result(SKIP, "no semgrep rules generated")
    executable = (tools or {}).get("semgrep")
    if not executable:
        return Result(SKIP, "semgrep is not installed (pip install semgrep)")

    report, raw = _scan(executable, [arg for r in rules for arg in ("--config", str(r))], repo)
    if report is None:
        return Result(ERROR, raw)
    failed = _errors(report)
    if failed:
        return Result(ERROR, failed)

    findings = report.get("results", [])
    lines = [f"{len(rules)} rule(s), {len(findings)} finding(s)"]
    for finding in findings:
        rule_id = str(finding.get("check_id", "")).split(".")[-1]
        line = finding.get("start", {}).get("line", "?")
        lines.append(f"  {rule_id}  {finding.get('path', '?')}:{line}")
    text = "\n".join(lines)
    return Result(VIOLATION if findings else PASS, text, len(findings))


def evaluate(rule: Path, tree: Path, tools: dict | None = None) -> Result:
    """Scan one tree with one rule document."""
    executable = (tools or {}).get("semgrep")
    if not executable:
        return Result(SKIP, "semgrep is not installed")
    report, raw = _scan(executable, ["--config", str(rule)], tree)
    if report is None:
        return Result(ERROR, raw)
    failed = _errors(report)
    if failed:
        return Result(ERROR, failed)
    findings = report.get("results", [])
    return Result(VIOLATION if findings else PASS, f"{len(findings)} finding(s)", len(findings))
