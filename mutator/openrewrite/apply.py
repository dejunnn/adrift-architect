"""Run one declarative recipe against a COPY of a repository, with the OpenRewrite Maven plugin."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from mutator.recipes import CUSTOM_COORDINATE, GENERATED_PACKAGE, JavaRecipe, Recipe

MODULE = Path(__file__).resolve().parent
GENERATED_DIR = MODULE / "src" / "main" / "java" / GENERATED_PACKAGE.replace(".", "/")


@dataclass(frozen=True)
class Applied:
    """What happened when a recipe was run."""

    changed: list[str]
    detail: str
    #: Everything the plugin printed, kept even on success -- only it explains a no-op run.
    output: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.changed)


def install(java: list[JavaRecipe], mvn: str = "mvn") -> tuple[bool, str, str]:
    """Compile and install model-authored recipes so the plugin can resolve them, clearing them first."""
    shutil.rmtree(GENERATED_DIR, ignore_errors=True)
    if not java:
        return True, "no generated recipes", ""
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    for recipe in java:
        (GENERATED_DIR / f"{recipe.class_name}.java").write_text(recipe.source,
                                                                 encoding="utf-8")
    # `clean install`, not a targeted delete: Maven's staleness check loses a race with an IDE.
    done = subprocess.run([mvn, "clean", "install"], cwd=MODULE, capture_output=True,
                          text=True, timeout=1800)
    sources = "\n\n".join(f"=== {r.class_name}.java ===\n{r.source}" for r in java)
    output = f"{sources}\n\n=== mvn install, EXIT {done.returncode} ===\n{done.stdout}{done.stderr}"
    if done.returncode != 0:
        lines = [l for l in (done.stdout + done.stderr).splitlines()
                 if "ERROR" in l and ".java:" in l]
        return False, ("generated recipe did not compile: "
                       + (lines[0].strip()[:240] if lines else f"mvn exited {done.returncode}")), \
            output
    return True, f"installed {', '.join(r.class_name for r in java)}", output


def _make_sources_visible_to_maven(copy: Path) -> list[str]:
    """Move Java sources living OUTSIDE `src/` into `src/main/java` in the copy, and say where from."""
    destination = copy / "src" / "main" / "java"
    if not destination.is_dir():
        return [], {}
    moved, came_from = [], {}
    for source in sorted(copy.iterdir()):
        if not source.is_dir() or source.name in ("src", "target", ".git"):
            continue
        java = list(source.rglob("*.java"))
        if not java:
            continue
        for file in java:
            target = destination / file.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, target)
            came_from[target.relative_to(copy).as_posix()] = \
                file.relative_to(copy).as_posix()
        shutil.rmtree(source)
        moved.append(f"{source.name}/ ({len(java)} file(s))")
    return moved, came_from


def rebuild(tree: Path, mvn: str = "mvn") -> tuple[list[Path], str]:
    """Recompile a mutated tree with ITS OWN build, from scratch, and return the class directories."""
    if not (tree / "pom.xml").is_file():
        return [], "not a Maven project -- ArchUnit verification needs the project's own build"
    shutil.rmtree(tree / "target" / "classes", ignore_errors=True)
    done = subprocess.run([mvn, "-q", "-DskipTests", "compile"], cwd=tree,
                          capture_output=True, text=True, timeout=1800)
    if done.returncode != 0:
        lines = [l.strip() for l in (done.stdout + done.stderr).splitlines()
                 if l.startswith("[ERROR]") and "http" not in l and l.strip() != "[ERROR]"]
        # A mutation that does not compile is a real outcome: the caller records INCONCLUSIVE.
        return [], ("mutant did not compile: "
                    + (lines[0][:200] if lines else f"mvn exited {done.returncode}"))
    from enforcer.archunit.runner import find_classes
    found = find_classes(tree)
    return found, (f"rebuilt with maven, {len(found)} class dir(s)" if found
                   else "maven build produced no classes")


def _is_build_output(relative: Path, copy: Path) -> bool:
    """Is this path Maven build output, at any module depth? `target` counts only beside a pom.xml."""
    parts = relative.parts
    if parts and parts[0] == ".git":
        return True
    for i, segment in enumerate(parts[:-1]):
        if segment == "target" and (copy.joinpath(*parts[:i], "pom.xml")).is_file():
            return True
    return False


def _changed_files(original: Path, copy: Path, came_from: dict[str, str]) -> list[str]:
    """Every file the RECIPE changed, excluding everything the harness itself put there."""
    changed = []
    for path in sorted(copy.rglob("*")):
        if not path.is_file() or path.name == "adrift-recipe.yml":
            continue
        relative = path.relative_to(copy)
        # Maven's build output, and the repository `apply` initialises. Neither is source.
        if _is_build_output(relative, copy):
            continue
        counterpart = original / came_from.get(relative.as_posix(), relative.as_posix())
        try:
            if not counterpart.is_file() or \
                    path.read_bytes() != counterpart.read_bytes():
                changed.append(relative.as_posix())
        except OSError:
            continue
    return changed


def apply(recipe: Recipe, repo: Path, into: Path, mvn: str = "mvn") -> Applied:
    """Copy `repo` to `into`, run `recipe` there, and report what actually changed."""
    repo, into = Path(repo).resolve(), Path(into).resolve()
    shutil.rmtree(into, ignore_errors=True)
    into.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(repo, into)
    # The mutant must be its own repo root, or OpenRewrite's git-ignore lookup excludes the copy.
    subprocess.run(["git", "init", "-q"], cwd=into, capture_output=True, text=True)
    relocated, came_from = _make_sources_visible_to_maven(into)

    if not (into / "pom.xml").is_file():
        return Applied([], "not a Maven project -- the coordinate invocation needs a pom")

    recipe_file = into / "adrift-recipe.yml"
    recipe_file.write_text(recipe.as_yaml(), encoding="utf-8")
    # NOT `-q`: the plugin reports what it parsed and changed at INFO, and the output is captured.
    command = [mvn, "org.openrewrite.maven:rewrite-maven-plugin:run",
               f"-Drewrite.configLocation={recipe_file}",
               f"-Drewrite.activeRecipes={recipe.name}"]
    if recipe.needs_custom_module:
        command.append(f"-Drewrite.recipeArtifactCoordinates={CUSTOM_COORDINATE}")

    done = subprocess.run(command, cwd=into, capture_output=True, text=True, timeout=1800)
    output = (f"$ {' '.join(command)}\n\n=== RECIPE ===\n{recipe.as_yaml()}\n"
              f"=== EXIT {done.returncode} ===\n{done.stdout}{done.stderr}")
    if done.returncode != 0:
        # The last line of a failed Maven run is a URL; the first ERROR line naming a cause is not.
        lines = [l.strip() for l in (done.stdout + done.stderr).splitlines()
                 if l.startswith("[ERROR]") and "http" not in l and l.strip() != "[ERROR]"]
        return Applied([], lines[0][:240] if lines else f"maven exited {done.returncode}", output)
    if "validation error" in output:
        # Exit code 0 with a validation error means the options failed to bind -- a tool failure.
        line = next((l.strip() for l in output.splitlines() if "validation error" in l), "")
        return Applied([], f"recipe options did not bind: {line[:200]}", output)

    changed = _changed_files(repo, into, came_from)
    note = f"{len(changed)} file(s) changed"
    if relocated:
        note += f"; relocated {', '.join(relocated)} so Maven could see them"
    return Applied(changed, note if changed else
                   "the recipe matched nothing -- the copy is identical to the original",
                   output)
