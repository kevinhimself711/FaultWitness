# EVAL-G02-005 Report

Result: `fail`.

Candidate `585deaee6548be0940d184bee3c73dadb4511fdb` passed the four frozen
fail-fast preflight phases and `lab-deploy-and-bind`. The lab bound all 30 pinned image subjects and
reported 24 ready Deployments. The run then stopped while producing the live input for
`isolation-access-matrix`; no downstream trace, canary, destructive scenario, deterministic
baseline, paid model, aggregate, reconciliation, or close-readiness phase ran.

## Blocking result

V-G02-009 requires all 60 access cells to match the frozen policy. Candidate-bound probes showed:

- `obs:loki|baseline-agent`: expected allow, actual deny.
- `obs:tempo|baseline-agent`: expected allow, actual deny.
- The same Loki and Tempo `/metrics` endpoints passed from canonical-owner controls in
  `fw-observability`, excluding endpoint unavailability as the cause.

The verified root cause is deterministic policy scope. `baseline-agent-allow-observability` permits
egress only to `kube-system` and `fw-sut`, while `fw-observability/default-deny` has no corresponding
baseline ingress. The raw candidate/environment-bound artifact is retained outside the repository;
its sanitized digest and pod references are recorded in
`artifacts/phases/isolation-access-matrix/failure.json`.

## Adjudication

This is a policy and zero-tolerance matrix failure, not a transient infrastructure failure. The
candidate is not eligible for resume or operator adjudication. I-0020 must become terminal
`failed`; a new forward corrective Iteration owns the policy change, and a new orchestration
Iteration evaluates the resulting candidate. Passed evidence is retained for attribution, but it
is reusable only when the corrected candidate's affected dependency closure and all bound digests
permit inheritance.

`open_evidence: []`: the failed result is fully recorded rather than deferred.
