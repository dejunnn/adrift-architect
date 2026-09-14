# ADR-0022: Do not use broken hash algorithms

**Status:** Accepted

**Context**

MD5 and SHA-1 both have practical collision attacks. Any integrity or signature check built on them can be defeated by an attacker who can supply one of the two inputs.

**Decision**

We will not allow `MessageDigest.getInstance` to be called with `MD5` or `SHA-1` in main sources.

**Consequences**

Digests carry their intended guarantee. Stored values computed with a broken algorithm must be recomputed or versioned.
