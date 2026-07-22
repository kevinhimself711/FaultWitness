# EVAL-G00-004 Plan

## Purpose

Verify that the frozen architecture is complete, internally consistent, safe at every privileged boundary, and sufficient for I-0005 contract design without product implementation.

## Positive checks

- Validate `ARCHITECTURE.yaml` against its Schema and cross-reference rules.
- Confirm exact plane sets, unique component/store/state ownership, and valid invocation/store references.
- Confirm every required prohibited path and walkthrough exists.
- Resolve every accepted ADR path and every architecture-document link.
- Run Ruff, pytest, Markdown, UTF-8, Schema, local-link, and changed-asset checks.

## Walkthrough review

Review W-ARCH-001 through W-ARCH-010 for the only allowed component path and fixed outcome: read-only success, R2 approval, rejection/expiry, lease loss, lost action response, failed verification and compensation, uncertain compensation, cancel, mandatory dependency outage, and cross-tenant access.

## Negative checks

- Remove one mandatory engineering plane.
- Let a non-owner declare write authority over Incident Lifecycle.
- Add an unknown component to a walkthrough.
- Remove the Agent-to-direct-action prohibited path.
- Point an accepted ADR at a missing document.

Each case must fail with its intended architecture governance error. No state, interface, or product implementation is required for this Eval.
