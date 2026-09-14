# ADR-0026: Do not declare synchronized methods

**Status:** Accepted

**Context**

A `synchronized` method locks on `this`, an object any caller can also lock on. The lock is therefore part of the public surface and an unrelated caller can deadlock the instance.

**Decision**

We will not allow a method in main sources to be declared `synchronized`.

**Consequences**

The lock is a private object the class owns, so no external caller can participate in it. Each synchronized method becomes a block synchronising on that field.
