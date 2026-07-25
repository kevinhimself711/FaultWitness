# EVAL-G02-041 Plan — Ambient Lab Load Corrective

## Purpose

Prove that the dedicated G02 lab renders the minimum nonzero one-user ambient load and can complete
one candidate-bound checkout without a new `accounting` OOM restart.

## Scope

1. Run the existing lab tests, including exact-anchor fail-closed coverage.
2. Deploy the exact corrective candidate with the existing candidate-bound deployer.
3. Verify 24/24 Ready, `LOCUST_USERS=1`, flag `off`, and the pre-check restart count.
4. Execute exactly one existing cart/checkout stimulus with the fault flag off.
5. Verify HTTP 2xx statuses, unchanged restart count, and zero Gate/model execution.

No scenario, Gate L2 phase, baseline, or model call is in scope. Eval N, oracle windows,
thresholds, security boundaries, and explicit-HTTP failure semantics are unchanged.
