# EVAL-G02-006 Plan — Lifecycle Monotonicity Governance

## Purpose

Prove the forward-only Iteration lifecycle and frozen Gate failure classification introduced by
I-0021 without running any G02 Gate phase or external service.

## Deterministic cases

1. Accept `planned -> in_progress`.
2. Accept `in_progress -> completed`.
3. Reject `completed -> in_progress`.
4. Reject `failed -> planned`.
5. Reject terminal-record deletion and a historical terminal reactivation hidden by a later
   terminal commit.

## Pass criteria

- All five cases pass under the named lifecycle validator.
- The policy epoch is repository-tracked and deletion fails closed.
- I-0020 contains no owner-reopen route.
- `verify-fast` and `eval-changed` pass.
- No runtime, model, Gate phase, validation N, threshold, locked test, or Ground Truth changes.
