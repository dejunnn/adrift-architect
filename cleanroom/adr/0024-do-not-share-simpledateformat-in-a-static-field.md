# ADR-0024: Do not share simpledateformat in a static field

**Status:** Accepted

**Context**

`SimpleDateFormat` is mutable and not thread-safe. Held in a static field and used from more than one request thread it silently produces wrong dates rather than failing.

**Decision**

We will not allow `SimpleDateFormat` to be assigned to a static field in main sources.

**Consequences**

Date formatting is thread-safe. Call sites move to `DateTimeFormatter`, which is immutable and may be shared.
