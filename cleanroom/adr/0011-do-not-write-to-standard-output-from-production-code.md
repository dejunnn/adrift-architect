# ADR-0011: Do not write to standard output from production code

**Status:** Accepted

**Context**

Diagnostic output written to `System.out` or `System.err` bypasses the logging configuration: it carries no level, no timestamp, no correlation id, and cannot be routed or suppressed per environment.

**Decision**

We will not allow any class to access the standard output or standard error streams.

**Consequences**

All diagnostic output is routed by the logging configuration. Code that genuinely writes to a console does so through an injected `PrintStream`.
