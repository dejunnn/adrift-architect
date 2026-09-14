# ADR-0023: Import each type explicitly

**Status:** Accepted

**Context**

A wildcard import makes the origin of a simple name invisible at the top of the file, and a new type added to either package can silently change which class a name resolves to.

**Decision**

We will not allow wildcard imports in main sources, generated sources excepted.

**Consequences**

Every simple name in a file can be traced to a declared import. Files that import many types from one package become longer.
