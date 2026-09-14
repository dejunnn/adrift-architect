# ADR-0030: Do not catch throwable

**Status:** Accepted

**Context**

Catching `Throwable` also catches `Error` -- `OutOfMemoryError`, `StackOverflowError`, `NoClassDefFoundError`. These signal that the JVM is no longer in a state the application can reason about, and swallowing one converts a fast failure into corrupted state.

**Decision**

We will not allow a catch clause naming `Throwable` in main sources.

**Consequences**

Errors reach the top of the stack and terminate the request or the process, which is the only safe response. Handlers that genuinely need a catch-all name `Exception` instead.
