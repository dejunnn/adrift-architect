"""One traversal of a repository, producing the raw facts both census and surface are derived from."""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path

from fingerprint.constants import (DECLARATION_POSITIONS, EXCLUDED_DIRECTORIES, INSTALL_HINT,
                                   JVM_SOURCE_EXTENSIONS, MEMBER_KINDS, MODIFIERS, NAME_NODES,
                                   PARSED_EXTENSION, TYPE_KINDS)


# ------------------------------------------------------------------------------ the facts


@dataclass(frozen=True)
class Member:
    """One field, method or constructor of a type."""

    name: str
    kind: str                       # field | method | constructor
    modifiers: list[str]
    type: str = ""                  # declared type, or return type; "" for a constructor
    annotations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TypeDecl:
    """One declared type with the members a rewrite could aim at; `name` is dotted for a nested type."""

    name: str
    kind: str                       # class | interface | enum | record | annotation
    modifiers: list[str]
    annotations: list[str] = field(default_factory=list)
    extends: str = ""
    implements: list[str] = field(default_factory=list)
    members: list[Member] = field(default_factory=list)


@dataclass(frozen=True)
class SourceFile:
    """One parsed Java file."""

    path: str                       # relative, POSIX
    package: str | None
    imports: dict[str, str]         # simple name -> fully-qualified name
    annotations: list[tuple[str, str]]   # (position, simple name) -- for the census
    types: list[TypeDecl]
    clean: bool
    """False when tree-sitter hit an ERROR node; this file's facts are incomplete."""


@dataclass(frozen=True)
class Walk:
    """Everything one pass over a repository found."""

    root: Path
    name: str
    files: list[str]                # every authored file, relative POSIX, sorted
    excluded: list[str]             # the extra patterns this run filtered out
    sources: list[SourceFile]       # parsed .java only
    unparsed_languages: list[str]   # JVM extensions present but never opened

    def type_named(self, simple_or_dotted: str) -> tuple[SourceFile, TypeDecl] | None:
        """Find a declared type by simple or dotted name. None when absent -- a real answer."""
        for source in self.sources:
            for declared in source.types:
                if declared.name == simple_or_dotted \
                        or declared.name.split(".")[-1] == simple_or_dotted:
                    return source, declared
        return None


# --------------------------------------------------------------------------- the traversal


def load_parser():
    """The Java parser, or a RuntimeError carrying the install command -- there is no regex fallback."""
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_java
    except ImportError as error:
        raise RuntimeError(
            f"tree-sitter is required and not installed ({error}).\n  {INSTALL_HINT}") from error
    return Parser(Language(tree_sitter_java.language()))


def _first_name(node) -> str | None:
    """Text of the first descendant that looks like a name, breadth-first."""
    queue = [node]
    while queue:
        current = queue.pop(0)
        if current.type in NAME_NODES:
            return current.text.decode("utf-8", "ignore")
        queue.extend(current.children)
    return None


def _text_of(node) -> str:
    return node.text.decode("utf-8", "ignore") if node is not None else ""


def _named(node) -> str:
    """A declaration's own name, from the grammar's `name` field rather than the first identifier."""
    return _text_of(node.child_by_field_name("name"))


def _modifiers_node(node):
    return next((c for c in node.children if c.type == "modifiers"), None)


def _modifiers_and_annotations(node) -> tuple[list[str], list[str]]:
    """The keyword modifiers and the annotation names on one declaration."""
    holder = _modifiers_node(node)
    if holder is None:
        return [], []
    modifiers, annotations = [], []
    for child in holder.children:
        if "annotation" in child.type:
            name = _first_name(child)
            if name:
                annotations.append(name)
        elif child.type in MODIFIERS:
            modifiers.append(child.type)
    return modifiers, annotations


