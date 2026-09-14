"""Do the names a generated rule uses exist in the repository it was generated for? Recorded, never rejected."""

from __future__ import annotations

import json
import re

#: The ArchUnit calls whose arguments are package identifiers BY POSITION, not by shape.
_PACKAGE_CALL = re.compile(
    r'reside(?:InAny|InA|OutsideOfAny|OutsideOfA|OutsideOf)Packages?\s*\(([^)]*)\)')

#: Quoted string literals, once a package call site has been isolated.
_LITERAL = re.compile(r'"([^"]*)"')

#: `pattern: import a.b.c` in a Semgrep rule, with or without a trailing wildcard.
_SEMGREP_IMPORT = re.compile(r'^\s*(?:-\s*)?pattern(?:-not)?\s*:\s*import\s+([\w.$*]+)', re.M)

#: A string that is a well-formed ArchUnit package identifier, leading `..` wildcard included.
_PACKAGEISH = re.compile(r'^(?=.*[A-Za-z])[A-Za-z0-9_$.*]+$')


def _known(fingerprint: dict) -> tuple[frozenset[str], tuple[str, ...]]:
    """The packages this repository declares, and the external prefixes it imports."""
    declared = frozenset(fingerprint.get("javaPackageNamesByDeclarationCount") or {})
    external = tuple(fingerprint.get("javaImportedExternalPackagePrefixesByCount") or {})
    return declared, external


def _resolves(identifier: str, declared: frozenset[str], external: tuple[str, ...]) -> bool:
    """Whether one ArchUnit package identifier selects anything this repository contains."""
    identifier = identifier.strip()
    if not identifier or not _PACKAGEISH.match(identifier):
        return False
    # Two consecutive `*` is a filesystem glob, not a package identifier, and grounds nothing.
    if "**" in identifier:
        return False

    core = identifier.strip(".")
    leading, trailing = identifier.startswith(".."), identifier.endswith("..")
    if not core:
        return True                                     # `..` selects everything

    candidates = list(declared) + [p.rstrip(".") for p in external]
    wanted = [s for s in core.split(".") if s]

    for package in candidates:
        segments = package.split(".")
        if leading and trailing:                        # ..a.b.. -- anywhere in the package
            if any(segments[i:i + len(wanted)] == wanted
                   for i in range(len(segments) - len(wanted) + 1)):
                return True
        elif leading:                                   # ..a.b   -- at the end
            if segments[-len(wanted):] == wanted:
                return True
        elif trailing:                                  # a.b..   -- at the start
            if segments[:len(wanted)] == wanted:
                return True
        else:                                           # a.b     -- exactly, or either prefix
            if segments == wanted or segments[:len(wanted)] == wanted \
                    or wanted[:len(segments)] == segments:
                return True
    # A single `*` stands for one segment; too weak to resolve, and too common to report.
    return "*" in identifier


def identifiers(engine: str, body) -> list[str]:
    """The strings this rule uses where a package identifier is required, chosen by position."""
    text = "\n".join(body) if isinstance(body, list) else (body or "")
    if engine == "archunit":
        return [lit for args in _PACKAGE_CALL.findall(text) for lit in _LITERAL.findall(args)]
    if engine == "semgrep":
        # `import $PKG.*` binds a metavariable and names no package.
        return [m.rstrip(".*") or m for m in _SEMGREP_IMPORT.findall(text)
                if not m.lstrip(".").startswith("$")]
    return []                                           # conftest: see the module docstring


def ungrounded(engine: str, body, fingerprint: dict) -> list[str]:
    """Every package identifier in this rule that names nothing the repository contains."""
    declared, external = _known(fingerprint)
    if not declared and not external:
        return []
    seen, found = set(), []
    for identifier in identifiers(engine, body):
        if identifier in seen:
            continue
        seen.add(identifier)
        if not _PACKAGEISH.match(identifier.strip()) or "**" in identifier:
            found.append(f"{identifier!r} is not a package identifier")
        elif not _resolves(identifier, declared, external):
            found.append(f"{identifier!r} names no package in this repository")
    return found


def load(fingerprint_json: str) -> dict:
    """The fingerprint as a dict, or an empty one -- grounding is never a reason to fail a run."""
    try:
        parsed = json.loads(fingerprint_json)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}
