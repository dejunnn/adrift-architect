"""Compile a decision record into executable conformance checks, then run them."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import clients
from core import gates, llm, prompts, runlog, schema
from core.result import ERROR, EXIT_CODE, PASS, SKIP, VIOLATION, worst
from enforcer import engines, grounding, prompt
from enforcer.archunit import catalogue

REPO_ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------------------- generate


def _fingerprint(repo: Path, destination: Path) -> str:
    """Write the repository's fingerprint and return it."""
    from fingerprint import census, read
    document = census(read(repo))
    text = json.dumps(document, indent=1, separators=(",", ":")) + "\n"
    destination.write_text(text, encoding="utf-8")
    return text


def _complete(args, run: runlog.Run, system: str, user: str, schema_doc: dict | None) -> str:
    """One completion, sync or batched, logged either way; a batch handle is saved before polling."""
    engine = clients.for_provider(args.provider)
    if args.mode == "sync":
        print(f"provider:    {args.provider} sync ...")
        exchange = engine.complete(system, user, schema_doc)
        run.exchange("completion", exchange.request, exchange.response,
                     exchange.usage, exchange.elapsed_ms, exchange.http_status)
        print(f"             {exchange.usage.get('inputTokens')} in / "
              f"{exchange.usage.get('outputTokens')} out tokens, {exchange.elapsed_ms} ms")
        return exchange.text

    handle_file = run.path("batch.json")
    custom_id = "adrift-1"
    if handle_file.exists():
        saved = json.loads(handle_file.read_text(encoding="utf-8"))
        handle = saved["handle"]
        # A combined batch writes the cell's own id here; absent, the default selects the only entry.
        custom_id = saved.get("customId", custom_id)
        print(f"provider:    {args.provider} batch, resuming {handle} as {custom_id} ...")
    else:
        handle = engine.submit_batch(system, user, schema_doc)
        handle_file.write_text(json.dumps({"provider": args.provider, "handle": handle},
                                          indent=2), encoding="utf-8")
        print(f"provider:    {args.provider} batch, submitted {handle} ...")
    text, usage = clients.await_batch(args.provider, handle, custom_id=custom_id,
                               on_poll=lambda status: print(f"             {status} ..."))
    run.exchange("batch", {"handle": handle, "mode": "batch", "customId": custom_id},
                 {"text": text}, usage)
    return text


def _render_catalogue(answer: dict) -> list[str]:
    """Turn every catalogue selection into the expression it stands for, in place."""
    notes = []
    kept, rejected = [], []
    for rule in answer.get("archunit") or []:
        selected = (rule.get("catalogueRule") or "").strip()
        if not selected:
            rule.pop("catalogueRule", None), rule.pop("paramsJson", None)
            kept.append(rule)
            continue
        try:
            params = json.loads(rule.get("paramsJson") or "{}")
            if not isinstance(params, dict):
                raise ValueError("paramsJson is not a JSON object")
        except (json.JSONDecodeError, ValueError) as error:
            rule["problems"] = [f"paramsJson did not parse: {error}"]
            notes.append(f"{rule['id']}: REJECTED {rule['problems'][0]}")
            rejected.append(rule)
            continue
        problems = catalogue.problems(selected, params)
        if problems:
            rule["problems"] = problems
            notes.append(f"{rule['id']}: REJECTED {'; '.join(problems)}")
            rejected.append(rule)
            continue
        rule["rule"] = [catalogue.render(selected, params)]
        rule["params"] = params
        rule.pop("paramsJson", None)
        notes.append(f"{rule['id']}: rendered from catalogue shape {selected!r}")
        kept.append(rule)
    answer["archunit"] = kept
    if rejected:
        answer["archunitRejected"] = rejected
    return notes


