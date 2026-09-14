# ADR-0009: Confine jdbc types to the persistence package

**Status:** Accepted

**Context**

`java.sql` types have leaked into service and web classes. Once a `ResultSet` crosses a layer boundary the connection's lifetime becomes ambiguous and the caller cannot be tested without a database.

**Decision**

We will not allow classes outside `..persistence..` to depend on `java.sql`.

**Consequences**

JDBC lifetimes stay inside one package. Callers receive domain types instead, which costs a mapping step per query.
