# ADR-0002: Do not throw generic exception types

**Status:** Accepted

**Context**

Throwing `Exception`, `RuntimeException`, `Error` or `Throwable` tells a caller nothing about what went wrong, so the only way to react to one failure and not another is to catch broadly and inspect the message.

**Decision**

We will not allow any class to throw a generic exception type.

**Consequences**

Every failure carries a type a caller can select on, and a catch clause names the condition it handles. Each new failure mode needs a declared exception class rather than a reused general one.