def _gate_rules(answer: dict, fingerprint_json: str, probe: bool) -> list[dict]:
    """Attach the standard gate record (`core/gates.py`) to every generated artefact, blocking none."""
    fingerprint = grounding.load(fingerprint_json)
    items = []
    if probe:
        for check in answer.get("checks") or []:
            check["gates"] = gates.record([], [], grounded_blocks=False)
            items.append(check)
        return items
    for tool in engines.TOOLS:
        for rule in answer.get(tool) or []:
            rule["gates"] = gates.record(
                renderable=[],                          # it is here, so it rendered
                grounded=grounding.ungrounded(tool, rule.get(engines.BODY_FIELD[tool]),
                                              fingerprint),
                grounded_blocks=False)
            items.append(rule)
    for rule in answer.get("archunitRejected") or []:
        rule["gates"] = gates.record(renderable=rule.get("problems") or [], grounded=[],
                                     grounded_blocks=False)
        items.append(rule)
    return items


def _write_rules(answer: dict, out: Path) -> dict[str, int]:
    """One file per rule, flat and engine-prefixed, each a real artefact of its engine. Returns counts."""
    from enforcer.archunit.runner import render_file
    for tool in engines.TOOLS:
        for entry in answer.get(tool) or []:
            if tool == "archunit":
                body = render_file(entry).rstrip()
            else:
                # The body arrives as an array of lines -- see core.schema.rules().
                body = "\n".join(entry[engines.BODY_FIELD[tool]]).rstrip()
            (out / f"{tool}_{entry['id']}{engines.SUFFIX[tool]}").write_text(
                body + "\n", encoding="utf-8")
    return {tool: len(answer.get(tool) or []) for tool in engines.TOOLS}


def _write_probes(answer: dict, out: Path) -> int:
    """One file per tool-free check, with its provenance as a header."""
    for check in answer["checks"]:
        (out / f"probe_{check['id']}.txt").write_text(
            f"# form:      {check['form']}\n"
            f"# targets:   {check['targets']}\n"
            f"# source:    {check['source']}\n"
            f"# run:       {check['howToRun']}\n"
            f"# violation: {check['whatCountsAsAViolation']}\n\n"
            + "\n".join(check["artifact"]).rstrip() + "\n", encoding="utf-8")
    return len(answer["checks"])


