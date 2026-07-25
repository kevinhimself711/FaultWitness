# EVAL-G02-018 Report

Result: `fail`.

Candidate `1bc74b9d976cd5721eb9f57f4587a9fb83f35dc8` passed the four frozen
fail-fast preflights: all 13 required manifests, the exact candidate/environment binding, 23 frozen
subject digests, and all nine G01 manifests were valid.

## Blocking result

`lab-deploy-and-bind` pulled, transferred, and imported both I-0032 probe OCI archives, then stopped
before applying the new candidate manifest. The exact `minio/mc` digest was present in K3s
containerd as
`index.docker.io/minio/mc@sha256:eb4ea9884b77704230e2423e9004d2fa738dc272876b9cc41a297d29443b8780`,
while the frozen import verifier required the requested source reference under `docker.io/minio/mc`.
That source lookup returned no row, so the privileged import script exited 1 before it could tag or
bind the new candidate.

This is a deterministic containerd-reference normalization defect in the staging implementation,
not registry, SSH, or transfer loss. The correct archive and manifest digest are already present;
same-candidate retry cannot change the missing alias and is prohibited.

One earlier local invocation was rejected before the phase handler because the new binding asset
was still visible as an untracked file. Applying the existing repository-local in-flight binding
exclude protocol fixed that supervision precondition. It produced no phase record and performed no
remote action; the single real runner attempt above is the candidate failure.

## Adjudication

I-0033 is terminally failed with complete negative evidence and `open_evidence: []`. A forward
corrective Iteration must resolve an imported source by repository alias **and exact digest**, then
tag and verify the frozen requested target. A later replacement orchestration must use a new
candidate and Eval ID; I-0032 and I-0033 remain terminal.

New-candidate deployment, access cells, trace stages, canary surfaces, destructive scenarios,
deterministic baselines, external-service probes, and model calls were all 0. No validation N,
threshold, Ground Truth, locked test, health window, model route, token/cost ceiling,
destructive-once rule, or failure semantic changed.
