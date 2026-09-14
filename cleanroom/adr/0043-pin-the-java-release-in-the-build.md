# ADR-0043: Pin the java release in the build

**Status:** Accepted

**Context**

Without an explicit release the compiler targets whatever JDK the build machine happens to have. The same source then produces different bytecode on a developer laptop and on CI, and the difference only surfaces at runtime.

**Decision**

We will require the build to set `maven.compiler.release` to an explicit version.

**Consequences**

Bytecode level is a property of the project rather than of the machine. Upgrading the language level becomes a deliberate, reviewable change.
