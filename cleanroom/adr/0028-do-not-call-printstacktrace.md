# ADR-0028: Do not call printstacktrace

**Status:** Accepted

**Context**

`printStackTrace` writes to standard error outside the logging configuration, so the trace carries no level, no timestamp and no correlation id, and it is frequently absent from aggregated logs.

**Decision**

We will not allow any call to `printStackTrace` in main sources.

**Consequences**

Stack traces reach the log with their context. Exceptions are either logged through the logging API with a message or propagated to a caller that can do so.
