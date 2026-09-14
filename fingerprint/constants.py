"""What the walk counts, skips and parses -- configuration, not implementation, standard library only."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = REPO_ROOT / ".dataset"

# Build output, tooling and vendored code. The ONLY filtering applied by default.
EXCLUDED_DIRECTORIES = {
    ".git", ".gradle", ".idea", ".mvn", "node_modules",
    "build", "target", "out", "dist", "bin", "venv", ".venv", "__pycache__",
}

BUILD_FILES = {
    "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle",
    "settings.gradle.kts", "build.xml", "Makefile", "Dockerfile",
    "package.json", "go.mod", "Cargo.toml", "requirements.txt", "pyproject.toml",
}

# Architecture checks the project already ships, matched by exact filename.
CHECK_MARKERS = (
    ("archunit.properties", "ArchUnit configuration"),
    (".semgrep.yml", "Semgrep rules"),
    ("checkstyle.xml", "Checkstyle"),
    ("pmd.xml", "PMD"),
)
# The same, matched against a file's PATH, for checks that announce themselves by convention.
CHECK_PATTERNS = (
    # A Java or Kotlin file named Arch*Test or ArchitectureTest*, with the extension anchored.
    (re.compile(r"[Aa]rch(itecture)?Test\w*\.(java|kt)$"), "ArchUnit tests"),
    # A `.semgrep` DIRECTORY anywhere in the path, including at the repository root.
    (re.compile(r"(^|/)\.semgrep/"), "Semgrep rules"),
    (re.compile(r"\.rego$"), "OPA/Rego policies"),
)

# Directory names that usually sit above real source rather than beside it.
SOURCE_ROOT_HINTS = ("src", "lib", "app", "internal", "pkg", "cmd", "modules")

# Test sources, for --exclude-tests. A real loss when a decision is ABOUT test code.
TEST_PATTERNS = (
    "*/src/test/*", "src/test/*",
    "*/src/testFixtures/*", "*/src/integrationTest/*", "*/src/intTest/*",
    "*/test/*", "test/*",
)

# Binary and asset files, never named by a check parameter and dominant on asset-heavy projects.
ASSET_PATTERNS = (
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.svg", "*.ico", "*.webp",
    "*.ttf", "*.woff", "*.woff2", "*.eot",
    "*.zip", "*.jar", "*.war", "*.tar", "*.gz", "*.pdf", "*.class",
)

# --- parsing ------------------------------------------------------------------------
# One grammar, one walk, several projections. Kotlin is left unparsed rather than parsed badly.

INSTALL_HINT = "pip install tree-sitter tree-sitter-java"

#: The only language parsed; files in other languages are still listed, simply never opened.
PARSED_EXTENSION = ".java"

#: Extensions whose FILENAMES are worth counting for naming conventions -- no parser needed.
NAMED_EXTENSIONS = (".java", ".kt")

#: JVM application-source extensions, the only ones reported as "present but not parsed".
JVM_SOURCE_EXTENSIONS = {".java", ".kt", ".scala", ".groovy"}

#: Node types that can carry annotations, and the position each one represents.
DECLARATION_POSITIONS = {
    "class_declaration": "class",
    "interface_declaration": "class",
    "enum_declaration": "class",
    "record_declaration": "class",
    "annotation_type_declaration": "class",
    "method_declaration": "method",
    "constructor_declaration": "method",
    "field_declaration": "field",
    "formal_parameter": "parameter",
}

#: Node types that declare a TYPE, and the word the surface reports for each.
TYPE_KINDS = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "record_declaration": "record",
    "annotation_type_declaration": "annotation",
}

#: Node types that declare a MEMBER of a type.
MEMBER_KINDS = {
    "field_declaration": "field",
    "method_declaration": "method",
    "constructor_declaration": "constructor",
}

#: Java modifier keywords, from a fixed list so an annotation is never reported as a modifier.
MODIFIERS = frozenset({
    "public", "protected", "private", "static", "final", "abstract", "native",
    "synchronized", "transient", "volatile", "strictfp", "default", "sealed", "non-sealed",
})

#: Node types whose text is a usable name; the walker takes the first descendant of one.
NAME_NODES = ("scoped_identifier", "type_identifier", "identifier")

#: Trailing CamelCase word of a filename: CaseController -> Controller.
NAME_SUFFIX = re.compile(r"([A-Z][a-z0-9]*)$")

#: An adjacent <groupId>/<artifactId> pair in a pom, captured as two groups.
MAVEN_DEPENDENCY = re.compile(
    r"<groupId>\s*([\w.\-${}]+)\s*</groupId>\s*<artifactId>\s*([\w.\-${}]+)\s*</artifactId>",
    re.S)

#: A Gradle dependency line, captured as (group, artifact); the version is deliberately dropped.
GRADLE_DEPENDENCY = re.compile(
    r"""(?:implementation|api|compileOnly|runtimeOnly|testImplementation)"""
    r"""\s*[(\s]\s*["']([\w.\-]+):([\w.\-]+)""")
