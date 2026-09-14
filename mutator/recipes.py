"""The OpenRewrite vocabulary -- open, never gated by a list -- and the recipe object built from an answer."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from fnmatch import fnmatchcase

import yaml

#: The recipe vocabulary is not gated, which is why no discovered catalogue is cached here.

#: Empty by design, and the emptiness is the control: both catalogue arms offer only what the substrate ships.
CUSTOM_RECIPES: frozenset[str] = frozenset()

#: The package a model-authored recipe must declare, so generated code is never mistaken for ours.
GENERATED_PACKAGE = "adrift.mutator.generated"

#: The artifact carrying any generated recipes; a recipe from outside the plugin needs its coordinate named.
CUSTOM_COORDINATE = "adrift.mutator:openrewrite-modifiers:0.1.0"

#: Answers that are not a recipe. Each is a real outcome, not a failure to try.
YES = "YES"
NO_RECIPE = "NO_RECIPE"                  # no recipe, and none could be written, for this edit
NOT_IN_REPOSITORY = "NOT_IN_REPOSITORY"  # the construct the decision governs is not here


@dataclass(frozen=True)
class JavaRecipe:
    """One recipe the model wrote, as a Java source file."""

    class_name: str
    source: str

    @property
    def fqn(self) -> str:
        return f"{GENERATED_PACKAGE}.{self.class_name}"

    @property
    def problems(self) -> list[str]:
        """Why this source cannot be compiled and installed as written. Empty when it can."""
        problems = []
        if not re.fullmatch(r"[A-Z]\w*", self.class_name):
            problems.append(f"{self.class_name!r} is not a Java class name")
        if f"package {GENERATED_PACKAGE};" not in self.source:
            problems.append(f"must declare `package {GENERATED_PACKAGE};`")
        if not re.search(rf"class\s+{re.escape(self.class_name)}\b", self.source):
            problems.append(f"does not declare `class {self.class_name}`")
        if "extends Recipe" not in self.source:
            problems.append("does not extend org.openrewrite.Recipe")
        # OpenRewrite ignores unknown properties, so a missing @JsonProperty fails silently.
        if "@Option" in self.source and "@JsonProperty" not in self.source:
            problems.append("has @Option without @JsonProperty on the constructor parameter; "
                            "options would silently fail to bind")
        return problems


@dataclass(frozen=True)
class Recipe:
    """One declarative OpenRewrite recipe: a name, a rationale, and a list of sub-recipes."""

    name: str
    display: str
    why: str
    recipe_list: list[dict] = field(default_factory=list)
    java: list[JavaRecipe] = field(default_factory=list)

    @property
    def names(self) -> list[str]:
        """The sub-recipe identifiers, in order."""
        return [next(iter(entry)) for entry in self.recipe_list]

    @property
    def needs_custom_module(self) -> bool:
        """Whether the run must name our artifact's coordinate to resolve a sub-recipe."""
        return any(name in CUSTOM_RECIPES or name.startswith(GENERATED_PACKAGE + ".")
                   for name in self.names)

    def as_yaml(self) -> str:
        """The recipe as OpenRewrite's declarative YAML, emitted by PyYAML rather than built from strings."""
        document = {
            "type": "specs.openrewrite.org/v1beta/recipe",
            "name": self.name,
            "displayName": self.display,
            "description": self.why,
            # A recipe taking no options is a BARE string entry; one taking options is a mapping.
            "recipeList": [name if not options else {name: dict(options)}
                           for entry in self.recipe_list
                           for name, options in (next(iter(entry.items())),)],
        }
        return yaml.safe_dump(document, sort_keys=False, default_flow_style=False,
                              allow_unicode=True, width=10 ** 6)


def normalise_recipe_list(entries) -> list[dict]:
    """One canonical `{recipeName: {option: value}}` per sub-recipe, from either wire shape."""
    canonical = []
    for entry in entries or []:
        if not isinstance(entry, dict) or not entry:
            continue
        if "recipeName" in entry:
            canonical.append({entry["recipeName"]: {
                option["name"]: option.get("value")
                for option in entry.get("options") or []
                if isinstance(option, dict) and "name" in option}})
        else:
            canonical.append(entry)
    return canonical


def from_answer(mutation: dict, adr: str) -> Recipe:
    """A Recipe from one entry of a model's `mutations` list."""
    return Recipe(name=f"adrift.mutate.{adr}.{mutation['id']}",
                  display=mutation.get("display") or mutation["id"],
                  why=mutation.get("why") or "",
                  # Normalised here too: `apply` builds a Recipe from a mutations.json it did not write.
                  recipe_list=normalise_recipe_list(mutation.get("recipeList")),
                  java=[JavaRecipe(entry["className"], "\n".join(entry["source"]))
                        for entry in (mutation.get("javaRecipes") or [])])


def ungrounded(mutation: dict, surface: dict) -> list[str]:
    """Names the mutation uses that do not appear in the repository's mutation surface."""
    types = surface.get("types", [])
    known = {entry["fqn"] for entry in types}
    # The surface omits `simpleName` because it is the last segment of `fqn`; derived here.
    known |= {entry["fqn"].rsplit(".", 1)[-1] for entry in types}
    known |= {member["name"] for entry in types for member in entry.get("fields", [])}
    known |= set(surface.get("packages", []))
    known |= set(surface.get("externalPackagePrefixes", []))

    # A recipe parameterised by FILE rather than by type names a path, which the surface records.
    paths = {entry["path"] for entry in types if entry.get("path")}
    # A used-but-undeclared type appears only as an external prefix, so matching is by prefix.
    prefixes = tuple(f"{prefix}." for prefix in surface.get("externalPackagePrefixes", []))

    def grounded(name: str) -> bool:
        """Whether one name resolves to something this repository actually contains."""
        return (name in known
                or name.startswith(prefixes)
                # A path or glob; fnmatchcase, so the verdict ignores filesystem case rules.
                or any(fnmatchcase(path, name) for path in paths))

    declared = set(mutation.get("targets") or [])
    problems = [f"{name!r} is not in the mutation surface" for name in sorted(declared)
                if not grounded(name)]

    for entry in mutation.get("recipeList") or []:
        for value in (next(iter(entry.values())) or {}).values():
            if not isinstance(value, str) or not value or value in declared:
                continue
            if "." in value and value[0].isalpha() and " " not in value:
                problems.append(f"{value!r} is used but not declared in targets")
    return problems
