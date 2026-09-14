"""Describe one repository from a single walk: the fingerprint, the mutation surface, or both."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fingerprint import census, read, render_census, render_surface, surface
from fingerprint.constants import ASSET_PATTERNS, DATASET_ROOT, TEST_PATTERNS


def dataset_projects() -> dict[str, Path]:
    """Every project in .dataset, by directory name."""
    return {
        project.name: project
        for bucket in sorted(DATASET_ROOT.glob("dataset-*")) if bucket.is_dir()
        for project in sorted(bucket.iterdir()) if project.is_dir()
    }


def _emit(document: dict, renderer, as_json: bool, output: Path | None) -> None:
    # separators drop the space after ':' and ',', free savings on a punctuation-heavy document.
    text = (json.dumps(document, indent=1, separators=(",", ":")) + "\n" if as_json
            else renderer(document))
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        print(f"written to {output}", file=sys.stderr)
    else:
        print(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", nargs="?", help="a project name from .dataset")
    parser.add_argument("--path", type=Path, help="describe an arbitrary directory")
    parser.add_argument("--list", action="store_true", help="list dataset projects")
    parser.add_argument("--surface", action="store_true",
                        help="emit the mutation surface instead of the fingerprint")
    parser.add_argument("--both", action="store_true",
                        help="write both documents; -o names the fingerprint and the surface "
                             "goes beside it as <name>.surface.<ext>")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    parser.add_argument("-o", "--output", type=Path, help="write here instead of stdout")
    parser.add_argument("--exclude-tests", action="store_true", help="omit test sources")
    parser.add_argument("--exclude-assets", action="store_true",
                        help="omit images, fonts and archives")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                        help="omit paths matching this fnmatch pattern (repeatable)")
    parser.add_argument("--packages", action="append", default=[], metavar="PKG",
                        help="surface only: restrict to this package and those under it "
                             "(repeatable). The surface enumerates where the census counts, "
                             "so scoping it to the packages a decision names is usually worth "
                             "doing on a large repository.")
    parser.add_argument("--methods", action="store_true",
                        help="surface only: include method lists. Off by default -- only two "
                             "recipes take a method pattern, and the lists are ~20%% of the "
                             "document.")
    args = parser.parse_args(argv)

    projects = dataset_projects()
    if args.list:
        for name in projects:
            print(name)
        return 0

    if args.path:
        root, name = args.path, args.path.resolve().name
    elif args.project:
        if args.project not in projects:
            print(f"unknown project: {args.project}", file=sys.stderr)
            return 2
        root, name = projects[args.project], args.project
    else:
        parser.error("give a project name, or --path, or --list")

    exclude = tuple(args.exclude)
    if args.exclude_tests:
        exclude += TEST_PATTERNS
    if args.exclude_assets:
        exclude += ASSET_PATTERNS

    try:
        found = read(root, name, exclude)
    except RuntimeError as error:               # tree-sitter missing
        print(error, file=sys.stderr)
        return 2

    scoped = tuple(args.packages)
    if args.both:
        _emit(census(found), render_census, args.json, args.output)
        beside = args.output.with_suffix(f".surface{args.output.suffix}") if args.output \
            else None
        _emit(surface(found, scoped, args.methods), render_surface, args.json, beside)
    elif args.surface:
        _emit(surface(found, scoped, args.methods), render_surface, args.json, args.output)
    else:
        _emit(census(found), render_census, args.json, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
