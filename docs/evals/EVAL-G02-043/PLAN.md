# EVAL-G02-043 Plan — Deterministic Payment Workload Corrective

## Purpose

Prove that both payment fault branches issue exactly one candidate-bound checkout after injection
and no longer depend on incidental one-user ambient traffic.

## Scope

1. Run the existing G02 lab tests targeted to payment stimulus and oracle behavior.
2. Bind the committed corrective candidate to the clean private lab through the existing deployer.
3. Execute exactly one existing `paymentUnreachable` scenario with its frozen two fault observations,
   30-second spacing, 90-second window, exact restoration, and two healthy recovery observations.
4. Record request response, correlated trace inputs, state sequence, restore digest, readiness, and
   cleanup in one reviewable artifact.
5. Confirm Gate L2 phases and model calls remain zero.

No threshold, sample count, permission, runtime image, Ground Truth, locked test, model route, token,
or cost setting changes.
