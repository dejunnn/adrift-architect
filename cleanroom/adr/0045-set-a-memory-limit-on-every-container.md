# ADR-0045: Set a memory limit on every container

**Status:** Accepted

**Context**

A JVM without a container memory limit sizes its heap from the node's total memory. Under pressure the kernel kills the largest process, which is usually the service itself, and the eviction looks like a random crash.

**Decision**

We will require every container in a workload manifest, including init containers, to declare `resources.limits.memory`.

**Consequences**

The JVM sizes its heap from a limit the manifest states, and the scheduler can place the pod honestly. Every service must know its own working set.
