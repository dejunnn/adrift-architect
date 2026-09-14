# ADR-0006: Make utility classes final

**Status:** Accepted

**Context**

Classes named `...Utils` hold only static helpers. Leaving them extensible invites subclasses that add state, which turns a namespace into an object with a lifecycle nobody intended.

**Decision**

We will require every class whose simple name ends in `Utils` to be declared `final`.

**Consequences**

Utility classes stay namespaces. Any helper that genuinely needs polymorphism must be renamed to something that is not a `Utils`.
