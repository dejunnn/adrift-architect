"""Assemble a system prompt by joining and $slot-substituting the text files in `prompts/`."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from string import Template

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"


def text(name: str) -> str:
    """One prompt file, raw, with its `$slots` still in place."""
    return (PROMPTS / f"{name}.txt").read_text(encoding="utf-8")


def block(name: str, **slots: str) -> str:
    """One prompt file with its `$slots` filled in; raises at assembly time on a missing slot."""
    return Template(text(name)).substitute(**slots)


def user(adr: str, **slots: str) -> str:
    """The user message: the decision record plus whatever grounding this arm supplies."""
    return block("enforce_user", adr=adr.strip(),
                 **{key: (value or "").strip() for key, value in slots.items()})


#: Ceilings on the grounding documents, in bytes of JSON -- a tripwire, not a budget.
LIMITS = {"fingerprint": 200_000, "surface": 600_000, "source": 500_000}


def check_size(kind: str, document: str, remedy: str) -> None:
    """Refuse a grounding document too large to be worth sending. Raises SystemExit."""
    ceiling = int(os.environ.get(f"ADRIFT_MAX_{kind.upper()}_BYTES", LIMITS[kind]))
    if len(document) <= ceiling:
        return
    raise SystemExit(
        f"{kind} is {len(document):,} bytes ({len(document) // 4:,} tokens, roughly) against a "
        f"ceiling of {ceiling:,}. That is too large to send usefully.\n"
        f"  Scope it:   {remedy}\n"
        f"  Or raise:   ADRIFT_MAX_{kind.upper()}_BYTES=<bytes>  (record the value -- it is a "
        f"different condition)")


def digest(system: str) -> str:
    """A short stable id -- twelve hex characters of SHA-256 -- for the exact prompt text used."""
    return hashlib.sha256(system.encode("utf-8")).hexdigest()[:12]


# ------------------------------------------------------------------------------- inspector
# Show what reaches a model without sending it. Imports sit inside the functions to avoid a cycle.


def _arms() -> dict:
    """Every arm, as (system message, response schema). Assembled, not sent."""
    from enforcer import prompt as ep
    from mutator import prompt as mp
    return {
        "enforce-generate":           (ep.SYSTEM_TOOLS, ep.RESPONSE_TOOLS),
        "enforce-generate-catalogue": (ep.SYSTEM_TOOLS_CATALOGUE, ep.RESPONSE_TOOLS_CATALOGUE),
        "enforce-probe":              (ep.SYSTEM_PROBE, ep.RESPONSE_PROBE),
        # `enforce-analyse` (Arm D) is absent: it was scoped but never implemented.
        # `catalogue` goes to BOTH halves, because the schema varies with the arm too.
        "mutate-generate":            (mp.system(catalogue=False), mp.response(catalogue=False)),
        "mutate-generate-catalogue":  (mp.system(catalogue=True), mp.response(catalogue=True)),
        "mutate-probe":               (mp.system(probe=True), mp.response(probe=True)),
    }


def _descriptions(node, found=None) -> list:
    """Every `description` string in a schema -- the part of it that reads as instruction."""
    found = [] if found is None else found
    if isinstance(node, dict):
        if isinstance(node.get("description"), str):
            found.append(node["description"])
        for value in node.values():
            _descriptions(value, found)
    elif isinstance(node, list):
        for value in node:
            _descriptions(value, found)
    return found


def main(argv=None) -> int:
    """Print what an arm sends, without sending it."""
    import argparse
    import json as _json

    parser = argparse.ArgumentParser(
        prog="python -m core.prompts",
        description="Show what reaches the model: the system message, the response schema, "
                    "and the blocks generated from code rather than from prompts/.")
    parser.add_argument("--arm", help="which arm to show (default: list them)")
    parser.add_argument("--schema", action="store_true",
                        help="the response schema instead of the system message")
    parser.add_argument("--descriptions", action="store_true",
                        help="only the schema's description strings, which are instructions "
                             "the model reads and which live in no prompt file")
    parser.add_argument("--blocks", action="store_true",
                        help="the two blocks generated from code: the ArchUnit catalogue and "
                             "the OpenRewrite recipe listing")
    args = parser.parse_args(argv)

    if args.blocks:
        from enforcer.archunit import catalogue
        from mutator.openrewrite import catalogue as recipe_catalogue
        for title, source, arm, body in (
                ("ARCHUNIT CATALOGUE", "enforcer/archunit/catalogue.py::describe()",
                 "enforce-generate-catalogue", catalogue.describe()),
                # Rendered from the module whose ids and option keys came from the plugin itself.
                ("OPENREWRITE CATALOGUE", "mutator/openrewrite/catalogue.py::describe()",
                 "mutate-generate-catalogue", recipe_catalogue.describe())):
            print("=" * 78)
            print(f"{title}  <- {source}")
            print(f"   sent only by: {arm}   ({len(body):,} chars)")
            print("=" * 78)
            print(body)
            print()
        return 0

    arms = _arms()
    if not args.arm:
        print(f"{'arm':30}{'system':>9}{'schema':>9}{'descriptions':>14}  promptSha")
        for name, (system, schema) in arms.items():
            body = _json.dumps(schema)
            print(f"{name:30}{len(system):>9,}{len(body):>9,}"
                  f"{len(''.join(_descriptions(schema))):>14,}  {digest(system)}")
        print("\n  --arm <name>            the exact system message")
        print("  --arm <name> --schema   the response schema, as sent")
        print("  --blocks                the two blocks generated from code")
        return 0

    if args.arm not in arms:
        raise SystemExit(f"unknown arm {args.arm!r}; one of: {', '.join(arms)}")
    system, schema = arms[args.arm]
    if args.descriptions:
        for line in _descriptions(schema):
            print(f"  - {line}")
    elif args.schema:
        print(_json.dumps(schema, indent=2))
    else:
        print(system)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
