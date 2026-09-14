"""Ground a mutation's names against the repository on disk, not against the types-only surface."""
from __future__ import annotations

import pathlib

GENERATED = "adrift.mutator.generated."
#: Extensions a mutation may name as a file to edit; anything with a separator is a path anyway.
FILE_SUFFIXES = (".xml", ".properties", ".yml", ".yaml", ".json", ".gradle", ".txt",
                 ".md", ".cfg", ".conf", ".toml", ".sql", ".dockerfile")


def _looks_like_path(name: str) -> bool:
    lower = name.lower()
    return "/" in name or lower.endswith(FILE_SUFFIXES) or lower in ("dockerfile", "makefile")


def index(repo: pathlib.Path) -> tuple[set[str], set[str]]:
    """Every type this repository declares, by simple and qualified name, and every file it contains."""
    types: set[str] = set()
    files: set[str] = set()
    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(repo).as_posix()
        files.add(rel)
        if path.suffix != ".java":
            continue
        types.add(path.stem)
        parts = rel.split("/")
        for root in ("java", "kotlin"):
            if root in parts:
                after = parts[parts.index(root) + 1:]
                types.add(".".join(after)[: -len(".java")])
                break
    return types, files


def ungrounded(mutation: dict, repo: pathlib.Path,
               declared_index: tuple[set[str], set[str]] | None = None) -> list[str]:
    """Names this mutation uses that the repository does not contain. Empty when it is grounded."""
    types, files = declared_index or index(repo)
    problems = []
    for name in sorted(set(mutation.get("targets") or [])):
        if not isinstance(name, str) or not name:
            continue
        if name.startswith(GENERATED):
            continue                                   # the harness compiles and installs it
        if _looks_like_path(name):
            if name in files or any(f.endswith("/" + name) for f in files):
                continue
            problems.append(f"{name!r} is not a file in this repository")
            continue
        if name in types or name.rsplit(".", 1)[-1] in types:
            continue
        if "." in name:
            continue                                   # a type from outside the project
        problems.append(f"{name!r} is neither a type this repository declares nor a file in it")
    return problems
