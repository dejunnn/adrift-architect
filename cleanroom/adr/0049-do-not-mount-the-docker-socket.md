# ADR-0049: Do not mount the docker socket

**Status:** Accepted

**Context**

Mounting `/var/run/docker.sock` gives the container full control of the host's Docker daemon, which is equivalent to root on the host. It is usually added so an integration test can start a database.

**Decision**

We will not allow a Compose service to mount `/var/run/docker.sock`.

**Consequences**

A compromised container cannot reach the host daemon. Tests that need containers use a remote Docker host or a dedicated runner.
