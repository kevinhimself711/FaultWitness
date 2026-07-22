# EVAL-G01-003 Report

## Result

Result: pending (implementation and private deployment checkpoint complete; full Eval not run).

Candidate `0c8b66c7fc4e781d0a44582a3c8c97ce5e543ed3` was deployed through the candidate-bound Helm command with bundle digest `affed4056efed7e2e74a5916d667e7a083e7a3528a3588e6fa22f7b17f065028`. The sanitized point-in-time inspection observed all 11 required workloads Ready. Secrets, kubeconfig, private locators, raw objects, and raw telemetry remained outside the repository.

This is implementation/deployment evidence only. It does not prove the 15-minute stability window, controlled restart, isolation/denial matrix, PostgreSQL restore, telemetry correlation, SBOM/license policy, or the complete EVAL-G01-003 result.

## Required evidence

- Full candidate SHA and digest-pinned deployment manifest.
- Fifteen-minute readiness and controlled-restart timeline.
- Isolation/denial matrix, PostgreSQL restore digest, telemetry control signals, SBOM, and license audit.
- Canonical command results for `verify-fast`, `eval-changed`, candidate-bound `deploy-platform` and 900-second `inspect-platform`, and the candidate-bound `eval-iteration I-0009` run.
- Sanitized public evidence that contains no kubeconfig, credential, private locator, raw dump, IdP/object-store export, or raw telemetry.

## Open evidence

The full pre-registered Eval remains open. Open items are: 15-minute readiness/recovery, paired authorized/denied boundary checks, PostgreSQL fresh-target restore digest equality, persistence after controlled restart, correlated synthetic telemetry, resource/retention bounds, deployed-image digest reconciliation, SBOM/license/provenance checks, and public-evidence secret scanning.

No partial smoke, live observation, documentation-only result, or evidence from a different SHA may be promoted to a pass claim. EVAL-G01-002 remains separate blocking debt and is not covered by this report.
