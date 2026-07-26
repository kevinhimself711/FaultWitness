# EVAL-G02-046 Plan — Replay-Stable Unified Candidate Gate Attempt

## Purpose

Execute the frozen fourteen-phase G02 Gate Eval on candidate
`86a459c0bec1bcf3e583fd1280fbca2667479d2e` after C-G02-012 proved exact real trace replay.

## Exact phase order

1. `preflight-manifests`
2. `preflight-candidate-binding`
3. `preflight-static-inheritance`
4. `preflight-upstream-g01`
5. `lab-deploy-and-bind`
6. `isolation-access-matrix`
7. `trace-six-stage-matrix`
8. `all-surface-canary`
9. `scenario-matrix`
10. `baseline-deterministic`
11. `baseline-live`
12. `baseline-aggregate`
13. `candidate-reconciliation`
14. `close-readiness`

The first four deterministic checks execute fresh. `lab-deploy-and-bind` verifies and rebinds the
unchanged clean SUT checkpoint without redeployment: source candidate
`bd374683de25b824af8669a993c8c7b771c6001e`, image-set digest
`3df502956e9c4ab2311501a9e867a40bdc1afae79ebcf3de284a95611e52610e`, 24/24 Ready, zero
restarts, and healthy flags must hold before and after replacing only the candidate label.

`isolation-access-matrix` inherits the A-G02-011 pass with current execution count zero. Its source
phase record ran from `2026-07-25T23:36:17.876114+00:00` to
`2026-07-25T23:39:38.346751+00:00`, produced artifact digest
`a9167f6670fe3b258fd3f5f9f068657b7fb819b7db3d11f86de3ef7fe98fb4c4`, and remains at its
original public/private paths. The current access impact record must prove that no access-owned
behavior, fixture, permission, identity, namespace, object prefix, credential, route, configuration,
runtime, or environment changed. No access cell executes again.

Trace and canary execute fresh. All 32 scenarios execute fresh. The deterministic baseline, the
permanently authorized resumable 192-trial live baseline, aggregate, reconciliation, and
close-readiness follow only after their dependencies pass. No phase changes N, thresholds,
permissions, model route, token/cost ceilings, health windows, or failure meaning.
