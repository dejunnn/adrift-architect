# ADR-0027: Read the clock through an injected clock

**Status:** Accepted

**Context**

A direct call to `System.currentTimeMillis` binds the caller to real time, so any behaviour that depends on the current instant can only be tested by waiting.

**Decision**

We will not allow any call to `System.currentTimeMillis` in main sources.

**Consequences**

Time-dependent behaviour is testable by supplying a fixed clock. Every class that needs the current instant declares a `Clock` dependency.
