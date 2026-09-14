"""Compile a decision record into a source edit that breaks it, then prove a check catches it."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import replace
from pathlib import Path

import clients
from core import gates, llm, prompts, runlog, schema
from core.result import ERROR, SKIP, VIOLATION, worst
from enforcer import engines
from mutator import prompt, recipes
from mutator.openrewrite.apply import apply as run_recipe, install

REPO_ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------------------- generate


def _gates(mutation: dict, surface_doc: dict, adr_stem: str) -> dict:
    """Everything wrong with one mutation, found before anything is copied or built."""
    if mutation["expressible"] != recipes.YES:
        # Recorded as a DECLINE, never as a defect, so the denominator matches the behaviour.
        return gates.record([], [], grounded_blocks=True,
                            declined=[f"expressible={mutation['expressible']}"])
    grounded = recipes.ungrounded(mutation, surface_doc)
    renderable = []
    if "recipeList" in mutation:                # the tool-free arm writes no recipe
        recipe = recipes.from_answer(mutation, adr_stem[:4])
        for written in recipe.java:
            renderable += [f"{written.class_name}: {why}" for why in written.problems]
        if not recipe.recipe_list:
            renderable.append("expressible YES but recipeList is empty")
    return gates.record(renderable, grounded, grounded_blocks=True)


def _render_catalogue(answer: dict) -> list[str]:
    """Turn every catalogue selection into the recipe invocation it stands for, in place."""
    from mutator.openrewrite import catalogue as recipe_catalogue

    notes = []
    for mutation in answer.get("mutations") or []:
        selected = (mutation.get("catalogueRecipe") or "").strip()
        if not selected:
            mutation.pop("catalogueRecipe", None)
            mutation.pop("paramsJson", None)
            continue
        try:
            params = json.loads(mutation.get("paramsJson") or "{}")
            if not isinstance(params, dict):
                raise ValueError("paramsJson is not a JSON object")
        except (json.JSONDecodeError, ValueError) as error:
            mutation["problems"] = [f"paramsJson did not parse: {error}"]
            notes.append(f"{mutation.get('id')}: REJECTED {mutation['problems'][0]}")
            continue
        problems = recipe_catalogue.problems(selected, params)
        if problems:
            mutation["problems"] = problems
            notes.append(f"{mutation.get('id')}: REJECTED {'; '.join(problems)}")
            continue
        mutation["recipeList"] = [recipe_catalogue.render(selected, params)]
        mutation["params"] = params
        mutation.pop("paramsJson", None)
        notes.append(f"{mutation.get('id')}: rendered from catalogue recipe {selected!r}")
    return notes


def generate(args) -> int:
    """Compile one ADR into candidate mutations for one repository."""
    from fingerprint import census, read, surface as build_surface
    from fingerprint.constants import TEST_PATTERNS

    adr_file, repo = Path(args.adr).resolve(), Path(args.repo).resolve()
    llm.load_dotenv(REPO_ROOT / ".env")
    if getattr(args, "no_thinking", False):
        # See the enforcer's note: set before any client is built.
        os.environ[f"ADRIFT_{args.provider.upper()}_EFFORT"] = "none"
    # The catalogue the arm shows. Nothing is gated on it; recorded so offers are never pooled.
    from mutator.openrewrite import catalogue as recipe_catalogue
    offered = frozenset() if (args.probe or not args.catalogue) else frozenset(
        recipe_catalogue.CATALOGUE)

    run = runlog.Run(
        kind="mutate", subject=adr_file.stem, repo=repo.name,
        provider=args.provider,
        model=llm.setting(args.provider, "MODEL") or "unset",

        # One arm vocabulary across both pipelines; `kind` already records which pipeline this is.
        arm=("probe" if args.probe else "catalogue" if args.catalogue else "free"),
        flags={"mode": args.mode,
               "repoPath": str(repo), "adrPath": str(adr_file),
               "probe": args.probe,
               "vocabulary": "n/a" if args.probe else (
                   "catalogue+open" if args.catalogue else "open"),
               "catalogue": bool(args.catalogue) and not args.probe,
               # See the enforcer's note: an output budget, and a lowered one is its own condition.
               "maxTokens": llm.max_tokens(),
               # See the enforcer's note: Ollama bounds prompt plus completion with this instead.
               "numCtx": llm.num_ctx(),
               "effort": llm.effort(args.provider),
               "recipesOffered": len(offered),
               "surfacePackages": args.packages, "surfaceMethods": args.methods,
               "surfaceExcludesTests": args.exclude_tests},
    )
    if args.out:
        run.use_directory(Path(args.out).resolve())
    out = run.directory
    print(f"run:      {run.run_id}  ->  {out}")

    try:
        shutil.copy(adr_file, out / "adr.md")
        print(f"reading:  {repo} ...")
        walked = read(repo, exclude=TEST_PATTERNS if args.exclude_tests else ())
        fingerprint_json = json.dumps(census(walked), indent=1, separators=(",", ":")) + "\n"
        surface_doc = build_surface(walked, tuple(args.packages), args.methods)
        surface_json = json.dumps(surface_doc, indent=1, separators=(",", ":")) + "\n"
        run.write(f"{repo.name}_fingerprint.json", fingerprint_json)
        run.write(f"{repo.name}_surface.json", surface_json)
        print(f"surface:  {surface_doc['typeCount']} type(s), {len(surface_json):,} bytes, "
              f"build system {surface_doc['buildSystem']}")
        if not args.probe:
            print(f"recipes:  {'shortlist of ' + str(len(offered)) if args.catalogue
                                 else 'no catalogue,'} plus any the model writes")

        system, user, response_schema = prompt.build(
            adr_file.read_text(encoding="utf-8"), fingerprint_json, surface_json,
            args.probe, args.catalogue)
        run.flags["promptSha"] = prompts.digest(system)
        run.flags["fingerprintSha"] = prompts.digest(fingerprint_json)
        run.flags["surfaceSha"] = prompts.digest(surface_json)
        prompts.check_size("fingerprint", fingerprint_json,
                           "the fingerprint is a census and does not scope; use a smaller repo")
        prompts.check_size(
            "surface", surface_json,
            f"--packages <pkg> [<pkg> ...]   e.g. --packages "
            f"{next(iter(surface_doc.get('packages') or ['com.example']), )}")
        # The vocabulary is an input like any other, digested so settings are never pooled.
        run.flags["vocabularySha"] = prompts.digest(" ".join(sorted(offered)))
        # See the enforcer's note: the response schema is prompt text, not covered by promptSha.
        run.flags["schemaSha"] = ("none" if args.no_schema
                                  else prompts.digest(json.dumps(response_schema,
                                                                 sort_keys=True)))
        run.write("prompt.txt", f"=== SYSTEM ===\n{system}\n\n=== USER ===\n{user}")

        schema_doc = None if args.no_schema else response_schema
        engine = clients.for_provider(args.provider)
        if args.mode == "sync":
            print(f"provider: {args.provider} sync ...")
            exchange = engine.complete(system, user, schema_doc)
            run.exchange("completion", exchange.request, exchange.response,
                         exchange.usage, exchange.elapsed_ms, exchange.http_status)
            text = exchange.text
        else:
            # Mirrors the enforcer's `_complete`, including resumption from the written handle.
            handle_file = run.path("batch.json")
            custom_id = "adrift-1"
            if handle_file.exists():
                saved = json.loads(handle_file.read_text(encoding="utf-8"))
                handle = saved["handle"]
                # A combined batch writes this cell's own id here; absent, the default takes the only entry.
                custom_id = saved.get("customId", custom_id)
                print(f"provider: {args.provider} batch, resuming {handle} as {custom_id} ...")
            else:
                handle = engine.submit_batch(system, user, schema_doc)
                handle_file.write_text(json.dumps({"provider": args.provider,
                                                   "handle": handle}, indent=2),
                                       encoding="utf-8")
                print(f"provider: {args.provider} batch, submitted {handle} ...")
            text, usage = clients.await_batch(args.provider, handle, custom_id=custom_id,
                                              on_poll=lambda s: print(f"          {s} ..."))
            run.exchange("batch", {"handle": handle, "mode": "batch", "customId": custom_id},
                         {"text": text}, usage)
        run.write("completion.txt", text)

        answer = llm.parse_json(text)
        llm.validate(answer, response_schema)
        for change in llm.sanitise_ids(answer["mutations"]):
            print(f"          id sanitised: {change}")
        # Before the gates, because a selection has no `recipeList` until it is rendered.
        if args.catalogue and not args.probe:
            for note in _render_catalogue(answer):
                print(f"          {note}")
        for mutation in answer["mutations"]:
            # Before any gate reads it: both `ungrounded` and `as_yaml` speak the canonical shape.
            if "recipeList" in mutation:
                mutation["recipeList"] = recipes.normalise_recipe_list(mutation["recipeList"])
            mutation["gates"] = _gates(mutation, surface_doc, adr_file.stem)
            # Retained alongside the record, because `apply` may read an older mutations.json.
            mutation["problems"] = gates.blocking(mutation)

        run.write("mutations.json", json.dumps(answer, indent=2))
        usable = _usable(answer)
        run.finish("ok",
                   mutations=len(answer["mutations"]),
                   usable=len(usable),
                   wroteRecipes=sum(len(m.get("javaRecipes") or [])
                                    for m in answer["mutations"]),
                   gates=gates.tally(answer["mutations"]),
                   expressible={v: sum(1 for m in answer["mutations"]
                                       if m["expressible"] == v)
                                for v in (recipes.YES, recipes.NO_RECIPE,
                                          recipes.NOT_IN_REPOSITORY)},
                   clauses=schema.tally(answer["clauses"]))
    except BaseException as error:                      # noqa: BLE001 -- record, then re-raise
        # See the enforcer's note: an answer the provider produced and then refused is still kept.
        rejected = llm.rejected_completion(error)
        if rejected and not run.path("completion.txt").exists():
            run.write("completion.txt", rejected)
            print(f"          provider rejected a {len(rejected)}-char answer -- kept at "
                  f"{run.path('completion.txt')}")
        run.finish("failed", error=f"{type(error).__name__}: {error}",
                   rejectedCompletion=bool(rejected))
        raise

    print(f"\nwrote {out}\n")
    print(schema.coverage_report(answer["clauses"]))
    print()
    for mutation in answer["mutations"]:
        print(f"  {mutation['id']:<34} {mutation['expressible']}")
        print(f"      {(mutation.get('display') or mutation.get('form') or '')[:96]}")
        for written in mutation.get("javaRecipes") or []:
            print(f"      wrote recipe {written['className']}")
        for why in gates.observed(mutation, gates.DECLINED):
            print(f"      DECLINED -- {why}")
        for why in gates.observed(mutation, gates.RENDERABLE):
            print(f"      NOT RENDERABLE -- {why}")
        for why in gates.observed(mutation, gates.GROUNDED):
            print(f"      NOT GROUNDED -- {why}  (blocking: a recipe aimed at nothing "
                  f"would be scored as the check missing)")
    print(gates.report(answer["mutations"], "mutation"))
    if args.probe:
        print("\nNothing was executed. Apply each `howToApply` yourself, then run a check "
              "generated for the same decision against the result.")
    else:
        print(f"next: python -m mutator.mutate apply --run {run.run_id} --repo {repo} "
              f"--into .work/mutants")
    return 0


# ---------------------------------------------------------------------------------- apply


def _load(run_dir: Path) -> dict:
    path = run_dir / "mutations.json"
    if not path.exists():
        raise SystemExit(f"no mutations at {path} -- run `generate` first")
    answer = json.loads(path.read_text(encoding="utf-8"))
    if any("recipeList" not in m for m in answer["mutations"]):
        raise SystemExit(f"{path} is tool-free output -- its edits are model-authored commands "
                         "and this instrument does not execute them. Apply them by hand.")
    return answer


def _usable(answer: dict) -> list[dict]:
    """The mutations this pipeline will actually apply."""
    return [m for m in answer["mutations"]
            if m["expressible"] == recipes.YES and not gates.blocking(m)]


def _record(run_dir: Path) -> dict:
    """A run's own `run.json`, or an empty dict; never raises, since attribution is a nice-to-have."""
    path = run_dir / "run.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _apply_one(mutation: dict, run_dir: Path, repo: Path, into: Path):
    """Apply one mutation to a fresh copy of `repo` under `into`. Returns (Applied, tree)."""
    from mutator.openrewrite.apply import Applied
    recipe = recipes.from_answer(mutation, run_dir.name[:4])
    mvn = engines.tool_path("mvn") or "mvn"
    built, detail, built_output = install(recipe.java, mvn)
    tree = into / mutation["id"]
    if not built:
        return Applied([], detail, built_output), tree
    outcome = run_recipe(recipe, repo, tree, mvn)
    # Both halves, in order: the install log is what rules out a recipe that compiled to something inert.
    return (replace(outcome, output=f"{built_output}\n\n{outcome.output}".strip())
            if built_output else outcome), tree


