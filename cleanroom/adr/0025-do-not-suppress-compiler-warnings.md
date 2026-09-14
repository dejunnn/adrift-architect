# ADR-0025: Do not suppress compiler warnings

**Status:** Accepted

**Context**

`@SuppressWarnings` hides a diagnostic rather than resolving it. Once present it usually outlives the problem it was added for, and it suppresses future warnings of the same kind in that scope.

**Decision**

We will not allow the `@SuppressWarnings` annotation in main sources.

**Consequences**

Warnings are resolved rather than hidden. Code that genuinely cannot avoid one, such as a checked generic cast, is isolated in a small method with a comment.
