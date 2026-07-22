# EVAL-G00-005 Plan

## Purpose

Verify that state and interface designs are complete, convergent, cross-referenced, and fail-closed at approval, uncertainty, lease, identity, and failure boundaries.

## Positive checks

- Parse all state, OpenAPI, AsyncAPI, type, Command/Event, error, and failure documents against registered Schemas.
- Walk graph reachability from each initial state and reverse terminal reachability from every terminal state.
- Resolve every Actor, state, Command, Event, component, store, type, and error reference.
- Regenerate the Mermaid document in memory and compare it byte-for-byte with the committed asset.
- Run Ruff, pytest, Markdown, UTF-8, local-link, Schema, and changed-asset checks.

## Negative checks

- Add an unreachable state.
- Add an outgoing edge from a terminal state.
- Remove a transition Guard.
- Remove the R2 action-dispatch approval digest precondition.
- Make `UNCERTAIN` reconciliation automatic.
- Remove the Runtime success fencing-token precondition.
- Add caller-controlled `tenant_id` to a public request.
- Remove `expected_state_version` from approval.
- Remove `event_id` from the AsyncAPI event envelope.
- Change lost-action-response policy to bounded retry.
- Reference an unregistered error code.

Each mutation must fail for the intended conformance reason. Parser crashes or unrelated validation errors are not passes.

## Walkthrough binding

The ten W-ARCH scenarios from EVAL-G00-004 are traced through the new states and failures, with special review for approval reject/expiry, lease loss, action response loss, compensation uncertainty, cancellation, dependency fail-closed, and cross-tenant denial.
