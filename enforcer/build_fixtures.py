"""Compile the cleanroom fixtures to bytecode -- each side alone, no classpath -- before any rule is scored."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from enforcer import engines

REPO_ROOT = Path(__file__).resolve().parents[1]


def sides(fixtures: Path, wanted: list[str] | None) -> list[Path]:
    """The fixture trees to compile: the compliant `A` first, then the `B-*` variants, sorted."""
    found = [fixtures / "A"] + sorted(p for p in fixtures.glob("B-*") if p.is_dir())
    found = [p for p in found if p.is_dir()]
    if wanted:
        keep = set(wanted)
        found = [p for p in found if p.name in keep]
        missing = keep - {p.name for p in found}
        if missing:
            raise SystemExit(f"no such fixture: {', '.join(sorted(missing))}")
    return found


def compile_side(javac: str, src: Path, out: Path, release: str) -> str | None:
    """Compile one fixture tree; returns None on success, or the first line of the failure."""
    java_files = sorted(str(p) for p in src.rglob("*.java"))
    if not java_files:
        return None
    out.mkdir(parents=True, exist_ok=True)
    done = subprocess.run([javac, "--release", release, "-d", str(out), *java_files],
                          capture_output=True, text=True)
    if done.returncode == 0:
        return None
    lines = [l for l in (done.stderr or done.stdout).splitlines() if l.strip()]
    return lines[0] if lines else f"javac exited {done.returncode}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m enforcer.build_fixtures",
        description="compile the cleanroom fixtures so ArchUnit rules can be scored against them")
    parser.add_argument("--fixtures", default="cleanroom/fixtures",
                        help="directory holding A and the B-* variants")
    parser.add_argument("--into", default=".work/cleanroom",
                        help="where the per-side class directories are written")
    parser.add_argument("--release", default="21", help="javac --release; ArchUnit reads up to 23")
    parser.add_argument("--only", nargs="*", metavar="SIDE",
                        help="compile just these fixtures, e.g. A B-0001")
    args = parser.parse_args(argv)

    javac = engines.tool_path("javac")
    if not javac:
        print("javac not found. Install a JDK (21 or newer), or set ADRIFT_JAVAC.",
              file=sys.stderr)
        return 2

    fixtures, into = Path(args.fixtures), Path(args.into)
    if not fixtures.is_dir():
        print(f"no fixtures at {fixtures}", file=sys.stderr)
        return 2

    targets = sides(fixtures, args.only)
    print(f"compiling {len(targets)} fixture(s) at --release {args.release} -> {into}")
    failed = []
    for src in targets:
        why = compile_side(javac, src, into / src.name, args.release)
        if why:
            failed.append(src.name)
            print(f"  FAILED  {src.name}: {why}")
    classes = len(list(into.rglob("*.class"))) if into.exists() else 0
    print(f"  {classes} class file(s) under {into}")
    if failed:
        print(f"  {len(failed)} fixture(s) did not compile: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
