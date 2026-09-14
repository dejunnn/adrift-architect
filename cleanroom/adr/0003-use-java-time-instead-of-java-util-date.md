# ADR-0003: Use java time instead of java util date

**Status:** Accepted

**Context**

`java.util.Date` is mutable, carries no time zone, and its accessors were deprecated two decades ago. Mixed use of it and `java.time` in the same codebase produces conversion bugs at the boundary.

**Decision**

We will not allow any class to depend on `java.util.Date`.

**Consequences**

Date and time handling is uniform and immutable. Existing persistence mappings that expect `java.util.Date` need converters.
