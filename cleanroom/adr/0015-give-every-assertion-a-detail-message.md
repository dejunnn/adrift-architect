# ADR-0015: Give every assertion a detail message

**Status:** Accepted

**Context**

A bare `assert` that fires reports only a line number. When one trips in a pre-production environment there is nothing in the log to say which invariant was violated or with what value.

**Decision**

We will require every `assert` statement to carry a detail message.

**Consequences**

An assertion failure explains itself without the source to hand. The cost is one message string per assertion.
