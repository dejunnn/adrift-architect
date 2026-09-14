"""Compile a decision into a check or mutation for a repository outside the corpus, regrounded against it."""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

from external import ground

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _run(command: list[str], log: pathlib.Path) -> int:
    """Run one documented command, tee its output to `log`, and return its exit status."""
    print("    $ " + " ".join(command))
    done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    log.write_text(done.stdout + done.stderr, encoding="utf-8")
    return done.returncode


def reground(cell: pathlib.Path, repo: pathlib.Path) -> dict:
    """Re-decide every mutation's grounding against the repository. Returns what changed."""
    path = cell / "mutations.json"
    answer = json.loads(path.read_text(encoding="utf-8"))
    idx = ground.index(repo)
    freed, still = 0, 0
    for mutation in answer.get("mutations", []):
        gates = mutation.setdefault("gates", {})
        if "surfaceGrounded" not in gates:
            gates["surfaceGrounded"] = list(gates.get("grounded") or [])
        problems = ground.ungrounded(mutation, repo, idx)
        gates["grounded"] = problems
        gates["regrounded"] = True
        gates["blocking"] = [p for p in problems] + list(gates.get("renderable") or [])
        mutation["problems"] = list(gates["blocking"])
        if gates["surfaceGrounded"] and not problems:
            freed += 1
        elif problems:
            still += 1
    path.write_text(json.dumps(answer, indent=1), encoding="utf-8")
    return {"freed": freed, "stillBlocked": still,
            "mutations": len(answer.get("mutations", []))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m external.pipeline")
    parser.add_argument("kind", choices=("check", "mutation"))
    parser.add_argument("--adr", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--into", default=".work/real-mutants")
    parser.add_argument("--classes", nargs="*", default=[])
    args = parser.parse_args(argv)

    cell, repo = pathlib.Path(args.out), pathlib.Path(args.repo)
    cell.parent.mkdir(parents=True, exist_ok=True)
    python = sys.executable
    module = "enforcer.enforce" if args.kind == "check" else "mutator.mutate"

    print(f"[1/2] generate ({args.kind})")
    code = _run([python, "-m", module, "generate", "--adr", args.adr, "--repo", args.repo,
                 "--provider", args.provider, "--out", args.out],
                pathlib.Path(str(cell) + ".generate.txt"))
    artefact = cell / ("rules.json" if args.kind == "check" else "mutations.json")
    if code != 0 or not artefact.exists():
        print(f"    generation produced no artefact (exit {code}) -- this is a RESULT, not a gap")
        return 1

    if args.kind == "mutation":
        moved = reground(cell, repo)
        print(f"    regrounded against {repo}: {moved['freed']} freed, "
              f"{moved['stillBlocked']} still blocked, of {moved['mutations']}")

    print(f"[2/2] {'execute' if args.kind == 'check' else 'apply'}")
    if args.kind == "check":
        command = [python, "-m", "enforcer.enforce", "execute", "--run", args.out,
                   "--repo", args.repo]
        if args.classes:
            command += ["--classes", *args.classes]
    else:
        command = [python, "-m", "mutator.mutate", "apply", "--run", args.out,
                   "--repo", args.repo, "--into", args.into]
    return _run(command, pathlib.Path(str(cell) + f".{args.kind}.txt"))


if __name__ == "__main__":
    raise SystemExit(main())
