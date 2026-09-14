"""The seventeen validated ArchUnit rule shapes, and the expressions they render to."""

from __future__ import annotations

import json

#: Value shapes a parameter can take, named exactly as the archived engine named them.
PACKAGES = "packagePatterns"      # ..domain.., com.foo.bar
SLICE = "slicePattern"            # com.foo.(*)..
CLASS_NAMES = "classNames"        # fully-qualified names
FRAGMENT = "nameFragment"         # a bare identifier suffix
FLAG = "boolean"
LAYERS = "layerObjects"           # [{name, packages, accessedBy}]
ADAPTERS = "adapterObjects"       # [{name, packages}]


def _quoted(values) -> str:
    """A Java varargs argument list from a Python list of strings."""
    if isinstance(values, str):
        values = [values]
    return ", ".join(json.dumps(str(value)) for value in values)


# ------------------------------------------------------------------ the seven library rules
# Identical in every project, so they take no parameters and nothing about them can be misconfigured.

_CONSTANTS = {
    "no-generic-exceptions": "NO_CLASSES_SHOULD_THROW_GENERIC_EXCEPTIONS",
    "no-field-injection": "NO_CLASSES_SHOULD_USE_FIELD_INJECTION",
    "no-standard-streams": "NO_CLASSES_SHOULD_ACCESS_STANDARD_STREAMS",
    "no-java-util-logging": "NO_CLASSES_SHOULD_USE_JAVA_UTIL_LOGGING",
    "no-joda-time": "NO_CLASSES_SHOULD_USE_JODATIME",
    "no-deprecated-api": "DEPRECATED_API_SHOULD_NOT_BE_USED",
    "assertions-have-messages": "ASSERTIONS_SHOULD_HAVE_DETAIL_MESSAGE",
}


# ------------------------------------------------------------------ the parameterised shapes


def _no_package_cycles(p) -> str:
    return f'slices().matching({_quoted(p["slices.matching"])}).should().beFreeOfCycles()'


def _slices_independent(p) -> str:
    return f'slices().matching({_quoted(p["slices.matching"])}).should().notDependOnEachOther()'


def _deny_dependency(p) -> str:
    return (f'noClasses().that().resideInAnyPackage({_quoted(p["deny.from"])})'
            f'.should().dependOnClassesThat().resideInAnyPackage({_quoted(p["deny.to"])})')


def _only_depend_on(p) -> str:
    return (f'classes().that().resideInAnyPackage({_quoted(p["depend.from"])})'
            f'.should().onlyDependOnClassesThat()'
            f'.resideInAnyPackage({_quoted(p["depend.allowed"])})')


def _only_accessed_by(p) -> str:
    return (f'classes().that().resideInAnyPackage({_quoted(p["access.target"])})'
            f'.should().onlyBeAccessed().byAnyPackage({_quoted(p["access.allowed"])})')


def _layered_architecture(p) -> str:
    """Two passes -- declare every layer, then constrain -- so `whereLayer` can name a later layer."""
    parts = ["Architectures.layeredArchitecture()",
             ".consideringOnlyDependenciesInLayers()", ".withOptionalLayers(true)"]
    for layer in p["layers"]:
        parts.append(f'.layer({_quoted(layer["name"])})'
                     f'.definedBy({_quoted(layer["packages"])})')
    for layer in p["layers"]:
        if "accessedBy" not in layer:
            continue
        callers = layer["accessedBy"]
        parts.append(f'.whereLayer({_quoted(layer["name"])})'
                     + (f'.mayOnlyBeAccessedByLayers({_quoted(callers)})' if callers
                        else ".mayNotBeAccessedByAnyLayer()"))
    return "".join(parts)


