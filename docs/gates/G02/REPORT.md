---
document_id: FW-GATE-G02-REPORT
gate: G02
status: in_progress
evaluated_candidate_sha: 2c51413fecf1a4c5a707b11c9744f87ab91b927e
closed_on: null
---

# G02 Gate Report

## Decision

Current decision: `NOT_READY_FORWARD_CORRECTIVE`.

The decision-complete G02 Master Plan remains frozen as `G02-master-plan-v1`. EVAL-G02-012 stopped
during candidate-binding preparation: Windows text-mode subprocess input changed LF script bytes
to CRLF and remote `/bin/sh` returned exit 2. A real local child-process byte probe reproduced the
mutation. Candidate binding and all fourteen Gate phase executions remained zero.

I-0028/EVAL-G02-013 passed all 4 byte-exact transport cases. EVAL-G02-014 then passed four preflights
and lab deployment before proving that `gate_probe.py` cannot import Python 3.11-only `datetime.UTC`
on the private host's Python 3.8. I-0029 is terminal `failed`; provisioning, all 60 access cells,
later remote phases, and model calls remained zero with `open_evidence: []`.

I-0030/EVAL-G02-015 passed both actual managed-Python 3.8 compatibility cases. EVAL-G02-016 then
passed four preflights and lab deployment before the exact pinned `minio/mc` helper Pod entered
`ImagePullBackOff`: the image was absent from K3s and the node's Docker Hub request timed out.
I-0031 is terminal `failed`; provisioning, all 60 access cells, later phases, and model calls
remained zero with `open_evidence: []`.

I-0032/EVAL-G02-017 passed all three local deterministic staging cases. The five existing Docker
Hub SUT archives now share the same digest-verified path with exactly two namespaced probe archives;
the frozen 30-image SUT digest is unchanged. V-G02-009/010/011/017 Iteration N remained 4/0/4/0,
remote and model execution remained zero, and `open_evidence: []`.

EVAL-G02-018 then passed four preflights before `lab-deploy-and-bind` exposed deterministic
containerd reference alias behavior: the exact `minio/mc` digest existed under `index.docker.io`,
while the verifier required a `docker.io` source before tagging. I-0033 is terminal `failed`;
new-candidate deployment, all matrices, destructive scenarios, external-service probes, and model
calls remained zero with `open_evidence: []`.

I-0034/EVAL-G02-019 passed all three local deterministic alias-resolution cases. Exact requested
source, alias-only exact digest, and wrong-digest fail-closed behavior all matched the frozen
contract; V-G02-009/010/011/017 Iteration N remained 4/0/4/0, remote/model execution remained zero,
and `open_evidence: []`.

EVAL-G02-020 then passed the four preflights and deployment with 24 ready Deployments. The first
24 database access cells passed; `s3:g02/scenarios/|canonical-owner` failed because the frozen
runner used `mc stat`, which attempted `ListBucket` before exercising the exact `GetObject` grant.
Read-only diagnosis proved the user enabled, candidate policy attached, sentinel present, and no
`ListBucket` permission. I-0035 is terminal `failed`; 35 remaining access cells and all downstream
phases, destructive scenarios, external-service probes, and model calls remained zero.

I-0036/EVAL-G02-021 is the next exact-GetObject runner corrective; I-0037/EVAL-G02-022 is the later
replacement orchestration. G02 has not passed, no waiver is present, and no closure or tag is
authorized. All earlier failed Eval assets remain immutable history.

Future reports must include `G01-SUPP-ACCESS-MATRIX`, `G01-SUPP-SIX-STAGE-SPANS`, and
`G01-SUPP-ALL-SURFACE-CANARY` without modifying closed G01 evidence.