def apply(args) -> int:
    """Apply every usable mutation to its own copy of the repository."""
    run_dir = runlog.find_run(args.run) or sys.exit(f"no run matching {args.run!r}")
    answer, repo = _load(run_dir), Path(args.repo).resolve()
    into = Path(args.into).resolve()

    usable = _usable(answer)
    if not usable:
        print("no usable mutations in this run")
        return 1

    run = runlog.Run(kind="apply", subject=run_dir.name, repo=repo.name, arm="mutator",
                     flags={"mutationsFrom": str(run_dir), "into": str(into)})
    applied = {}
    for mutation in usable:
        outcome, tree = _apply_one(mutation, run_dir, repo, into)
        applied[mutation["id"]] = {"changed": outcome.changed, "detail": outcome.detail}
        # Written beside the run record, not into the mutant, which is diffed against the original.
        if outcome.output:
            run.write(f"openrewrite_{mutation['id']}.txt", outcome.output)
        print(f"  {'OK ' if outcome.ok else '   '} {mutation['id']:<34} {outcome.detail}")
        if outcome.ok:
            print(f"      -> {tree}")
        else:
            print(f"      why: {run.directory / f'openrewrite_{mutation["id"]}.txt'}")
    run.finish("ok", applied=applied,
               succeeded=sum(1 for a in applied.values() if a["changed"]))
    return 0 if any(a["changed"] for a in applied.values()) else 1


