---
document_id: FW-GATE-G02-REPORT
gate: G02
status: in_progress
evaluated_candidate_sha: 0f3e83b871c8c69cfdb2c2321cc96e4894975d56
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

I-0032 is the sole digest-pinned probe-image offline staging corrective; I-0033/EVAL-G02-018 is the
planned replacement orchestration. G02 has not passed, no waiver is present, and no closure or tag
is authorized. All earlier failed Eval assets remain immutable history.

Future reports must include `G01-SUPP-ACCESS-MATRIX`, `G01-SUPP-SIX-STAGE-SPANS`, and
`G01-SUPP-ALL-SURFACE-CANARY` without modifying closed G01 evidence.