def generate(args) -> int:
    """Compile one ADR into checks and write a self-contained run directory."""
    adr_file, repo = Path(args.adr).resolve(), Path(args.repo).resolve()
    if getattr(args, "no_thinking", False):
        # Set before any client is built, because the clients read this through `llm.effort`.
        os.environ[f"ADRIFT_{args.provider.upper()}_EFFORT"] = "none"
    llm.load_dotenv(REPO_ROOT / ".env")

    run = runlog.Run(
        kind="probe" if args.probe else "generate",
        subject=adr_file.stem,
        repo=repo.name,
        provider=args.provider,
        model=llm.setting(args.provider, "MODEL") or "unset",
        # The catalogue is its own arm, not a flag: it changes what the model is asked to produce.
        arm=("probe" if args.probe else "catalogue" if args.catalogue else "free"),
        flags={"mode": args.mode, "schema": not args.no_schema,
               "repoPath": str(repo), "adrPath": str(adr_file),
               "catalogue": bool(args.catalogue) and not args.probe,
               # The output budget, recorded for the same reason as promptSha: it bounds the answer.
               "maxTokens": llm.max_tokens(),
               # Ollama ignores maxTokens and bounds prompt plus completion with this instead.
               "numCtx": llm.num_ctx(),
               # Recorded because it changes what the model was asked to do, not merely how.
               "effort": llm.effort(args.provider),
               "reusedFingerprint": bool(args.fingerprint)},
    )
    if args.out:
        run.use_directory(Path(args.out).resolve())
    out = run.directory
    print(f"run:         {run.run_id}  ->  {out}")

    try:
        shutil.copy(adr_file, out / "adr.md")
        fingerprint_file = out / f"{repo.name}_fingerprint.json"
        if args.fingerprint:
            shutil.copy(Path(args.fingerprint), fingerprint_file)
            print(f"fingerprint: reused {args.fingerprint}")
        else:
            print(f"fingerprint: reading {repo} ...")
            _fingerprint(repo, fingerprint_file)
        fingerprint_json = fingerprint_file.read_text(encoding="utf-8")

        system, user, response_schema = prompt.build(
            adr_file.read_text(encoding="utf-8"), fingerprint_json, args.probe, args.catalogue)
        # Both inputs are digested into the record: prompt wording is the largest confound here.
        run.flags["promptSha"] = prompts.digest(system)
        run.flags["fingerprintSha"] = prompts.digest(fingerprint_json)
        prompts.check_size("fingerprint", fingerprint_json,
                           "the census does not scope; split the module or use a smaller repo")
        # The schema is prompt too -- its `description` fields are instructions the model reads.
        run.flags["schemaSha"] = ("none" if args.no_schema
                                  else prompts.digest(json.dumps(response_schema,
                                                                 sort_keys=True)))
        run.write("prompt.txt", f"=== SYSTEM ===\n{system}\n\n=== USER ===\n{user}")

        completion = _complete(args, run, system, user,
                               None if args.no_schema else response_schema)
        run.write("completion.txt", completion)

        # Valid JSON, in the shape asked for. Whether a check is any good is the experiment.
        answer = llm.parse_json(completion)
        llm.validate(answer, response_schema)

        # Ids become filenames, so they are sanitised before anything is written, and reported.
        entries = (answer["checks"] if args.probe
                   else [e for tool in engines.TOOLS for e in (answer.get(tool) or [])])
        for change in llm.sanitise_ids(entries):
            print(f"             id sanitised: {change}")

        if args.catalogue and not args.probe:
            for note in _render_catalogue(answer):
                print(f"             {note}")

        gated = _gate_rules(answer, fingerprint_json, args.probe)

        if args.probe:
            run.write("checks.json", json.dumps(answer, indent=2))
            count = _write_probes(answer, out)
            run.finish("ok", checks=count, clauses=schema.tally(answer["clauses"]),
                       gates=gates.tally(gated),
                       forms=[c["form"][:80] for c in answer["checks"]])
        else:
            run.write("rules.json", json.dumps(answer, indent=2))
            counts = _write_rules(answer, out)
            run.finish("ok", rules=counts, clauses=schema.tally(answer["clauses"]),
                       gates=gates.tally(gated))
    except BaseException as error:                      # noqa: BLE001 -- record, then re-raise
        # An answer the PROVIDER refused is still an answer, kept under the name a success uses.
        rejected = llm.rejected_completion(error)
        if rejected and not run.path("completion.txt").exists():
            run.write("completion.txt", rejected)
            print(f"             provider rejected a {len(rejected)}-char answer -- kept at "
                  f"{run.path('completion.txt')}")
        run.finish("failed", error=f"{type(error).__name__}: {error}",
                   rejectedCompletion=bool(rejected))
        raise

    print(f"\nwrote {out}\n")
    print(schema.coverage_report(answer["clauses"]))
    print(gates.report(gated, "check" if args.probe else "rule"))
    for item in gated:
        for why in gates.observed(item, gates.GROUNDED):
            print(f"      {item['id']}: NOT GROUNDED -- {why}  (recorded, still run)")
    if args.probe:
        for check in answer["checks"]:
            print(f"\n  {check['id']}\n    form:    {check['form'][:100]}"
                  f"\n    targets: {check['targets'][:100]}"
                  f"\n    run:     {check['howToRun'][:160]}")
        print("\nNothing was executed. Run each `howToRun` yourself, against the violating "
              "fixture and then the compliant one.")
    else:
        for tool in engines.TOOLS:
            listed = ", ".join(e["id"] for e in answer[tool]) or "-"
            print(f"  {tool:9} {counts[tool]} rule(s): {listed}")
        for rule in answer.get("archunitRejected") or []:
            for why in gates.blocking(rule):
                print(f"      {rule['id']}: NOT RENDERABLE -- {why}")
        print(f"\nnext: python -m enforcer.enforce execute --run {run.run_id} --repo {repo}")
    return 0


# -------------------------------------------------------------------------------- execute