# --------------------------------------------------------------------------------- verify

#: The outcomes of putting one mutation in front of one independently generated check, in test order.
NOT_APPLIED = "NOT-APPLIED"
INCONCLUSIVE = "INCONCLUSIVE"
ALREADY_VIOLATING = "ALREADY-VIOLATING"
DETECTED = "DETECTED"
MISSED = "MISSED"
#: The mutation applied, but no engine ever evaluated the check -- never scored as a miss.
NOT_EVALUATED = "NOT-EVALUATED"


def verdict_for(baseline: str, after: str, applied: bool) -> str:
    """The verification verdict for one (mutation, check) outcome. The order of tests matters."""
    if not applied:
        return NOT_APPLIED
    # ERROR first: a check that could not be evaluated has said nothing about either tree.
    if baseline == ERROR or after == ERROR:
        return INCONCLUSIVE
    # Then the original: if it was already violating, the mutant tells us nothing.
    if baseline == VIOLATION:
        return ALREADY_VIOLATING
    # Then "nothing ran", BEFORE any verdict about behaviour -- see NOT_EVALUATED above.
    if after == SKIP:
        return NOT_EVALUATED
    if after == VIOLATION:
        return DETECTED
    return MISSED


def _prepare(tree: Path, rules: dict, scratch: Path) -> list[Path] | None:
    """Compiled classes for `tree` when the check run has ArchUnit rules; None when it has none."""
    if not (rules.get("archunit") or []):
        return None
    from mutator.openrewrite.apply import rebuild
    from enforcer.archunit.runner import compile_tree
    classes, detail = rebuild(tree, engines.tool_path("mvn") or "mvn")
    if classes:
        print(f"          {tree.name}: {detail}")
        return classes
    compiled = compile_tree(tree, scratch)
    if compiled:
        return [compiled]
    print(f"          {tree.name}: {detail}; classpath-free compile also failed")
    return []


