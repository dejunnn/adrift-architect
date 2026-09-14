# ADR-0007: Declare test methods only in classes named test

**Status:** Accepted

**Context**

Test methods have appeared in helper and fixture classes. The build's test include pattern is `*Test`, so those methods are compiled but never executed, and they read as covered when they are not.

**Decision**

We will require every method annotated with `@Test` to be declared in a class whose simple name ends in `Test`.

**Consequences**

Every test method the build compiles is a test method the build runs. Shared setup moves to base classes or extensions that hold no `@Test` methods.