def _locate(reference: str) -> Path:
    """The run directory a reference names, or exit saying so."""
    found = runlog.find_run(reference)
    if found is None:
        raise SystemExit(f"no run matching {reference!r} under {runlog.LOGS_ROOT}")
    return found


def _execute(run_dir: Path, repo: Path, classes: list[Path] | None,
             only: list[str] | None) -> tuple[dict, Path]:
    """Run a directory's rules against one repository and record it; returns results and report path."""
    rules_file = run_dir / "rules.json"
    if not rules_file.exists():
        raise SystemExit(f"no rules at {rules_file} -- run `generate` first, and note that "
                         "`--probe` output is not executable")
    rules = json.loads(rules_file.read_text(encoding="utf-8"))

    # Inherit what the generation recorded, so an execution joins back to the run that made the rules.
    prior = {}
    if (run_dir / "run.json").exists():
        prior = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    run = runlog.Run(
        kind="execute",
        subject=prior.get("subject", run_dir.name),
        repo=repo.name,
        provider=prior.get("provider", "-"),
        model=prior.get("model", "-"),
        arm="execution",
        flags={"generateRunId": prior.get("runId"), "rulesFrom": str(run_dir),
               "repoPath": str(repo), "only": only or list(engines.TOOLS),
               "classes": [str(c) for c in (classes or [])]},
    )

    results = engines.run_all(rules, run_dir, repo, classes, only)

    report = [f"repository: {repo}", f"rules:      {run_dir}", ""]
    for tool, result in results.items():
        report += [f"== {tool}: {result.status}", result.detail, ""]
    if rules.get("clauses"):
        # Carried into the report so a clean run cannot be read as "the ADR is satisfied".
        report += ["== coverage", schema.coverage_report(rules["clauses"]), ""]
    body = "\n".join(report)
    report_file = run_dir / f"report_{runlog._slug(repo.name)}.txt"
    report_file.write_text(body, encoding="utf-8")

    run.finish("ok",
               verdict=worst(results.values()),
               engines={tool: {"status": r.status, "findings": r.findings}
                        for tool, r in results.items()})
    return results, report_file


def execute(args) -> int:
    """Execute a previous run's rules against a repository. Exit 0 clean, 1 VIOLATION, 2 ERROR."""
    run_dir, repo = _locate(args.run), Path(args.repo).resolve()
    classes = [Path(p).resolve() for p in args.classes] if args.classes else None
    results, report_file = _execute(run_dir, repo, classes, args.only)

    for tool, result in results.items():
        print(f"== {tool}: {result.status}")
        print(result.detail)
        print()
    print(f"wrote {report_file}")
    return EXIT_CODE[worst(results.values())]


# --------------------------------------------------------------------------- discriminate

#: The outcomes of running one set of rules against a labelled fixture pair, in the order tested.
DISCRIMINATES = "DISCRIMINATES"
MISSED = "MISSED the violation"
OVER_BROAD = "FIRED on the compliant fixture"
DID_NOT_RUN = "RULE DID NOT RUN"
#: Neither side ran: no rule was generated for the engine being scored. Never scored as a miss.
NO_RULE = "NO RULE FOR THIS ENGINE"


def _pair_verdict(good: str | None, bad: str | None) -> str:
    """The verdict for one compliant/violating pair of statuses. The order of tests matters."""
    if ERROR in (good, bad):
        return DID_NOT_RUN
    # Before any verdict about behaviour: a rule that does not exist supports no finding at all.
    if SKIP in (good, bad) or None in (good, bad):
        return NO_RULE
    if bad == VIOLATION and good == PASS:
        return DISCRIMINATES
    if bad == PASS:
        return MISSED
    return OVER_BROAD


