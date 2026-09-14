# ADR-0003: Keep the domain model free of persistence annotations

**Status:** Accepted

**Context**

Persistence annotations on a domain type bind the model to a storage technology: the class cannot be constructed or asserted on without the mapping being valid, and a change of store becomes a change to the domain.

**Decision**

We will not allow any class in the domain model to carry a persistence annotation.

**Consequences**

Domain types stay plain objects that a test can build directly, and the mapping moves to a separate layer. The cost is an explicit translation between the domain type and the persisted one.
