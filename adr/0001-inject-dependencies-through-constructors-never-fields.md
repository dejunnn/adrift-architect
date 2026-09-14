# ADR-0001: Inject dependencies through constructors never fields

**Status:** Accepted

**Context**

Field injection hides a class's collaborators from its constructor, so an instance can exist in a half-built state and a unit test cannot supply a double without a container or reflection.

**Decision**

We will not allow dependencies to be injected into fields.

**Consequences**

Every collaborator appears in the constructor signature, which makes the dependency list visible and the class constructible in a plain test. Circular dependencies that field injection concealed must be resolved.
