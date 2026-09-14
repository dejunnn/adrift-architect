# ADR-0029: Validate arguments with explicit exceptions

**Status:** Accepted

**Context**

The `assert` keyword is disabled unless the JVM is started with `-ea`, so an assertion that guards a real precondition silently does nothing in production.

**Decision**

We will not allow the `assert` keyword in main sources.

**Consequences**

Precondition checks run in every environment. Each assertion becomes an explicit `if` that throws a named exception.