def _onion_architecture(p) -> str:
    parts = ["Architectures.onionArchitecture()", ".withOptionalLayers(true)",
             f'.domainModels({_quoted(p["domainModels"])})',
             f'.domainServices({_quoted(p["domainServices"])})',
             f'.applicationServices({_quoted(p["applicationServices"])})']
    for adapter in p.get("adapters") or []:
        parts.append(f'.adapter({_quoted(adapter["name"])}, {_quoted(adapter["packages"])})')
    return "".join(parts)


def _class_placement(p) -> str:
    """Predicate and condition rather than the fluent chain, so any number of clauses composes."""
    selector = ["DescribedPredicate.<JavaClass>alwaysTrue()"]
    if p.get("that.annotations"):
        annotations = list(p["that.annotations"])
        any_of = ["DescribedPredicate.<JavaClass>alwaysFalse()"] + [
            ".or(com.tngtech.archunit.core.domain.properties.CanBeAnnotated.Predicates"
            f".annotatedWith({_quoted(a)}))" for a in annotations]
        selector.append(f'.and({"".join(any_of)})')
    if p.get("that.packages"):
        selector.append(f'.and(JavaClass.Predicates'
                        f'.resideInAnyPackage({_quoted(p["that.packages"])}))')
    if p.get("that.nameEndingWith"):
        selector.append(f'.and(JavaClass.Predicates'
                        f'.simpleNameEndingWith({_quoted(p["that.nameEndingWith"])}))')

    conditions = []
    if p.get("should.packages"):
        conditions.append(f'ArchConditions.resideInAnyPackage({_quoted(p["should.packages"])})')
    if p.get("should.nameEndingWith"):
        conditions.append("ArchConditions.haveSimpleNameEndingWith("
                          f'{_quoted(p["should.nameEndingWith"])})')
    if p.get("should.interface"):
        conditions.append("ArchConditions.beInterfaces()")
    # Class MODIFIERS: `ClassesShould` has no `beFinal()`, but `ArchConditions.haveModifier` does.
    for key, modifier in (("should.final", "FINAL"), ("should.static", "STATIC"),
                          ("should.abstract", "ABSTRACT")):
        if p.get(key):
            conditions.append(
                f"ArchConditions.<JavaClass>haveModifier(JavaModifier.{modifier})")
    condition = conditions[0] + "".join(f".and({c})" for c in conditions[1:])
    return f'classes().that({"".join(selector)}).should({condition})'


def _members_should(p, given: str, member: str, flags: dict, annotations_key: str = "") -> str:
    """The shared body of `fields-should` and `methods-should`; modifier assertions are flags."""
    selected = (f'{given}().that().areDeclaredInClassesThat()'
                f'.resideInAnyPackage({_quoted(p["that.declaredIn"])})')
    if p.get("that.public"):
        selected += ".and().arePublic()"
    conditions = [f'ArchConditions.<{member}>beAnnotatedWith({_quoted(a)})'
                  for a in (p.get(annotations_key) or [] if annotations_key else [])]
    conditions += [f"ArchConditions.<{member}>{call}"
                   for key, call in flags.items() if p.get(key)]
    condition = conditions[0] + "".join(f".and({c})" for c in conditions[1:])
    return f"{selected}.should({condition})"


def _fields_should(p) -> str:
    return _members_should(p, "fields", "JavaField", {
        "should.private": "bePrivate()", "should.final": "beFinal()",
        "should.static": "beStatic()", "should.notPublic": "notBePublic()"})


def _methods_should(p) -> str:
    return _members_should(p, "methods", "JavaMethod", {
        "should.static": "beStatic()", "should.notPublic": "notBePublic()"},
        annotations_key="should.annotations")


# ------------------------------------------------------------------------------ the contract
# Description and renderer travel together: a shape described but not rendered is a broken promise.

#: rule id -> (summary, required params, optional params, one-of groups, notes, renderer).
#: A "one-of" group names parameters of which at least one must be present.
CATALOGUE: dict = {}


def _add(rule_id, summary, renderer, required=(), optional=(), one_of=(), notes=""):
    CATALOGUE[rule_id] = {"summary": summary, "required": list(required),
                          "optional": list(optional), "oneOf": [list(g) for g in one_of],
                          "notes": notes, "render": renderer}


