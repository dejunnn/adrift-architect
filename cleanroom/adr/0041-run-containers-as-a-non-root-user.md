# ADR-0041: Run containers as a non root user

**Status:** Accepted

**Context**

The service image inherits root from its base image. A process that is compromised then holds root inside the container, which shortens the path to a host escape considerably.

**Decision**

We will require every Dockerfile to declare a `USER` instruction naming a non-root user.

**Consequences**

A compromised process starts unprivileged. Anything the image did at runtime that needed root -- binding a low port, writing to a system path -- must be arranged at build time instead.
