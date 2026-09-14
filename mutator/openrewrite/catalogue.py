"""A catalogue of stock OpenRewrite recipes for seeding violations, mirroring the enforcer's catalogue."""

from __future__ import annotations

#: Recipes that break a decision by moving or retyping code.
_STRUCTURE = {
    "retype-reference": {
        "recipe": "org.openrewrite.java.ChangeType",
        "summary": "make every reference to one type point at another",
        "required": ["oldFullyQualifiedTypeName", "newFullyQualifiedTypeName"],
        "optional": ["ignoreDefinition"],
        "notes": "the usual way to introduce a forbidden dependency: retype a field or "
                 "parameter to a type the decision bans. `ignoreDefinition: true` changes uses "
                 "without renaming the declaration.",
    },
    "move-package": {
        "recipe": "org.openrewrite.java.ChangePackage",
        "summary": "move every type in a package to another package",
        "required": ["oldPackageName", "newPackageName"],
        "optional": ["recursive"],
        "notes": "takes a type into or out of a constrained scope. Prefer moving the offending "
                 "type INTO the scope the decision protects, rather than moving the protected "
                 "scope, which changes the decision's subject rather than breaching it.",
    },
    "create-class": {
        "recipe": "org.openrewrite.java.CreateEmptyJavaClass",
        "summary": "add a new type in a named package",
        "required": ["sourceRoot", "packageName", "className"],
        "optional": ["modifier", "overwriteExisting", "relativePath"],
        "notes": "use when the decision forbids a KIND of type existing somewhere. A rule that "
                 "only inspects types the project already had will not see it.",
    },
}

#: Recipes that break a decision through annotations.
_ANNOTATION = {
    "remove-annotation": {
        "recipe": "org.openrewrite.java.RemoveAnnotation",
        "summary": "delete an annotation wherever it appears",
        "required": ["annotationPattern"],
        "optional": [],
        "notes": 'the pattern is an annotation signature, e.g. "@java.lang.Override" or '
                 '"@org.springframework.stereotype.Service".',
    },
    "replace-annotation": {
        "recipe": "org.openrewrite.java.ReplaceAnnotation",
        "summary": "swap one annotation for another",
        "required": ["annotationPatternToReplace", "annotationTemplateToInsert"],
        "optional": ["classpathResourceName"],
        "notes": "the insert is a TEMPLATE, e.g. `@org.springframework.stereotype.Service`. "
                 "The nearest thing to adding an annotation: there is no AddAnnotation recipe, "
                 "so add by replacing one the target already carries.",
    },
    "set-annotation-attribute": {
        "recipe": "org.openrewrite.java.AddOrUpdateAnnotationAttribute",
        "summary": "add or change an attribute on an existing annotation",
        "required": ["annotationType", "attributeName", "attributeValue"],
        "optional": ["oldAttributeValue", "addOnly", "appendArray"],
        "notes": "for decisions about how something is configured rather than whether it is "
                 "annotated at all.",
    },
    "remove-annotation-attribute": {
        "recipe": "org.openrewrite.java.RemoveAnnotationAttribute",
        "summary": "drop one attribute from an annotation",
        "required": ["annotationType", "attributeName"],
        "optional": [],
        "notes": "",
    },
    "rename-annotation-attribute": {
        "recipe": "org.openrewrite.java.ChangeAnnotationAttributeName",
        "summary": "rename an attribute on an annotation",
        "required": ["annotationType", "oldAttributeName", "newAttributeName"],
        "optional": [],
        "notes": "",
    },
}

#: Recipes that break a decision through a type's contract.
_CONTRACT = {
    "remove-implements": {
        "recipe": "org.openrewrite.java.RemoveImplements",
        "summary": "stop a class implementing an interface",
        "required": ["interfaceType"],
        "optional": ["filter"],
        "notes": "`filter` narrows to one fully-qualified class; without it every implementor "
                 "is changed, which is usually broader than a single decision.",
    },
    "widen-method-access": {
        "recipe": "org.openrewrite.java.ChangeMethodAccessLevel",
        "summary": "change a method's visibility",
        "required": ["methodPattern", "newAccessLevel"],
        "optional": ["matchOverrides"],
        "notes": 'the pattern is an AspectJ-style signature, e.g. '
                 '"com.example.api.Gateway charge(..)". `newAccessLevel` is public, protected '
                 "or private. NOTE this reaches methods only -- no shipped recipe changes a "
                 "FIELD's visibility or a CLASS's modifiers.",
    },
    "rename-method": {
        "recipe": "org.openrewrite.java.ChangeMethodName",
        "summary": "rename a method and every call to it",
        "required": ["methodPattern", "newMethodName"],
        "optional": ["matchOverrides", "ignoreDefinition"],
        "notes": "renaming out of a rule's selector EVADES the rule rather than breaching the "
                 "decision; prefer it only when the decision itself is about the name.",
    },
    "remove-throws": {
        "recipe": "org.openrewrite.java.RemoveMethodThrows",
        "summary": "drop a declared checked exception from a method",
        "required": ["methodPattern", "exceptionTypePattern"],
        "optional": ["matchOverrides"],
        "notes": "",
    },
    "add-method-parameter": {
        "recipe": "org.openrewrite.java.AddMethodParameter",
        "summary": "add a parameter to a method",
        "required": ["methodPattern", "parameterType", "parameterName"],
        "optional": ["parameterIndex"],
        "notes": "",
    },
    "delete-method-argument": {
        "recipe": "org.openrewrite.java.DeleteMethodArgument",
        "summary": "delete an argument from every call to a method",
        "required": ["methodPattern", "argumentIndex"],
        "optional": [],
        "notes": "`argumentIndex` is zero-based.",
    },
    "add-literal-argument": {
        "recipe": "org.openrewrite.java.AddLiteralMethodArgument",
        "summary": "insert a literal argument into every call to a method",
        "required": ["methodPattern", "argumentIndex", "literal"],
        "optional": ["primitiveType"],
        "notes": "use for decisions about how an API is called, e.g. a forbidden flag value.",
    },
    "retarget-to-static": {
        "recipe": "org.openrewrite.java.ChangeMethodTargetToStatic",
        "summary": "make an instance call a static call on another type",
        "required": ["methodPattern", "fullyQualifiedTargetTypeName"],
        "optional": ["returnType", "matchOverrides", "matchUnknownTypes"],
        "notes": "introduces a dependency on the target type, which is often the breach.",
    },
    "change-return-type": {
        "recipe": "org.openrewrite.java.ChangeMethodInvocationReturnType",
        "summary": "change the declared return type of a method invocation",
        "required": ["methodPattern", "newReturnType"],
        "optional": [],
        "notes": "",
    },
}

