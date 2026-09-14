# ADR-0001: Keep the domain package free of spring types

**Status:** Accepted

**Context**

Domain classes currently import Spring annotations for convenience. This makes the business rules impossible to instantiate or test without a container, and ties the domain's lifetime to a framework upgrade cycle it has no stake in.

**Decision**

We will not allow any class in `..domain..` to depend on a type in `org.springframework`.

**Consequences**

Domain logic becomes testable with plain constructors and no context startup. The cost is indirection: capabilities Spring would have injected now require an interface owned by the domain and an adapter that implements it.
