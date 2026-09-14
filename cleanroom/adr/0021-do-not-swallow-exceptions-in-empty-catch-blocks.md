# ADR-0021: Do not swallow exceptions in empty catch blocks

**Status:** Accepted

**Context**

A catch block with no body discards the only evidence that something failed. Theprogram  continues on a bad assumption and the eventual symptom appears far from the cause.

**Decision**

We will not allow a catch block with an empty body in main sources.

**Consequences**

Every caught exception is logged, handled, or rethrown. A genuinely ignorable exception carries a comment and an explicit no-op call so the intent is visible.