def verify(args) -> int:
    """Put every applied mutation in front of an independently generated check, in careful order."""
    run_dir = runlog.find_run(args.run) or sys.exit(f"no run matching {args.run!r}")
    check_dir = runlog.find_run(args.check_run) or sys.exit(f"no run matching {args.check_run!r}")
    answer, repo = _load(run_dir), Path(args.repo).resolve()
    into = Path(args.into).resolve()

    rules_file = check_dir / "rules.json"
    if not rules_file.exists():
        raise SystemExit(f"no rules at {rules_file} -- the check run must be a `generate` run")
    rules = json.loads(rules_file.read_text(encoding="utf-8"))

    scratch = into / ".classes"
    baseline = engines.run_all(rules, check_dir, repo, _prepare(repo, rules, scratch / "original"))
    baseline_status = worst(baseline.values())

    # Both sides of the pairing are named, so the row carrying the measurement groups by model.
    source = _record(run_dir)
    check = _record(check_dir)
    run = runlog.Run(kind="apply", subject=run_dir.name, repo=repo.name, arm="verification",
                     provider=source.get("provider") or "-", model=source.get("model") or "-",
                     flags={"mutationsFrom": str(run_dir), "checksFrom": str(check_dir),
                            "baseline": baseline_status,
                            "mutationsRunId": source.get("runId"),
                            "checkModel": check.get("model") or "-",
                            "checkProvider": check.get("provider") or "-",
                            "checkRulesRunId": check.get("runId"),
                            "checkArm": check.get("arm"),
                            "checkRepetition": check_dir.parent.name,
                            # Not independent derivation; labelled so the analysis can split on it.
                            "sameModel": bool(source.get("model")) and
                                         source.get("model") == check.get("model")})
    verdicts = {}
    for mutation in _usable(answer):
        outcome, tree = _apply_one(mutation, run_dir, repo, into)
        if not outcome.ok:
            verdict, after = NOT_APPLIED, "-"
        else:
            results = engines.run_all(rules, check_dir, tree,
                                      _prepare(tree, rules, scratch / mutation["id"]))
            after = worst(results.values())
            verdict = verdict_for(baseline_status, after, applied=True)
        verdicts[mutation["id"]] = {"verdict": verdict, "after": after,
                                    "detail": outcome.detail}
        print(f"  {mutation['id']:<34} baseline={baseline_status:<10} after={after:<10} "
              f"{verdict}")

    detected = sum(1 for v in verdicts.values() if v["verdict"] == DETECTED)
    run.finish("ok", baseline=baseline_status, verdicts=verdicts, detected=detected)
    print(f"\n{detected} of {len(verdicts)} mutation(s) DETECTED by the independently "
          f"generated check")
    return 0


