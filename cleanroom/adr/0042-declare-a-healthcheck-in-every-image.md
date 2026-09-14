# ADR-0042: Declare a healthcheck in every image

**Status:** Accepted

**Context**

The orchestrator can only see that the process is alive, not that it is serving. A Java service that has exhausted its thread pool stays running and keeps receiving traffic it cannot answer.

**Decision**

We will require every Dockerfile to declare a `HEALTHCHECK` instruction.

**Consequences**

The orchestrator can distinguish a running container from a serving one and restart or drain it. Each image must expose an endpoint cheap enough to poll.
