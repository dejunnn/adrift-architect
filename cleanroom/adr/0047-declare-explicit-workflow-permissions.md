# ADR-0047: Declare explicit workflow permissions

**Status:** Accepted

**Context**

A workflow without a `permissions` block inherits the repository default, which historically grants write scopes. Any action it runs then holds a token that can push to the repository.

**Decision**

We will require every workflow to declare a top-level `permissions` block.

**Consequences**

The token a workflow carries is visible in the workflow file. Jobs that genuinely need to write must widen the scope deliberately.