for _id, _constant in _CONSTANTS.items():
    _add(_id, "", (lambda c: lambda p: f"GeneralCodingRules.{c}")(_constant))

CATALOGUE["no-generic-exceptions"]["summary"] = \
    "no class may throw Throwable, Exception, RuntimeException or Error"
CATALOGUE["no-field-injection"]["summary"] = \
    "no field may carry @Autowired, @Inject or @Resource"
CATALOGUE["no-field-injection"]["notes"] = (
    "fires on @Autowired, @Value, @Inject and @Resource and cannot be narrowed -- @Value is "
    "the one that surprises")
CATALOGUE["no-standard-streams"]["summary"] = "no class may write to System.out or System.err"
CATALOGUE["no-java-util-logging"]["summary"] = "no class may use java.util.logging"
CATALOGUE["no-joda-time"]["summary"] = \
    "no class may use Joda-Time; java.time is expected instead"
CATALOGUE["no-deprecated-api"]["summary"] = "no class may use API marked @Deprecated"
CATALOGUE["no-deprecated-api"]["notes"] = "noisy on older codebases -- opt in per project"
CATALOGUE["assertions-have-messages"]["summary"] = \
    "every assert statement carries a detail message"

_add("no-package-cycles", "no dependency cycle between the slices of a package tree",
     _no_package_cycles,
     required=[("slices.matching", SLICE,
                "(*) marks the segment to group by, e.g. com.foo.(*).. -- use (*).. when the "
                "project has no common root")],
     notes="one violation per cycle, each listing the whole loop")

_add("slices-independent",
     "slices may not reference each other at all -- stricter than acyclicity",
     _slices_independent,
     required=[("slices.matching", SLICE, "as for no-package-cycles")],
     notes="implies no-package-cycles; declaring both double-reports the same violation")

_add("deny-dependency", "classes in one package group must not depend on another",
     _deny_dependency,
     required=[("deny.from", PACKAGES, "the packages constrained"),
               ("deny.to", PACKAGES, "the packages they may not reach")],
     notes="'depends on' includes field, parameter, return and thrown types, annotations and "
           "generic arguments -- not just imports")

_add("only-depend-on",
     "classes in one package group may depend on nothing outside an allow-list",
     _only_depend_on,
     required=[("depend.from", PACKAGES, "the packages constrained"),
               ("depend.allowed", PACKAGES,
                "every package they may reach -- MUST include java.. and any framework "
                "packages, or the rule reports thousands")])

_add("only-accessed-by", "only the listed packages may reach the target", _only_accessed_by,
     required=[("access.target", PACKAGES, "the packages protected"),
               ("access.allowed", PACKAGES, "who may reach them")],
     notes="uses ACCESSES (calls and field accesses), narrower than 'depends on' -- a type "
           "used only as a parameter is not an access")

_add("layered-architecture", "layer access constraints: who may reach whom",
     _layered_architecture,
     required=[("layers", LAYERS,
                "an ARRAY OF OBJECTS, each {name, packages, accessedBy}. accessedBy ABSENT "
                "leaves the layer unconstrained; accessedBy EMPTY means no layer may access "
                "it")],
     notes="only dependencies landing inside a declared layer are considered, so third-party "
           "imports are never violations")

_add("onion-architecture",
     "dependencies point inward only: adapters -> application -> domain", _onion_architecture,
     required=[("domainModels", PACKAGES, "the innermost ring"),
               ("domainServices", PACKAGES, "domain behaviour"),
               ("applicationServices", PACKAGES, "use cases")],
     optional=[("adapters", ADAPTERS, "an ARRAY OF OBJECTS, each {name, packages}")],
     notes="the ring constraints are fixed by the pattern -- you declare membership only")

