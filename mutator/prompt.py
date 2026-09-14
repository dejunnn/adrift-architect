"""The mutator's system prompts and response schemas: two arms, over the enforcer's shared blocks."""

from __future__ import annotations

from core import prompts, schema
from mutator import recipes

_OPTIONS = ("Two entries mean you weighed two ways of breaking the clause and kept one; the\n"
            "rejected one still belongs in the list, and `reason` says why it was rejected.")

_WHAT_TOOLS = (
    "Produce a SOURCE EDIT that would breach the decision, expressed as an OpenRewrite\n"
    "recipe. You are not writing a check and you will never see one: the edit is judged by\n"
    "whether a check compiled from this same decision, in a separate session, reacts to it.")

_WHAT_PROBE = (
    "Produce a SOURCE EDIT that would breach the decision. You are not writing a check and you\n"
    "will never see one: the edit is judged by whether a check compiled from this same\n"
    "decision, in a separate session, reacts to it.")


def _vocabulary_block() -> str:
    """The recipes the model is shown: an annotated shortlist generated from the plugin's own classes."""
    from mutator.openrewrite import catalogue as recipe_catalogue
    return prompts.block("mutate_generate_recipes_shortlist",
                         catalogue=recipe_catalogue.describe())


def system(probe: bool = False, catalogue: bool = False) -> str:
    """The system message for one arm."""
    if probe:
        return (prompts.block("shared_preamble", artefact="mutation", what=_WHAT_PROBE)
                + prompts.block("mutate_probe_technique")
                + prompts.block("shared_coverage", artefact="mutation",
                                      field="consideredApproaches", options=_OPTIONS)
                + prompts.block("mutate_probe_output"))
    return (prompts.block("shared_preamble", artefact="mutation", what=_WHAT_TOOLS)
            + prompts.block("mutate_generate_recipes",
                            vocabulary=(_vocabulary_block() if catalogue
                                        else prompts.text("mutate_generate_recipes_freeform")),
                            # Always: writing a recipe is the answer whenever nothing offered fits.
                            custom=prompts.text("mutate_generate_recipes_custom"))
            + prompts.block("shared_coverage", artefact="mutation",
                              field="consideredRecipes", options=_OPTIONS)
            + prompts.block("mutate_generate_output",
                            # The same sentences the enforcer sends, from the same file.
                            serialisation=prompts.block("shared_serialisation",
                                                        body="Java recipe source")))


#: Fields every mutation carries, whichever arm produced it. Order is load-bearing: `why` comes first.
_COMMON = {
    "id": {"type": "string", "description": "kebab-case, unique"},
    "source": {"type": "string", "description": "the ADR sentence this violates"},
    # Always replaced by the arm below, which supplies the enum its arm actually allows.
    "expressible": {"type": "string", "description": "see the output contract"},
    "why": {"type": "string",
            "description": "why the edit breaches that sentence. Written BEFORE the edit."},
}

#: The sub-recipes as a CLOSED shape: a map keyed by recipe name cannot go to a strict provider.
_RECIPE_LIST = {
    "type": "array",
    "description": "the sub-recipes, in the order they run. Empty unless expressible is YES.",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["recipeName", "options"],
        "properties": {
            "recipeName": {"type": "string",
                           "description": "the recipe's fully-qualified name, exactly as listed "
                                          "above"},
            "options": {
                "type": "array",
                "description": "this recipe's options. Empty when it takes none.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "value"],
                    "properties": {
                        "name": {"type": "string", "description": "the option name"},
                        # Typed rather than stringified: OpenRewrite binds an option by its declared type.
                        "value": {"anyOf": [{"type": "string"}, {"type": "boolean"},
                                            {"type": "number"}],
                                  "description": "the value, in the type the option declares"},
                    },
                },
            },
        },
    },
}