def _members(body) -> list[Member]:
    """The fields, methods and constructors declared DIRECTLY in one type body."""
    found: list[Member] = []
    if body is None:
        return found
    for child in body.children:
        kind = MEMBER_KINDS.get(child.type)
        if kind is None:
            continue
        modifiers, annotations = _modifiers_and_annotations(child)
        declared_type = _text_of(child.child_by_field_name("type"))
        if kind == "field":
            # One `field_declaration` can declare several names (`int a, b;`); each gets an entry.
            for declarator in child.children:
                if declarator.type != "variable_declarator":
                    continue
                name = _text_of(declarator.child_by_field_name("name"))
                if name:
                    found.append(Member(name=name, kind=kind, modifiers=modifiers,
                                        type=declared_type, annotations=annotations))
        else:
            name = _named(child)
            if name:
                found.append(Member(name=name, kind=kind, modifiers=modifiers,
                                    type=declared_type, annotations=annotations))
    return found


def parse_java(source: bytes, parser) -> tuple[str | None, dict[str, str],
                                               list[tuple[str, str]], list[TypeDecl], bool]:
    """Package, imports, positioned annotations, declared types, and whether the parse was clean."""
    tree = parser.parse(source)
    package: str | None = None
    imports: dict[str, str] = {}
    annotations: list[tuple[str, str]] = []
    types: list[TypeDecl] = []

    # (node, enclosing dotted type name), depth-first so a nested type knows what encloses it.
    stack = [(tree.root_node, "")]
    while stack:
        node, enclosing = stack.pop()

        if node.type == "package_declaration":
            package = _first_name(node)

        elif node.type == "import_declaration":
            text = _text_of(node)
            # A wildcard import resolves nothing, so it is skipped rather than guessed at.
            if not text.rstrip().endswith("*"):
                fqn = _first_name(node)
                if fqn and "." in fqn:
                    imports[fqn.rsplit(".", 1)[-1]] = fqn

        # A node can be BOTH a type declaration and an annotation site, so these are independent.
        if node.type in DECLARATION_POSITIONS:
            position = DECLARATION_POSITIONS[node.type]
            _, on_this = _modifiers_and_annotations(node)
            annotations += [(position, name) for name in on_this]

        inner = enclosing
        if node.type in TYPE_KINDS:
            simple = _named(node)
            if simple:
                inner = f"{enclosing}.{simple}" if enclosing else simple
                modifiers, on_type = _modifiers_and_annotations(node)
                types.append(TypeDecl(
                    name=inner,
                    kind=TYPE_KINDS[node.type],
                    modifiers=modifiers,
                    annotations=on_type,
                    extends=_text_of(node.child_by_field_name("superclass")).removeprefix(
                        "extends").strip(),
                    implements=[part.strip() for part in _text_of(
                        node.child_by_field_name("interfaces")).removeprefix("implements")
                        .split(",") if part.strip()],
                    members=_members(node.child_by_field_name("body")),
                ))

        stack.extend((child, inner) for child in node.children)

    return package, imports, annotations, types, not tree.root_node.has_error


def repository_files(root: Path, exclude: tuple[str, ...] = ()) -> list[Path]:
    """Every authored file under `root`, relative and sorted -- the sort order is the determinism."""
    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in EXCLUDED_DIRECTORIES for part in relative.parts):
            continue
        if any(fnmatch(relative.as_posix(), pattern) for pattern in exclude):
            continue
        found.append(relative)
    return sorted(found)


def walk(root: Path, name: str | None = None, exclude: tuple[str, ...] = ()) -> Walk:
    """Read one repository once. Every projection is derived from what this returns."""
    parser = load_parser()
    root = Path(root).resolve()
    files = repository_files(root, exclude)

    sources: list[SourceFile] = []
    unparsed_languages: set[str] = set()

    for relative in files:
        suffix = relative.suffix.lower()
        if suffix != PARSED_EXTENSION:
            if suffix in JVM_SOURCE_EXTENSIONS:
                unparsed_languages.add(suffix)
            continue
        try:
            text = (root / relative).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        package, imports, annotations, types, clean = parse_java(
            text.encode("utf-8", "ignore"), parser)
        sources.append(SourceFile(path=relative.as_posix(), package=package, imports=imports,
                                  annotations=annotations, types=types, clean=clean))

    return Walk(root=root, name=name or root.name,
                files=[path.as_posix() for path in files],
                excluded=sorted(exclude),
                sources=sources,
                unparsed_languages=sorted(unparsed_languages))