#: Recipes that reach imports, literals and text.
_TEXT = {
    "use-static-import": {
        "recipe": "org.openrewrite.java.UseStaticImport",
        "summary": "convert qualified calls to a static import",
        "required": ["methodPattern"],
        "optional": [],
        "notes": "changes what an import-shaped rule sees without changing behaviour.",
    },
    "no-static-import": {
        "recipe": "org.openrewrite.java.NoStaticImport",
        "summary": "expand a static import back to qualified calls",
        "required": ["methodPattern"],
        "optional": [],
        "notes": "",
    },
    "retype-in-string": {
        "recipe": "org.openrewrite.java.ChangeTypeInStringLiteral",
        "summary": "rewrite a fully-qualified type name inside string literals",
        "required": ["oldFullyQualifiedTypeName", "newFullyQualifiedTypeName"],
        "optional": [],
        "notes": "reaches reflective and configuration references a type-aware recipe misses.",
    },
    "repackage-in-string": {
        "recipe": "org.openrewrite.java.ChangePackageInStringLiteral",
        "summary": "rewrite a package name inside string literals",
        "required": ["oldPackageName", "newPackageName"],
        "optional": [],
        "notes": "",
    },
    "replace-string-literal": {
        "recipe": "org.openrewrite.java.ReplaceStringLiteralValue",
        "summary": "replace one string literal value with another",
        "required": ["oldLiteralValue", "newLiteralValue"],
        "optional": [],
        "notes": "for decisions carried by a configuration string rather than by a type.",
    },
    "replace-constant": {
        "recipe": "org.openrewrite.java.ReplaceConstant",
        "summary": "replace references to a constant with a literal",
        "required": ["owningType", "constantName", "literalValue"],
        "optional": [],
        "notes": "",
    },
    "find-and-replace": {
        "recipe": "org.openrewrite.text.FindAndReplace",
        "summary": "literal text substitution in any file",
        "required": ["find", "replace"],
        "optional": ["filePattern", "regex", "caseSensitive"],
        "notes": "no type awareness, and it reaches files no language parser claims -- YAML, "
                 "Dockerfiles, properties. The only entry here that leaves Java.",
    },
}

CATALOGUE: dict[str, dict] = {**_STRUCTURE, **_ANNOTATION, **_CONTRACT, **_TEXT}


def problems(recipe_id: str, params: dict) -> list[str]:
    """Everything wrong with one selection, or an empty list. Call before `render`."""
    entry = CATALOGUE.get(recipe_id)
    if entry is None:
        return [f"no catalogue recipe with id {recipe_id!r}"]
    if not isinstance(params, dict):
        return [f"{recipe_id}: paramsJson must be a JSON object"]
    found = []
    missing = [p for p in entry["required"] if not str(params.get(p, "")).strip()]
    if missing:
        found.append(f"{recipe_id}: missing required parameter(s) {', '.join(missing)}")
    allowed = set(entry["required"]) | set(entry["optional"])
    unknown = sorted(set(params) - allowed)
    if unknown:
        found.append(f"{recipe_id}: {entry['recipe']} has no option(s) "
                     f"{', '.join(unknown)} -- it takes {', '.join(sorted(allowed))}")
    return found


def render(recipe_id: str, params: dict) -> dict:
    """The recipe invocation for one selection, as `apply` expects it. Call `problems` first."""
    entry = CATALOGUE[recipe_id]
    allowed = set(entry["required"]) | set(entry["optional"])
    return {entry["recipe"]: {k: v for k, v in params.items() if k in allowed}}


def describe() -> str:
    """The catalogue as prompt text: every shape, its parameters and its caveats."""
    lines = []
    for recipe_id, entry in CATALOGUE.items():
        lines.append(f"    {recipe_id}")
        lines.append(f"        {entry['summary']}")
        lines.append(f"        recipe: {entry['recipe']}")
        lines.append(f"        required: {', '.join(entry['required']) or '(none)'}")
        if entry["optional"]:
            lines.append(f"        optional: {', '.join(entry['optional'])}")
        if entry["notes"]:
            lines.append(f"        NOTE {entry['notes']}")
        lines.append("")
    return "\n".join(lines)
