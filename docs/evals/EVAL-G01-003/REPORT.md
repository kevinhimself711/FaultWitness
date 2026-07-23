# EVAL-G01-003 Report

## Result

Result: **PASS** on final candidate `df644f10a4596232be24774bae209d1c1a4befa6`.

Candidate `0c8b66c7fc4e781d0a44582a3c8c97ce5e543ed3` was deployed through the candidate-bound Helm command with bundle digest `affed4056efed7e2e74a5916d667e7a083e7a3528a3588e6fa22f7b17f065028`. The sanitized point-in-time inspection observed all 11 required workloads Ready. Secrets, kubeconfig, private locators, raw objects, and raw telemetry remained outside the repository.

This is implementation/deployment evidence only. It does not prove the 15-minute stability window, controlled restart, isolation/denial matrix, PostgreSQL restore, telemetry correlation, SBOM/license policy, or the complete EVAL-G01-003 result.

## Required evidence

- Full candidate SHA and digest-pinned deployment manifest.
- Fifteen-minute readiness and controlled-restart timeline.
- Isolation/denial matrix, PostgreSQL restore digest, telemetry control signals, SBOM, and license audit.
- Canonical command results for `verify-fast`, `eval-changed`, candidate-bound `deploy-platform` and 900-second `inspect-platform`, and the candidate-bound `eval-iteration I-0009` run.
- Sanitized public evidence that contains no kubeconfig, credential, private locator, raw dump, IdP/object-store export, or raw telemetry.

## Open evidence at implementation checkpoint

The full pre-registered Eval remains open. Open items are: 15-minute readiness/recovery, paired authorized/denied boundary checks, PostgreSQL fresh-target restore digest equality, persistence after controlled restart, correlated synthetic telemetry, resource/retention bounds, deployed-image digest reconciliation, SBOM/license/provenance checks, and public-evidence secret scanning.

No partial smoke, live observation, documentation-only result, or evidence from a different SHA may be promoted to a pass claim. EVAL-G01-002 remains separate blocking debt and is not covered by this report.

## I-0015 replay checkpoint

Candidate `16294bc617e4dadac9591df325e57622f96b67b6` completed a fresh-target
PostgreSQL restore rehearsal. The project database was dumped, restored into a
new temporary database, and independently re-dumped; sanitized schema and data
SHA-256 values matched exactly, and the temporary target was removed. The same
candidate also completed two 15-minute Ready windows under the operator-approved
post-window transport adjudication. Remaining isolation, controlled-restart,
telemetry, supply-chain, and same-final-SHA evidence keeps this Eval pending.

Later I-0015 recovery rehearsals passed real K3s embedded-etcd snapshot/restore,
recovered the single node and all project workloads to Ready, and completed a
project-only Helm rollback followed by idempotent reinstall with zero regression
to the pre-existing Docker estate. Supply-chain reconciliation and final
same-SHA replay remain open.
