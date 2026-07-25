# EVAL-G02-024 Report

Result: `fail`.

Candidate `91c2ce4dc27d6e7e661b9fa6315605ba44124a97` passed all four fail-fast
preflights and the real `lab-deploy-and-bind` phase. The preflights proved 13 debt-free manifests,
the candidate/evidence ancestry, 23 frozen subject digests, and all nine G01 manifests. The private
K3s lab used the frozen 30-image digest and reported all 24 Deployments ready.

## Blocking result

`isolation-access-matrix` persisted 58 of 60 live cells. The first 57 cells passed, including all
PostgreSQL, MinIO, Prometheus, Loki, and Tempo allow/deny expectations. Cell
`obs:langsmith|canonical-owner` then returned `actual_allow: false` against `expected_allow: true`.
The phase stopped with deterministic `metric_fail`; the two later LangSmith cells and every
downstream Gate phase remained unexecuted.

The frozen runner separately classifies transport failures, HTTP 408/425/429, and 5xx responses.
This result therefore came from a non-success, nonretryable LangSmith response, but the frozen
artifact maps all such responses to a boolean deny and omits the status class. No frozen diagnostic
runner exists in this Gate attempt to distinguish authentication, authorization, or request-contract
failure. A-G02-001 consequently performed no ad hoc API call and created no operator pass route.

## Provenance bootstrap accounting

Before remote execution, two local invocations were rejected by provenance guards: one because the
binding artifact was still uncommitted, and one because its declared evidence head did not match the
clean checkout. No deployment occurred in either invocation. The corrected protocol used
`3d0692b9acfbd282bfac56e8145f54a4ae9d0b24` as the already-existing evidence checkpoint and kept
the binding untracked during execution, matching the established repository-local exclude pattern.
The real lab phase then executed exactly once.

## Adjudication

A-G02-001 is terminally failed with complete negative evidence and `open_evidence: []`. A forward
`C-G02-002` must repair the single LangSmith access-probe attribution/contract root cause using the
existing collector entrypoint and a minimum real seam proof. A later `A-G02-002` preserves the 57
passing cells as immutable history, then reruns the affected access phase and its downstream
dependencies under a new candidate-bound journal and the frozen Gate semantics.

No trace, canary, destructive scenario, deterministic baseline, Bailian call, model token, or model
cost phase ran. No validation N, threshold, permission, Ground Truth, locked test, health window,
model route, token/cost ceiling, destructive-once rule, or failure semantic changed.
