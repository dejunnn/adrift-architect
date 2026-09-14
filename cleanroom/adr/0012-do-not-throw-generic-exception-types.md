# ADR-0012: Do not throw generic exception types

**Status:** Accepted

**Context**

Throwing `Exception`, `RuntimeException` or `Throwable` gives the caller nothing to dispatch on, so the only available handler is a catch-all that cannot distinguish a bug from an expected failure.

**Decision**

We will not allow any class to throw a generic exception type.

**Consequences**

Every thrown type names its failure, so callers can handle the ones they understand. The cost is one exception class per distinct failure.