def discriminate(args) -> int:
    """Run the rules against both sides of a fixture pair and derive the verdict, ERROR tested first."""
    run_dir = _locate(args.run)
    compliant, violating = Path(args.compliant).resolve(), Path(args.violating).resolve()

    def side(repo: Path, classes: list[str] | None):
        resolved = [Path(c).resolve() for c in classes] if classes else None
        results, _ = _execute(run_dir, repo, resolved, args.only)
        return {tool: result.status for tool, result in results.items()}

    good_by_tool = side(compliant, args.classes_compliant)
    bad_by_tool = side(violating, args.classes_violating)
    good, bad = worst(good_by_tool.values()), worst(bad_by_tool.values())

    # The aggregate verdict hides a real result, so the per-engine breakdown is recorded too.
    per_engine = {tool: _pair_verdict(good_by_tool.get(tool), bad_by_tool.get(tool))
                  for tool in sorted(set(good_by_tool) | set(bad_by_tool))}

    verdict = _pair_verdict(good, bad)

    # The verdict record carries the model that produced the rules, read out of the generating run.
    source: dict = {}
    record = run_dir / "run.json"
    if record.exists():
        try:
            source = json.loads(record.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            source = {}

    run = runlog.Run(kind="execute",
                     subject=source.get("subject") or run_dir.name,
                     repo=f"{compliant.name}|{violating.name}",
                     provider=source.get("provider") or "-",
                     model=source.get("model") or "-",
                     arm="discrimination",
                     flags={"rulesFrom": str(run_dir), "compliant": str(compliant),
                            "violating": str(violating),
                            # The exact generation this verdict judges, joined on an id.
                            "rulesRunId": source.get("runId"),
                            "generationArm": source.get("arm"),
                            "repetition": run_dir.parent.name})
    run.finish("ok", verdict=verdict, compliantSide=good, violatingSide=bad,
               perEngine=per_engine)

    print(f"compliant={good}  violating={bad}  ->  {verdict}")
    for tool, engine_verdict in per_engine.items():
        if engine_verdict != NO_RULE:
            print(f"    {tool:<9} {engine_verdict}")
    return 0 if verdict == DISCRIMINATES else 1


# ------------------------------------------------------------------------------------ CLI


def batch_submit(args) -> int:
    """Queue every (repetition, ADR) cell as ONE batch, leaving each cell able to collect its own."""
    llm.load_dotenv(REPO_ROOT / ".env")
    adr_dir, repo = Path(args.adr_dir).resolve(), Path(args.repo).resolve()
    out_root = Path(args.out_root).resolve()
    adrs = sorted(adr_dir.glob("[0-9]*.md"))
    if not adrs:
        raise SystemExit(f"no ADRs matching [0-9]*.md under {adr_dir}")

    # ONE fingerprint for every cell: the repository is the same, and re-reading it could differ.
    out_root.mkdir(parents=True, exist_ok=True)
    fingerprint_file = out_root / f"{repo.name}_fingerprint.json"
    fingerprint_json = _fingerprint(repo, fingerprint_file)
    print(f"fingerprint: {repo} -> {fingerprint_file}")

    items, targets, skipped = [], [], 0
    for rep in range(1, args.reps + 1):
        for adr_file in adrs:
            cell = out_root / f"r{rep}" / adr_file.name[:4]
            # A cell already holding rules, or already attached to a batch, is left alone.
            if (cell / "rules.json").exists() or (cell / "batch.json").exists():
                skipped += 1
                continue
            system, user, schema = prompt.build(
                adr_file.read_text(encoding="utf-8"), fingerprint_json,
                args.probe, args.catalogue)
            # The id must survive the round trip through the provider and still name exactly one cell.
            items.append((f"r{rep}-{adr_file.name[:4]}", system, user))
            targets.append(cell)
    if not items:
        print(f"nothing to submit -- {skipped} cell(s) already done or queued")
        return 0

    engine = clients.for_provider(args.provider)
    if not getattr(engine, "supports_batch", False):
        raise SystemExit(f"{args.provider} has no batch endpoint -- use --mode sync")
    _, _, schema = prompt.build(adrs[0].read_text(encoding="utf-8"), fingerprint_json,
                                args.probe, args.catalogue)
    handle = engine.submit_batch_many(items, None if args.no_schema else schema)
    print(f"submitted:   {len(items)} request(s) as one batch {handle}"
          f"{f'  ({skipped} skipped)' if skipped else ''}")

    for (custom_id, _, _), cell in zip(items, targets):
        cell.mkdir(parents=True, exist_ok=True)
        (cell / "batch.json").write_text(json.dumps(
            {"provider": args.provider, "handle": handle, "customId": custom_id}, indent=2),
            encoding="utf-8")
    print(f"wrote:       batch.json into {len(targets)} cell(s) under {out_root}")
    print(f"\nnext: collect with `generate --mode batch --out <cell>` per cell; each resumes "
          f"this handle and takes only its own customId.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    gen = commands.add_parser("generate", help="ADR + fingerprint -> checks")
    gen.add_argument("--adr", required=True, help="the decision record")
    gen.add_argument("--repo", required=True, help="the project it applies to")
    gen.add_argument("--provider", required=True, choices=llm.PROVIDERS)
    gen.add_argument("--probe", action="store_true",
                     help="the tool-free arm: name no analysis tool and let the model choose "
                          "the technique. Its artefacts are saved but never executed.")
    gen.add_argument("--no-thinking", action="store_true",
                     help="send no reasoning/thinking parameters at all. Required by models that reject them outright rather than merely not needing them -- Anthropic's Haiku 4.5 and Groq's qwen3.6-27b both answer 400 otherwise. Equivalent to ADRIFT_<PROVIDER>_EFFORT=none.")
    gen.add_argument("--catalogue", action="store_true",
                     help="offer the seventeen validated ArchUnit rule shapes, which the model "
                          "may select and parameterise instead of writing an expression. A "
                          "free expression stays available for decisions no shape can state. "
                          "Ignored with --probe.")
    gen.add_argument("--out", help="output directory (default: a named directory under "
                                   "logs/generate or logs/probe)")
    gen.add_argument("--fingerprint", help="reuse this fingerprint.json")
    gen.add_argument("--mode", choices=("sync", "batch"), default="sync",
                     help="batch is roughly half price and takes minutes to hours; re-run to "
                          "resume polling (" + " and ".join(llm.BATCH_PROVIDERS) + " only)")
    gen.add_argument("--no-schema", action="store_true",
                     help="do not constrain the response with a JSON schema")
    gen.set_defaults(handler=generate)

    ex = commands.add_parser("execute", help="run generated rules against a repository")
    ex.add_argument("--run", required=True,
                    help="a run id, a run directory name, or a path")
    ex.add_argument("--repo", required=True, help="the project to check")
    ex.add_argument("--classes", nargs="*",
                    help="compiled class directories for ArchUnit (default: auto-detect)")
    ex.add_argument("--only", nargs="*", choices=engines.TOOLS, help="run only these engines")
    ex.set_defaults(handler=execute)

    dis = commands.add_parser("discriminate",
                              help="run both sides of a fixture pair and derive the verdict")
    dis.add_argument("--run", required=True)
    dis.add_argument("--compliant", required=True, help="the fixture that satisfies the ADR")
    dis.add_argument("--violating", required=True, help="the fixture that breaches it")
    dis.add_argument("--classes-compliant", nargs="*")
    dis.add_argument("--classes-violating", nargs="*")
    dis.add_argument("--only", nargs="*", choices=engines.TOOLS)
    dis.set_defaults(handler=discriminate)

    sub = commands.add_parser(
        "batch-submit",
        help="queue every repetition x ADR cell as ONE batch; collect with generate --mode batch")
    sub.add_argument("--provider", required=True, choices=llm.PROVIDERS)
    sub.add_argument("--adr-dir", default="cleanroom/adr", help="directory of ADRs")
    sub.add_argument("--repo", required=True, help="the project to fingerprint")
    sub.add_argument("--out-root", required=True,
                     help="cells are written as <out-root>/r<N>/<NNNN>/")
    sub.add_argument("--reps", type=int, default=3, help="repetitions per ADR")
    sub.add_argument("--probe", action="store_true")
    sub.add_argument("--catalogue", action="store_true")
    sub.add_argument("--no-schema", action="store_true")
    sub.set_defaults(handler=batch_submit)

    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except llm.LlmError as error:
        raise SystemExit(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