_add("class-placement",
     "selected classes must live in given packages and/or be named a given way",
     _class_placement,
     optional=[("that.annotations", CLASS_NAMES,
                "select classes carrying ANY of these, by fully-qualified name"),
               ("that.packages", PACKAGES, "select by package"),
               ("that.nameEndingWith", FRAGMENT, "select by name suffix"),
               ("should.packages", PACKAGES, "where they must live"),
               ("should.nameEndingWith", FRAGMENT, "how they must be named"),
               ("should.interface", FLAG, "they must be interfaces"),
               ("should.final", FLAG, "they must be declared final"),
               ("should.static", FLAG, "they must be declared static"),
               ("should.abstract", FLAG, "they must be declared abstract")],
     one_of=[("that.annotations", "that.packages", "that.nameEndingWith"),
             ("should.packages", "should.nameEndingWith", "should.interface",
              "should.final", "should.static", "should.abstract")],
     notes="annotations are matched by NAME from the class file, so no framework need be on "
           "the classpath -- but meta-annotations are not followed, so list each explicitly")

_add("fields-should", "fields of classes in given packages must carry given modifiers",
     _fields_should,
     required=[("that.declaredIn", PACKAGES, "whose fields")],
     optional=[("should.private", FLAG, ""), ("should.final", FLAG, ""),
               ("should.static", FLAG, ""), ("should.notPublic", FLAG, "")],
     one_of=[("should.private", "should.final", "should.static", "should.notPublic")],
     notes="one violation per field")

_add("methods-should",
     "methods of classes in given packages must carry given annotations/modifiers",
     _methods_should,
     required=[("that.declaredIn", PACKAGES, "whose methods")],
     optional=[("that.public", FLAG, "restrict to public methods"),
               ("should.annotations", CLASS_NAMES,
                "every selected method must carry ALL of these -- ANDed, unlike "
                "that.annotations elsewhere"),
               ("should.static", FLAG, ""), ("should.notPublic", FLAG, "")],
     one_of=[("should.annotations", "should.static", "should.notPublic")],
     notes="annotation ATTRIBUTES cannot be asserted -- presence only")


# ------------------------------------------------------------------------------ the gate


def problems(rule_id: str, params: dict) -> list[str]:
    """Why this selection cannot be rendered. Empty when it can."""
    if rule_id not in CATALOGUE:
        return [f"{rule_id!r} is not a catalogue rule"]
    shape = CATALOGUE[rule_id]
    known = {name for name, _, _ in shape["required"] + shape["optional"]}
    found = []
    for name, _, _ in shape["required"]:
        if params.get(name) in (None, "", [], {}):
            found.append(f"{rule_id} requires {name!r}")
    for group in shape["oneOf"]:
        if not any(params.get(name) not in (None, "", [], {}, False) for name in group):
            found.append(f"{rule_id} needs at least one of: {', '.join(group)}")
    for name in params:
        if name not in known:
            found.append(f"{rule_id} takes no parameter {name!r}")
    return found


def render(rule_id: str, params: dict) -> str:
    """The ArchUnit expression for one catalogue selection. Call `problems` first."""
    return CATALOGUE[rule_id]["render"](params)


def describe() -> str:
    """The catalogue as prompt text: every shape, its parameters and its caveats."""
    lines = []
    for rule_id, shape in CATALOGUE.items():
        lines.append(f"    {rule_id}")
        lines.append(f"        {shape['summary']}")
        for name, kind, doc in shape["required"]:
            lines.append(f"        {name} ({kind}, REQUIRED)" + (f" -- {doc}" if doc else ""))
        for name, kind, doc in shape["optional"]:
            lines.append(f"        {name} ({kind})" + (f" -- {doc}" if doc else ""))
        for group in shape["oneOf"]:
            lines.append(f"        at least one of: {', '.join(group)}")
        if shape["notes"]:
            lines.append(f"        NOTE {shape['notes']}")
        lines.append("")
    return "\n".join(lines).rstrip()