_JAVA_RECIPE = {
    "type": "array",
    "description": "recipes you had to write because none available expressed the edit. Empty "
                   "when you used only existing recipes.",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["className", "source"],
        "properties": {
            "className": {"type": "string",
                          "description": "the class name; the file is <className>.java and the "
                                         f"package must be {recipes.GENERATED_PACKAGE}"},
            "source": {"type": "array", "items": {"type": "string"},
                       "description": "the complete Java file, ONE ARRAY ENTRY PER LINE"},
        },
    },
}


#: Selection by id, offered only in the catalogue arm, mirroring the enforcer's `catalogueRule`.
_CATALOGUE_SELECTION = {
    "catalogueRecipe": {"type": "string",
                        "description": "a catalogue id to render, or \"\" to write "
                                       "recipeList yourself"},
    "paramsJson": {"type": "string",
                   "description": "JSON object of parameters for catalogueRecipe, or "
                                  "\"\" when authoring freely"},
}


def response(probe: bool = False, catalogue: bool = False) -> dict:
    """The response schema for one arm."""
    if probe:
        mutation = {
            **_COMMON,
            "expressible": {"type": "string", "enum": [recipes.YES, recipes.NOT_IN_REPOSITORY],
                            "description": "YES when the edit below breaches the decision; "
                                           "NOT_IN_REPOSITORY when the construct it governs "
                                           "is absent here. Both are correct answers."},
            "form": {"type": "string",
                     "description": "what kind of edit this is, in your own words"},
            "targets": {"type": "array", "items": {"type": "string"},
                        "description": "every file, type or package the edit touches, as it "
                                       "appears in the mutation surface"},
            "artifact": {"type": "array", "items": {"type": "string"},
                         "description": "the edit itself, complete, ONE ARRAY ENTRY PER LINE, "
                                        "exactly as it should be saved to a file"},
            "howToApply": {"type": "string",
                           "description": "the exact command, and any install step"},
            "whatChanges": {"type": "string", "description": "how to confirm the edit landed"},
        }
        clauses = schema.clauses(
            "consideredApproaches", {"type": "string"},
            "every approach you CONSIDERED for this clause, in your own words, including any "
            "you then rejected. Empty only if no edit could breach the clause at all.")
    else:
        mutation = {
            **_COMMON,
            # The description carries the weight here: a bare enum invited the wrong decline.
            "expressible": {"type": "string",
                            "enum": [recipes.YES, recipes.NO_RECIPE,
                                     recipes.NOT_IN_REPOSITORY],
                            "description": "YES when the recipe below breaches the decision "
                                           "and every name resolves; NO_RECIPE when no source "
                                           "edit could breach it, including one you write "
                                           "yourself; NOT_IN_REPOSITORY when the construct it "
                                           "governs is absent here. All three are correct."},
            "targets": {"type": "array", "items": {"type": "string"},
                        "description": "every type, field, package and file name used in "
                                       "recipeList, exactly as it appears in the mutation "
                                       "surface"},
            "display": {"type": "string", "description": "one line naming the edit"},
            # BEFORE `recipeList`: strict outputs are emitted in schema order.
            **(_CATALOGUE_SELECTION if catalogue else {}),
            "recipeList": _RECIPE_LIST,
            # Always offered, and required-but-empty: a model that must say "none" has decided.
            "javaRecipes": _JAVA_RECIPE,
        }
        clauses = schema.clauses(
            "consideredRecipes", {"type": "string"},
            "every recipe you CONSIDERED for this clause, including any you then rejected. "
            "Empty only if no source edit could breach the clause at all.")

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["clauses", "mutations"],
        "properties": {
            "clauses": clauses,
            "mutations": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": False,
                          "required": list(mutation), "properties": mutation},
            },
        },
    }


def build(adr: str, fingerprint: str, surface: str, probe: bool = False,
          catalogue: bool = False) -> tuple[str, str, dict]:
    """The system message, user message and response schema for one arm; `catalogue` defaults false."""
    user = prompts.user(adr, fingerprint=fingerprint) \
        + prompts.block("mutate_user_surface", surface=surface)
    return system(probe, catalogue), user, response(probe, catalogue)
