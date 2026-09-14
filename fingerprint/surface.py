"""The mutation surface: every type this repository declares, named in full, for aiming a rewrite."""

from __future__ import annotations

from fingerprint.walk import Walk


def _build_system(files: list[str]) -> str:
    """Which build tool drives this project, since it decides what can be applied to it."""
    names = {path.rpartition("/")[2] for path in files}
    if "pom.xml" in names:
        return "maven"
    if names & {"build.gradle", "build.gradle.kts"}:
        return "gradle"
    return "unknown"


def surface(found: Walk, packages: tuple[str, ...] = (),
            include_methods: bool = False) -> dict:
    """The mutation surface document from one walk, optionally scoped by package and method lists."""
    def wanted(package: str) -> bool:
        return not packages or any(package == p or package.startswith(p + ".")
                                   for p in packages)

    types = []
    for source in found.sources:
        if not wanted(source.package or ""):
            continue
        for declared in source.types:
            package = source.package or ""
            # `package` and `simpleName` are NOT emitted -- both derive from `fqn`. `path` IS kept.
            types.append({
                "fqn": f"{package}.{declared.name}" if package else declared.name,
                "kind": declared.kind,
                "path": source.path,
                "modifiers": declared.modifiers,
                "annotations": [source.imports.get(a, a) for a in declared.annotations],
                "extends": declared.extends,
                "implements": declared.implements,
                "fields": [
                    {"name": m.name, "type": m.type, "modifiers": m.modifiers,
                     "annotations": [source.imports.get(a, a) for a in m.annotations]}
                    for m in declared.members if m.kind == "field"],
                "methods": [
                    {"name": m.name, "returns": m.type, "modifiers": m.modifiers,
                     "annotations": [source.imports.get(a, a) for a in m.annotations]}
                    for m in declared.members if m.kind in ("method", "constructor")
                ] if include_methods else [],
            })
    # An empty value carries nothing a reader could not assume, at eleven keys per type.
    types = [{key: value for key, value in entry.items() if value not in ("", [], {})}
             for entry in types]
    types.sort(key=lambda entry: entry["fqn"])

    declared_packages = sorted({source.package for source in found.sources
                                if source.package and wanted(source.package)})
    external = sorted({".".join(fqn.split(".")[:2])
                       for source in found.sources for fqn in source.imports.values()})

    return {
        "projectName": found.name,
        "documentScope": {
            "purpose": "aiming a source-rewriting recipe at code that exists in this "
                       "repository right now",
            "isCompleteAccounting": not found.excluded,
            "excludedPathPatterns": found.excluded,
            "parsedLanguage": "java (tree-sitter)",
            "languagesPresentButNotParsed": found.unparsed_languages,
            "notCollected": [
                "source text -- a recipe takes structured parameters, not prose",
                "method bodies and statement-level detail",
            ] + ([] if include_methods else ["method lists (pass include_methods)"]),
            "restrictedToPackages": list(packages),
            "relationToFingerprint": "the fingerprint reports this repository's SHAPE, in "
                                     "patterns, for writing a check that must generalise. "
                                     "This reports its INHABITANTS, by name, for writing a "
                                     "rewrite that must resolve. Neither replaces the other.",
        },
        "buildSystem": _build_system(found.files),
        "sourceRoots": sorted({path.rsplit("/", 1)[0] for path in found.files
                               if path.endswith(".java")}),
        "packages": declared_packages,
        "externalPackagePrefixes": external,
        "typeCount": len(types),
        "types": types,
    }


def render(document: dict) -> str:
    """The surface as markdown, for a person checking what a recipe could name."""
    lines = [
        f"# Mutation surface: {document['projectName']}",
        "",
        document["documentScope"]["relationToFingerprint"],
        "",
        f"Build system: {document['buildSystem']}",
        f"Types declared: {document['typeCount']}",
        "",
        "## Packages",
        *([f"- {name}" for name in document["packages"]] or ["- (none found)"]),
        "",
        "## Declared types",
    ]
    for entry in document["types"]:
        signature = " ".join([*entry.get("modifiers", []), entry["kind"]])
        lines.append(f"- `{entry['fqn']}` -- {signature}")
        lines.append(f"  - declared in {entry['path']}")
        if entry.get("annotations"):
            lines.append(f"  - annotated {', '.join(entry['annotations'])}")
        for member in entry.get("fields", []):
            declared = " ".join(filter(None, [*member.get("modifiers", []),
                                              member.get("type", ""), member["name"]]))
            lines.append(f"  - field  {declared}")
        for member in entry.get("methods", []):
            declared = " ".join(filter(None, [*member.get("modifiers", []),
                                              member.get("returns", ""), member["name"]]))
            lines.append(f"  - method {declared}")
    return "\n".join(lines)
