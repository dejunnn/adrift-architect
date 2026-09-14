# ADR-0013: Log through slf4j only

**Status:** Accepted

**Context**

Two logging APIs are in use. `java.util.logging` writes through a different configuration than the rest of the service, so its output has a different format and is often missing entirely from aggregated logs.

**Decision**

We will not allow any class to use `java.util.logging`.

**Consequences**

One logging configuration governs all output. Code currently on `java.util.logging` is migrated to the SLF4J API.
