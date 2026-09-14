# ADR-0044: Depend only on released versions

**Status:** Accepted

**Context**

A SNAPSHOT dependency is remade by whoever publishes it. A build that succeeded yesterday can fail today, or worse succeed with different behaviour, with no change in this repository.

**Decision**

We will not allow a dependency to be declared with a SNAPSHOT version, including under `dependencyManagement`.

**Consequences**

A given commit resolves to the same artefacts every time. Consuming an unreleased change now requires the upstream project to cut a release.
