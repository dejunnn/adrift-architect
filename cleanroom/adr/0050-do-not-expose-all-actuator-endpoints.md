# ADR-0050: Do not expose all actuator endpoints

**Status:** Accepted

**Context**

Setting the actuator exposure list to a wildcard publishes every endpoint, including `heapdump` and `env`, which return process memory and the resolved configuration with credentials in it.

**Decision**

We will not allow the actuator exposure list to include a wildcard.

**Consequences**

Only the endpoints a service intends to publish are reachable. Adding one becomes a deliberate change to the configuration.
