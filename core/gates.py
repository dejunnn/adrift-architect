"""The shared vocabulary for what can be wrong with a generated artefact: declined, renderable, grounded."""

from __future__ import annotations

RENDERABLE = "renderable"
GROUNDED = "grounded"

#: The model said it could not express this at all -- counted apart, never scored as a defect.
DECLINED = "declined"

#: The order gates are reported in, cheapest and most fundamental first.
ORDER = (DECLINED, RENDERABLE, GROUNDED)


def record(renderable, grounded, *, grounded_blocks: bool, declined=()) -> dict:
    """The gate record for one artefact, including which gates actually blocked it."""
    renderable, grounded, declined = list(renderable), list(grounded), list(declined)
    return {
        DECLINED: declined,
        RENDERABLE: renderable,
        GROUNDED: grounded,
        "groundedBlocks": grounded_blocks,
        "blocking": declined + renderable + (grounded if grounded_blocks else []),
    }


def blocking(item: dict) -> list[str]:
    """Why this artefact was not used, or empty if it was."""
    gates = item.get("gates")
    if isinstance(gates, dict):
        return list(gates.get("blocking") or [])
    return list(item.get("problems") or [])


def observed(item: dict, gate: str) -> list[str]:
    """What one gate found, whether or not it blocked. Empty for artefacts predating the record."""
    gates = item.get("gates")
    return list(gates.get(gate) or []) if isinstance(gates, dict) else []


def tally(items) -> dict:
    """Counts for the run record: how many artefacts, how many each gate caught, how many used."""
    items = list(items)
    counts = {"total": len(items), "used": sum(1 for i in items if not blocking(i))}
    for gate in ORDER:
        counts[gate] = sum(1 for i in items if observed(i, gate))
    return counts


def report(items, noun: str) -> str:
    """The one summary line both pipelines print, flagging gates that recorded without blocking."""
    items = list(items)
    counts = tally(items)
    blocks = {DECLINED: True, RENDERABLE: True,
              GROUNDED: any((i.get("gates") or {}).get("groundedBlocks") for i in items)}
    wording = {DECLINED: "declined by the model",
               RENDERABLE: "not renderable", GROUNDED: "not grounded"}
    parts = [f"{counts['used']} of {counts['total']} {noun}(s) usable"]
    for gate in ORDER:
        if counts[gate]:
            parts.append(f"{counts[gate]} {wording[gate]}"
                         + ("" if blocks[gate] else " (recorded, not blocking)"))
    return "  --  ".join(parts)
