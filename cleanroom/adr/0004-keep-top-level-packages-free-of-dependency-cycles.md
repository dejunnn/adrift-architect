# ADR-0004: Keep top level packages free of dependency cycles

**Status:** Accepted

**Context**

Two top-level packages now reference each other. A cycle means neither can be understood, tested, or extracted without the other, and it tends to grow silently.

**Decision**

We will not allow dependency cycles between top-level packages under `com.example`.

**Consequences**

Packages stay individually comprehensible and extractable. Breaking an existing cycle usually costs one new interface owned by the depended-upon side.