# ------------------------------------------------------------------------------------ CLI


def batch_submit(args) -> int:
    """Queue every (repetition, ADR) cell as ONE batch, leaving each cell able to collect its own."""
    from fingerprint import census, read, surface as build_surface
    from fingerprint.constants import TEST_PATTERNS

    llm.load_dotenv(REPO_ROOT / ".env")
    adr_dir, repo = Path(args.adr_dir).resolve(), Path(args.repo).resolve()
    out_root = Path(args.out_root).resolve()
    adrs = sorted(adr_dir.glob("[0-9]*.md"))
    if not adrs:
        raise SystemExit(f"no ADRs matching [0-9]*.md under {adr_dir}")

    # ONE reading of the repository for every cell: the inputs are identical across them.
    out_root.mkdir(parents=True, exist_ok=True)
    walked = read(repo, exclude=TEST_PATTERNS if args.exclude_tests else ())
    fingerprint_json = json.dumps(census(walked), indent=1, separators=(",", ":")) + "\n"
    surface_doc = build_surface(walked, tuple(args.packages), args.methods)
    surface_json = json.dumps(surface_doc, indent=1, separators=(",", ":")) + "\n"
    print(f"surface:  {surface_doc['typeCount']} type(s), build system "
          f"{surface_doc['buildSystem']}")

    items, targets, skipped = [], [], 0
    for rep in range(1, args.reps + 1):
        for adr_file in adrs:
            cell = out_root / f"r{rep}" / adr_file.name[:4]
            if (cell / "mutations.json").exists() or (cell / "batch.json").exists():
                skipped += 1
                continue
            system, user, schema = prompt.build(
                adr_file.read_text(encoding="utf-8"), fingerprint_json, surface_json,
                args.probe, args.catalogue)
            items.append((f"r{rep}-{adr_file.name[:4]}", system, user))
            targets.append(cell)
    if not items:
        print(f"nothing to submit -- {skipped} cell(s) already done or queued")
        return 0

    engine = clients.for_provider(args.provider)
    if not getattr(engine, "supports_batch", False):
        raise SystemExit(f"{args.provider} has no batch endpoint -- use --mode sync")
    _, _, schema = prompt.build(adrs[0].read_text(encoding="utf-8"), fingerprint_json,
                                surface_json, args.probe, args.catalogue)
    handle = engine.submit_batch_many(items, None if args.no_schema else schema)
    print(f"submitted: {len(items)} request(s) as one batch {handle}"
          f"{f'  ({skipped} skipped)' if skipped else ''}")

    for (custom_id, _, _), cell in zip(items, targets):
        cell.mkdir(parents=True, exist_ok=True)
        (cell / "batch.json").write_text(json.dumps(
            {"provider": args.provider, "handle": handle, "customId": custom_id}, indent=2),
            encoding="utf-8")
    print(f"wrote:     batch.json into {len(targets)} cell(s) under {out_root}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    gen = commands.add_parser("generate", help="ADR + fingerprint + surface -> a breaking edit")
    gen.add_argument("--adr", required=True)
    gen.add_argument("--repo", required=True, help="the project to mutate")
    gen.add_argument("--provider", required=True, choices=llm.PROVIDERS)
    gen.add_argument("--probe", action="store_true",
                     help="the tool-free arm: name no tool and let the model choose the "
                          "technique. Its artefacts are saved but never executed.")
    gen.add_argument("--no-thinking", action="store_true",
                     help="send no reasoning/thinking parameters at all. Required by models that reject them outright rather than merely not needing them -- Anthropic's Haiku 4.5 and Groq's qwen3.6-27b both answer 400 otherwise. Equivalent to ADRIFT_<PROVIDER>_EFFORT=none.")
    # OPT-IN, matching the enforcer: free authoring is the baseline the catalogue is compared against.
    gen.add_argument("--catalogue", action="store_true",
                     help="offer the recipe catalogue -- the 24 stock recipes of "
                          "openrewrite/catalogue.py, selectable by id -- instead of writing "
                          "every recipe out. Writing its own stays available either way. Adds "
                          "catalogueRecipe/paramsJson to the schema, as the enforcer's twin "
                          "adds catalogueRule/paramsJson. Ignored with --probe.")
    gen.add_argument("--packages", action="append", default=[], metavar="PKG",
                     help="restrict the mutation surface to this package and those under it")
    gen.add_argument("--methods", action="store_true",
                     help="include method lists in the surface (~20%% larger)")
    gen.add_argument("--exclude-tests", action="store_true",
                     help="leave test sources out of the surface. On a real service they are "
                          "roughly a third of it, and a decision that governs production code "
                          "cannot be violated by editing a test. Leave them IN when the "
                          "decision is itself about test code.")
    gen.add_argument("--out")
    gen.add_argument("--mode", choices=("sync", "batch"), default="sync",
                     help="batch is roughly half price and takes minutes to hours; re-run to "
                          "resume polling (" + " and ".join(llm.BATCH_PROVIDERS) + " only)")
    gen.add_argument("--no-schema", action="store_true")
    gen.set_defaults(handler=generate)

    app = commands.add_parser("apply", help="run each recipe on a copy of the repository")
    app.add_argument("--run", required=True)
    app.add_argument("--repo", required=True)
    app.add_argument("--into", default=".work/mutants", help="where the copies go")
    app.set_defaults(handler=apply)

    ver = commands.add_parser("verify",
                              help="run an independently generated check against each mutant")
    ver.add_argument("--run", required=True, help="a mutation run")
    ver.add_argument("--check-run", required=True,
                     help="an enforcer `generate` run for the SAME ADR and repository")
    ver.add_argument("--repo", required=True)
    ver.add_argument("--into", default=".work/mutants")
    ver.set_defaults(handler=verify)

    sub = commands.add_parser(
        "batch-submit",
        help="queue every repetition x ADR cell as ONE batch; collect with generate --mode batch")
    sub.add_argument("--provider", required=True, choices=llm.PROVIDERS)
    sub.add_argument("--adr-dir", default="cleanroom/adr", help="directory of ADRs")
    sub.add_argument("--repo", required=True, help="the project to fingerprint and survey")
    sub.add_argument("--out-root", required=True,
                     help="cells are written as <out-root>/r<N>/<NNNN>/")
    sub.add_argument("--reps", type=int, default=1)
    sub.add_argument("--probe", action="store_true")
    sub.add_argument("--catalogue", action="store_true")
    sub.add_argument("--no-schema", action="store_true")
    sub.add_argument("--packages", nargs="*", default=[])
    sub.add_argument("--methods", action="store_true")
    sub.add_argument("--exclude-tests", action="store_true")
    sub.set_defaults(handler=batch_submit)

    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except llm.LlmError as error:
        raise SystemExit(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
