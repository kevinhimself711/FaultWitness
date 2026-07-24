# EVAL-G02-010 Report

Result: `fail`.

Candidate `9e68e2622d18ffcbd63549a4fd2b9dedee37f74e` passed the four frozen fail-fast
preflights and `lab-deploy-and-bind`. The preflights proved all 13 required manifests, the exact
candidate/evidence binding, 22 frozen subject digests, and all nine G01 manifests. The lab bound
the expected image-set digest and reported all 24 Deployments ready.

## Blocking result

`isolation-access-matrix` failed before provisioning or its first matrix cell. On Windows,
`CandidateProbeBackend` placed the complete probe program and request inside a base64 remote script;
the privileged `run_remote_script` path then base64-wrapped that complete script again into the SSH
child-process command line. Windows `CreateProcess` rejected the oversized command with
`WinError 206` before SSH started.

This is a deterministic runner transport defect, not a remote transport interruption. The run
therefore did not create an `infra_failed` retry path and did not retry the unchanged candidate.
No access cell, trace stage, canary surface, destructive scenario, external-service probe, or model
call ran.

## Adjudication

I-0025 is terminally failed with complete negative evidence and `open_evidence: []`. I-0026 must
forward-correct the probe transport using bounded child-process arguments and deterministic local
tests; I-0027 then runs a fresh replacement orchestration. Neither I-0024 nor any older Iteration is
reopened, and no metric, validation N, threshold, locked test, Ground Truth, health window, token
ceiling, or cost ceiling changes.
