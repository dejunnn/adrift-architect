# ADR-0010: Do not name interfaces with an impl suffix

**Status:** Accepted

**Context**

An interface named `...Impl` inverts the convention: readers expect `Impl` to denote a concrete class, so the name misleads at every call site.

**Decision**

We will not allow any interface to have a simple name ending in `Impl`.

**Consequences**

The `Impl` suffix keeps its single meaning. Interfaces are named for the capability they describe.
