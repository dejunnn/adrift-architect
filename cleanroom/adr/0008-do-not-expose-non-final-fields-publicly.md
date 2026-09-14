# ADR-0008: Do not expose non final fields publicly

**Status:** Accepted

**Context**

Public mutable fields let any caller change an object's state without the object knowing, which defeats every invariant the constructor established.

**Decision**

We will not allow any non-final field to be declared `public`.

**Consequences**

State changes go through methods that can validate them. Public constants remain permitted, because `final` fields cannot be reassigned.
