# ADR-0005: Do not terminate the jvm from application code

**Status:** Accepted

**Context**

A call to `System.exit` inside library or request-handling code kills the process without unwinding, skipping shutdown hooks and in-flight work. It also makes the code untestable, because the test JVM dies with it.

**Decision**

We will not allow any class to call `System.exit`.

**Consequences**

Failures propagate as exceptions and are handled once, at the entry point. Code that genuinely must set an exit status returns it to `main` instead.
