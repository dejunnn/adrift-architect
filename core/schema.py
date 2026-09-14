"""Response-schema fragments shared by every arm, in the strict dialect every provider accepts."""

from __future__ import annotations

#: The clause statuses, in the order a report tallies them.
STATUSES = ("COVERED", "PARTIAL", "UNSUPPORTED")


def clauses(field: str, items: dict, considered: str) -> dict:
    """Schema for the clause account: each ADR clause with what was weighed, a reason and a verdict."""
    return {
        "type": "array",
        "description": "every clause of the ADR, accounted for -- covered or not",
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["id", "text", field, "reason", "status", "checkIds", "gap"],
            "properties": {
                "id": {"type": "string", "description": "C1, C2, ... in the order they appear"},
                "text": {"type": "string", "description": "the clause, quoted from the ADR"},
                field: {"type": "array", "items": items, "description": considered},
                "reason": {"type": "string",
                           "description": "why it is enforceable and by what, or why it "
                                          "cannot be checked -- and why you rejected anything "
                                          f"listed in {field}. Written BEFORE the verdict."},
                "status": {"type": "string", "enum": list(STATUSES)},
                "checkIds": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "every check enforcing this clause. Empty when UNSUPPORTED.",
                },
                "gap": {"type": "string",
                        "description": "what this clause requires that the checks in checkIds "
                                       "do NOT check. Empty string when nothing is left out. "
                                       "Required for PARTIAL; say plainly what is missing."},
            },
        },
    }


def rules(body_field: str, extra: dict | None = None) -> dict:
    """Schema for a list of rules: an id, the body as one array entry per line, source and extras."""
    properties = {
        "id": {"type": "string", "description": "kebab-case, unique across all lists"},
        body_field: {"type": "array", "items": {"type": "string"},
                     "description": "the artefact, ONE ARRAY ENTRY PER LINE, no trailing "
                                    "newlines. Indentation is part of the line."},
        "source": {"type": "string", "description": "the ADR sentence this enforces"},
        **(extra or {}),
    }
    return {
        "type": "array",
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": list(properties),
            "properties": properties,
        },
    }


def coverage_report(clause_list: list[dict]) -> str:
    """Render the clause account as a table, with gaps and rejected options on their own lines."""
    lines = []
    for clause in clause_list:
        lines.append(f"  {clause['id']:<4} {clause['status']:<12} "
                     f"{', '.join(clause.get('checkIds') or []) or '-':<34} "
                     f"{clause['text'][:60]}")
        considered = next((clause[key] for key in clause
                           if key.startswith("considered") and clause[key]), [])
        if considered:
            lines.append(f"       considered: {', '.join(considered)}")
        if (clause.get("gap") or "").strip():
            lines.append(f"       NOT CHECKED: {clause['gap']}")
    tally = {status: sum(1 for c in clause_list if c["status"] == status)
             for status in STATUSES}
    lines.append(f"  {len(clause_list)} clause(s): "
                 + ", ".join(f"{count} {status.lower()}" for status, count in tally.items()))
    gaps = sum(1 for c in clause_list if (c.get("gap") or "").strip())
    if gaps:
        lines.append(f"  {gaps} clause(s) report an unchecked gap")
    return "\n".join(lines)


def tally(clause_list: list[dict]) -> dict:
    """Clause statuses as counts, for the run record."""
    return {status: sum(1 for c in clause_list if c["status"] == status) for status in STATUSES}
