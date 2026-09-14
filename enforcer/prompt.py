"""The enforcer's two system prompts -- tools-named and tool-free -- and the response schema for each."""

from __future__ import annotations

import textwrap

from core import prompts, schema
from enforcer.archunit import catalogue as archunit_catalogue
from enforcer.archunit.runner import IMPORTS

#: The ArchUnit import list the model is shown, taken from the SAME constant the runner compiles against.
_ARCHUNIT_IMPORTS = textwrap.indent(
    "\n".join(line for line in IMPORTS.splitlines() if line.strip()), "    ")

#: Filled into `coverage.txt` in both arms. Deliberately ABSTRACT, so the tool-free arm is not primed.
_OPTIONS = ("Two entries mean you weighed two ways of checking the clause and kept one; the\n"
            "rejected one still belongs in the list, and `reason` says why it was rejected.")

def _tools_system(catalogue: bool) -> str:
    """The tools-arm system message, with or without the ArchUnit rule catalogue block."""
    return (
        prompts.block("shared_preamble", artefact="check", what=(
            "Return rules for whichever of the three engines below can actually enforce the "
            "decision.\nIf an engine cannot express the decision, return an empty list for "
            "it. Two engines\nenforcing the same clause is fine when both genuinely can."))
        # Only the ArchUnit block takes slots; the others go through `text`, which leaves `$` alone.
        + prompts.block("enforce_generate_engines",
                        archunit=prompts.block(
                            "enforce_generate_engine_archunit",
                            archunit_imports=_ARCHUNIT_IMPORTS,
                            catalogue=prompts.block("enforce_generate_catalogue",
                                                    catalogue=archunit_catalogue.describe())
                            if catalogue else ""),
                        semgrep=prompts.text("enforce_generate_engine_semgrep"),
                        conftest=prompts.text("enforce_generate_engine_conftest"))
        + prompts.block("shared_coverage", artefact="check", field="consideredTools",
                        options=_OPTIONS)
        + prompts.block("enforce_generate_output",
                        serialisation=prompts.block("shared_serialisation",
                                                    body="rule body"))
    )


SYSTEM_TOOLS = _tools_system(False)
SYSTEM_TOOLS_CATALOGUE = _tools_system(True)

SYSTEM_PROBE = (
    prompts.block("shared_preamble", artefact="check", what=(
        "Produce one or more AUTOMATED CHECKS that would fail if the decision were breached, "
        "and\npass otherwise. Use any technique you consider appropriate."))
    + prompts.block("enforce_probe_technique")
    + prompts.block("shared_coverage", artefact="check", field="consideredApproaches",
                    options=_OPTIONS)
    + prompts.block("enforce_probe_output")
)

RESPONSE_TOOLS = {
    "type": "object",
    "additionalProperties": False,
    "required": ["clauses", "archunit", "semgrep", "conftest"],
    "properties": {
        "clauses": schema.clauses(
            "consideredTools",
            {"type": "string", "enum": ["archunit", "semgrep", "conftest"]},
            "every engine you CONSIDERED for this clause, including any you then rejected. "
            "Empty only if no engine could apply at all."),
        "archunit": schema.rules("rule"),
        "semgrep": schema.rules("yaml"),
        "conftest": schema.rules("rego", {
            "files": {"type": "array", "items": {"type": "string"},
                      "description": "globs relative to the repository root"},
        }),
    },
}

#: The catalogue arm's schema: the tools schema with two extra fields on every ArchUnit rule.
RESPONSE_TOOLS_CATALOGUE = {
    **RESPONSE_TOOLS,
    "properties": {
        **RESPONSE_TOOLS["properties"],
        "archunit": schema.rules("rule", {
            "catalogueRule": {
                "type": "string",
                "description": "a catalogue rule id, or \"\" to write a free expression in "
                               "`rule` instead"},
            "paramsJson": {
                "type": "string",
                "description": "that rule's parameters as a JSON object, e.g. "
                               "{\"deny.from\": [\"..domain..\"]}. \"{}\" when writing a free "
                               "expression"},
        }),
    },
}

RESPONSE_PROBE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["clauses", "checks"],
    "properties": {
        "clauses": schema.clauses(
            "consideredApproaches", {"type": "string"},
            "every approach you CONSIDERED for this clause, in your own words, including any "
            "you then rejected. Empty only if nothing automated could apply at all."),
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "source", "form", "targets", "artifact", "howToRun",
                             "whatCountsAsAViolation"],
                "properties": {
                    "id": {"type": "string", "description": "kebab-case, unique"},
                    "source": {"type": "string",
                               "description": "the ADR sentence this enforces"},
                    "form": {"type": "string",
                             "description": "what kind of check this is, in your own words"},
                    "targets": {"type": "string",
                                "description": "which files or artifacts this inspects"},
                    "artifact": {"type": "array", "items": {"type": "string"},
                                 "description": "the check itself, complete, ONE ARRAY ENTRY "
                                                "PER LINE, exactly as it should be saved to a "
                                                "file. Indentation is part of the line."},
                    "howToRun": {"type": "string",
                                 "description": "the exact command, and any install step"},
                    "whatCountsAsAViolation": {"type": "string",
                                               "description": "how to read the output"},
                },
            },
        },
    },
}


def build(adr: str, fingerprint: str, probe: bool = False,
          catalogue: bool = False) -> tuple[str, str, dict]:
    """The system message, user message and response schema for one arm."""
    if probe:
        return SYSTEM_PROBE, prompts.user(adr, fingerprint=fingerprint), RESPONSE_PROBE
    return ((SYSTEM_TOOLS_CATALOGUE if catalogue else SYSTEM_TOOLS),
            prompts.user(adr, fingerprint=fingerprint),
            (RESPONSE_TOOLS_CATALOGUE if catalogue else RESPONSE_TOOLS))
