# ADR-0048: Do not trigger workflows on pull request target

**Status:** Accepted

**Context**

`pull_request_target` runs the workflow from the base branch with a write-scoped token, but against the fork's code. A pull request from an untrusted fork can therefore reach a privileged token.

**Decision**

We will not allow a workflow to declare a `pull_request_target` trigger.

**Consequences**

Pull-request automation runs without repository write access. Workflows that must comment or label do so from a separate, manually triggered workflow.
