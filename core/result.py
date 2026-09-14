"""The shared vocabulary for what an analysis engine found: PASS, VIOLATION, ERROR, SKIP."""

from __future__ import annotations

from dataclasses import dataclass

PASS = "PASS"              # the rule ran and found nothing
VIOLATION = "VIOLATION"    # the rule ran and found something
ERROR = "ERROR"            # the rule could not be evaluated -- `detail` says why
SKIP = "SKIP"              # the rule was never attempted


@dataclass(frozen=True)
class Result:
    """One engine's verdict on one target."""

    status: str
    detail: str = ""
    findings: int = 0

    def __str__(self) -> str:
        return f"{self.status}{f' ({self.detail})' if self.detail else ''}"

    @property
    def detected(self) -> bool:
        """True only for a real violation, since an ERROR never examined the code."""
        return self.status == VIOLATION


def worst(results) -> str:
    """The most severe status among several: ERROR beats VIOLATION beats PASS beats SKIP."""
    statuses = {r.status if isinstance(r, Result) else r for r in results}
    for status in (ERROR, VIOLATION, PASS):
        if status in statuses:
            return status
    return SKIP


#: Shell exit codes, so commands compose. Matches the ArchUnit Runner's own contract.
EXIT_CODE = {PASS: 0, SKIP: 0, VIOLATION: 1, ERROR: 2}
