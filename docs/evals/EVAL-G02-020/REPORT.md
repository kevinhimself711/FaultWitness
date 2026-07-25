# EVAL-G02-020 Report

Result: `fail`.

Candidate `2c51413fecf1a4c5a707b11c9744f87ab91b927e` passed the four frozen
fail-fast preflights and `lab-deploy-and-bind`. The preflights proved all 13 required manifests,
the exact candidate/evidence binding, 23 frozen subject digests, and all nine G01 manifests. The
lab bound the expected image-set digest and reported all 24 Deployments ready.

## Blocking result

`isolation-access-matrix` persisted 25 of 60 cells. The first 24 database cells passed. Cell
`s3:g02/scenarios/|canonical-owner` then returned `actual_allow: false` against an expected allow,
so the phase correctly stopped with deterministic `metric_fail` and did not run downstream work.

Read-only diagnosis proved that the MinIO user was enabled, the exact candidate-bound policy was
attached, the policy allowed `s3:GetObject` on `g02/scenarios/*`, and the sentinel existed. The
frozen runner nevertheless used `mc stat`; that client operation first attempted `ListBucket`,
which the isolation policy intentionally does not grant. This is an object-read probe semantics
defect, not an authorization-policy failure and not resumable infrastructure failure.

## Adjudication

I-0035 is terminally failed with complete negative evidence and `open_evidence: []`. A forward
corrective Iteration must replace the object-read probe with a true `GetObject` operation that does
not require directory listing, prove allow and deny behavior locally, and then hand a new candidate
to a later replacement orchestration.

No trace, canary, destructive scenario, deterministic baseline, external-service, or model phase
ran. No validation N, threshold, isolation policy, Ground Truth, locked test, health window, model
route, token/cost ceiling, destructive-once rule, or failure semantic changed.
