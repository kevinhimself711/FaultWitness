# EVAL-G02-041 Plan — Ambient Lab Load Corrective

## Purpose

Prove that the dedicated G02 lab recreates a clean `fw-sut` namespace, renders the minimum nonzero
one-user ambient load, and can complete one candidate-bound checkout without an `accounting` OOM.

## Scope

1. Run the existing lab tests, including exact-anchor fail-closed coverage.
2. Delete/recreate only the disposable `fw-sut` namespace and deploy the exact corrective candidate.
3. Verify 24/24 Ready, `LOCUST_USERS=1`, flag `off`, and a clean restart count.
4. Execute exactly one existing cart/checkout stimulus with the fault flag off.
5. Verify HTTP 2xx statuses, unchanged restart count, and zero Gate/model execution.

No scenario, Gate L2 phase, baseline, or model call is in scope. Eval N, oracle windows,
thresholds, security boundaries, and explicit-HTTP failure semantics are unchanged.
