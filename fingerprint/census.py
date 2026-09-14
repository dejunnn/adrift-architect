"""The fingerprint: a complete structural census of a repository -- counts and names, no instances."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from fingerprint.constants import (BUILD_FILES, CHECK_MARKERS, CHECK_PATTERNS,
                                   GRADLE_DEPENDENCY, MAVEN_DEPENDENCY, NAME_SUFFIX,
                                   NAMED_EXTENSIONS, SOURCE_ROOT_HINTS)
from fingerprint.walk import Walk


def ranked(counter: Counter[str]) -> dict[str, int]:
    """Every entry, by count descending then key ascending, so ties break deterministically."""
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def resolve_annotation(simple: str, imports: dict[str, str]) -> str | None:
    """The fully-qualified name of an annotation, or None when it cannot be resolved -- never guessed."""
    if "." in simple:                      # already qualified at the use site
        return simple
    return imports.get(simple)


def declared_dependencies(root: Path, build_files: list[str]) -> list[str]:
    """Libraries the build declares, as `group:artifact`, by regex over the build files."""
    found: set[str] = set()
    for relative in build_files:
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if path.name == "pom.xml":
            found.update(f"{g}:{a}" for g, a in MAVEN_DEPENDENCY.findall(text))
        elif path.name.startswith("build.gradle"):
            found.update(f"{g}:{a}" for g, a in GRADLE_DEPENDENCY.findall(text))
    return sorted(found)


def census(found: Walk) -> dict:
    """The fingerprint document, from one walk."""
    languages: Counter[str] = Counter()
    directories: Counter[str] = Counter()
    suffixes: Counter[str] = Counter()
    build_files: set[str] = set()
    existing_checks: set[str] = set()
    source_roots: set[str] = set()

    # Pass over the paths: every file contributes, whatever language it is written in.
    for posix in found.files:
        relative = Path(posix)
        suffix = relative.suffix.lower()
        languages[suffix] += 1

        parent = relative.parent.as_posix()
        directories["(repository root)" if parent == "." else parent] += 1

        parts = relative.parts
        if len(parts) > 1 and parts[0] in SOURCE_ROOT_HINTS:
            # Up to THREE components, so `src/main/java` and `src/test/java` stay distinct.
            source_roots.add("/".join(parts[:min(3, len(parts) - 1)]))

        if relative.name in BUILD_FILES:
            build_files.add(posix)
        for marker, label in CHECK_MARKERS:
            if relative.name == marker:
                existing_checks.add(label)
        for pattern, label in CHECK_PATTERNS:
            if pattern.search(posix):
                existing_checks.add(label)

        if suffix in NAMED_EXTENSIONS:
            # Filename only -- no parser needed, so Kotlin naming still shows up.
            named = NAME_SUFFIX.search(relative.stem)
            if named:
                suffixes[named.group(1)] += 1

    # Pass over the parsed contents. Java only -- every section it fills is named `java*`.
    packages: Counter[str] = Counter()
    external: Counter[str] = Counter()
    positions: dict[str, Counter[str]] = {p: Counter()
                                          for p in ("class", "method", "field", "parameter")}
    unresolved: Counter[str] = Counter()
    unparsed_files: list[str] = []

    for source in found.sources:
        if not source.clean:
            # A tree with ERROR nodes still yields partial data, so the files are named.
            unparsed_files.append(source.path)
        if source.package:
            packages[source.package] += 1
        for fqn in source.imports.values():
            external[".".join(fqn.split(".")[:2])] += 1
        for position, simple in source.annotations:
            resolved = resolve_annotation(simple, source.imports)
            if resolved:
                positions.setdefault(position, Counter())[resolved] += 1
            else:
                unresolved[simple] += 1

    by_directory: dict[str, list[str]] = {}
    for posix in found.files:
        directory, _, filename = posix.rpartition("/")
        by_directory.setdefault(directory or ".", []).append(filename)

    excluded = found.excluded
    return {
        "projectName": found.name,

        # What a consumer may conclude from this document, and what it may not.
        "documentScope": {
            "isCompleteAccounting": not excluded,
            "isCappedOrTruncated": False,
            "meaningOfAbsence": (
                "a name absent from this document is absent from the project, EXCEPT in "
                "languages listed under languagesPresentButNotParsed"
                + (", and EXCEPT paths matching excludedPathPatterns, which were filtered "
                   "out of this run" if excluded else "")),
            "excludedPathPatterns": excluded,
            "parsedLanguage": "java (tree-sitter)",
            "languagesPresentButNotParsed": found.unparsed_languages,
            "notCollected": [
                "the dependency graph -- which package imports which",
                "which class carries which annotation or sits in which package",
                "method and field names",
            ],
            "whyNotCollected": "those are the ANSWER a check should assert; supplying them "
                               "invites deriving the check from the code, which produces a "
                               "rule that cannot fail. The mutation surface reports them "
                               "separately, for a consumer that rewrites code rather than "
                               "checking it.",
        },

        "totalFileCount": len(found.files),
        "fileCountByExtension": ranked(languages),
        "likelySourceRootDirectories": sorted(source_roots),
        "buildDescriptorFilePaths": sorted(build_files),
        "dependenciesDeclaredInBuildFiles": declared_dependencies(found.root,
                                                                  sorted(build_files)),
        "architectureCheckToolsAlreadyInProject": sorted(existing_checks),

        # Java-only, from parsed source. The key says so: a Kotlin package will not appear here.
        "javaPackageNamesByDeclarationCount": ranked(packages),
        "javaAnnotationsByPositionAndUseCount": {
            "onClasses": ranked(positions["class"]),
            "onMethods": ranked(positions["method"]),
            "onFields": ranked(positions["field"]),
            "onParameters": ranked(positions["parameter"]),
            "unresolvableToFullyQualifiedName": ranked(unresolved),
        },
        "javaImportedExternalPackagePrefixesByCount": ranked(external),
        "javaFileCountParsed": len(found.sources),
        "javaFilesTreeSitterCouldNotFullyParse": sorted(unparsed_files),

        # From filenames, so Kotlin contributes here too.
        "classNameSuffixesByCount": ranked(suffixes),

        "allFilePathsGroupedByDirectory": by_directory,
    }


def render(document: dict) -> str:
    """The census as markdown, with empty sections stated as "(none found)" rather than omitted."""
    def bullets(items) -> list[str]:
        rendered = [f"- {item}" for item in items]
        return rendered or ["- (none found)"]

    def counted(mapping: dict) -> list[str]:
        return bullets(f"{name or '(no extension)'}: {count}"
                       for name, count in mapping.items())

    scope = document["documentScope"]
    annotations = document["javaAnnotationsByPositionAndUseCount"]
    lines = [
        f"# Project fingerprint: {document['projectName']}",
        "",
        "Complete accounting: nothing below is capped or truncated, so a name absent from",
        "this document is absent from the project."
        + ("" if scope["isCompleteAccounting"] else
           "\nEXCEPT for paths matching the exclusion patterns listed near the end."),
        "",
        f"Files (build output and VCS metadata excluded): {document['totalFileCount']}",
        "",
        "## File count by extension",
        *counted(document["fileCountByExtension"]),
        "",
        "## Likely source root directories",
        *bullets(document["likelySourceRootDirectories"]),
        "",
        "## Build descriptor files",
        *bullets(document["buildDescriptorFilePaths"]),
        "",
        f"## Java package names ({len(document['javaPackageNamesByDeclarationCount'])}), "
        "by declaration count",
        "These are the REAL package names in this repository, in full. A check's package",
        "patterns must be drawn from this list, not invented.",
        "",
        *counted(document["javaPackageNamesByDeclarationCount"]),
        "",
        "## Java annotations on CLASSES, by use count",
        "Use these fully-qualified names verbatim. `javax.` and `jakarta.` are different",
        "packages and only one of them is present here.",
        "",
        *counted(annotations["onClasses"]),
        "",
        "## Java annotations on METHODS, by use count",
        *counted(annotations["onMethods"]),
        "",
        "## Java annotations on FIELDS, by use count",
        *counted(annotations["onFields"]),
        "",
        "## Java annotations on PARAMETERS, by use count",
        *counted(annotations["onParameters"]),
        "",
        "## Java annotations NOT resolvable to a fully-qualified name",
        "Same-package or wildcard-imported. Present in the project, but their full names",
        "are not visible in the files that use them.",
        "",
        *counted(annotations["unresolvableToFullyQualifiedName"]),
        "",
        "## Class-name suffixes, by count (from filenames, so Kotlin is included)",
        *counted(document["classNameSuffixesByCount"]),
        "",
        "## Java imported external package prefixes, by count",
        "An allow-list parameter must enumerate these, or the check reports every framework",
        "call as a violation.",
        "",
        *counted(document["javaImportedExternalPackagePrefixesByCount"]),
        "",
        "## Dependencies declared in build files",
        *bullets(document["dependenciesDeclaredInBuildFiles"]),
        "",
        "## Architecture check tools already in this project",
        *bullets(document["architectureCheckToolsAlreadyInProject"]),
        "",
        f"## Java files tree-sitter could not fully parse "
        f"({len(document['javaFilesTreeSitterCouldNotFullyParse'])} of "
        f"{document['javaFileCountParsed']})",
        *bullets(document["javaFilesTreeSitterCouldNotFullyParse"]),
        "",
        "## Languages present but NOT parsed",
        "These files appear in the listing below but were never opened. They contribute no",
        "packages, imports or annotations -- so their absence from those sections means",
        "nothing.",
        "",
        *bullets(scope["languagesPresentButNotParsed"]),
        "",
        "## Deliberately not collected",
        *bullets(scope["notCollected"]),
        "",
        scope["whyNotCollected"],
        "",
        f"## All file paths, grouped by directory ({document['totalFileCount']} files)",
    ]
    for directory, names in document["allFilePathsGroupedByDirectory"].items():
        lines.append(f"- {directory}/")
        lines += [f"  - {name}" for name in names]
    return "\n".join(lines)
