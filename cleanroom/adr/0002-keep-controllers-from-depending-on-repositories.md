# ADR-0002: Keep controllers from depending on repositories

**Status:** Accepted

**Context**

Controllers have begun calling repositories directly, which puts persistence concerns and transaction boundaries into the HTTP layer and leaves no single place where a use case is described.

**Decision**

We will not allow any class in `..controller..` to depend on a class in `..repository..`.

**Consequences**

Every use case has one home in the service layer. The cost is an extra delegation for controllers that genuinely only read one row.
