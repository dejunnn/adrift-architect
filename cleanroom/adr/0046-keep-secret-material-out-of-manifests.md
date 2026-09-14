# ADR-0046: Keep secret material out of manifests

**Status:** Accepted

**Context**

A `Secret` with inline `data` puts base64 of the real credential into version control, where it is readable by anyone with repository access and stays in the history after rotation.

**Decision**

We will not allow a `Secret` manifest to carry inline `data` or `stringData`.

**Consequences**

Credentials live in the secret store and are injected at deploy time. The manifest declares that a secret is needed without containing it.
