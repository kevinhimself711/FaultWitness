---
document_id: FW-GATE-G02-REPORT
gate: G02
status: in_progress
evaluated_candidate_sha: 09693ceb52a883113c82ac1a7be489e826bad04f
closed_on: null
---

# G02 Gate Report

## Decision

Current decision: `NOT_READY_FORWARD_CORRECTIVE`.

The decision-complete G02 Master Plan remains frozen as `G02-master-plan-v1`. EVAL-G02-012 stopped
during candidate-binding preparation: Windows text-mode subprocess input changed LF script bytes
to CRLF and remote `/bin/sh` returned exit 2. A real local child-process byte probe reproduced the
mutation. Candidate binding and all fourteen Gate phase executions remained zero.

I-0028/EVAL-G02-013 passed all 4 byte-exact transport cases on Windows with frozen Iteration
N=4/0/4, no remote/model execution, and `open_evidence: []`. I-0029/EVAL-G02-014 is the next
replacement orchestration. G02 has not passed, no waiver is present, and no closure or tag is
authorized. I-0020/EVAL-G02-005, I-0023/EVAL-G02-008, I-0025/EVAL-G02-010, and
I-0027/EVAL-G02-012 remain immutable failed history.

Future reports must include `G01-SUPP-ACCESS-MATRIX`, `G01-SUPP-SIX-STAGE-SPANS`, and
`G01-SUPP-ALL-SURFACE-CANARY` without modifying closed G01 evidence.
