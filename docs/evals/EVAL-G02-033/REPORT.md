# EVAL-G02-033 Report

Result: `pass` on candidate `7fdb34999bef3413ccf16774440135730b23b5e4`.

The targeted allow/reject branches, full repository verification, and changed-asset validation
passed. The existing lab deployment runner bound 24/24 Deployments to the candidate. The existing
scenario runner then executed only `SEED-G02-0004`, consuming the two healthy recovery observations
from EVAL-G02-032 `SEED-G02-0003` instead of taking a redundant one-shot control sample.

Both fault observations reached `FAULT_ACTIVE`, both recovery observations were healthy, and the
original/restored flag-document digests matched exactly. The artifact records
`precondition_source=prior-scenario-recovery`. Gate L2, the 32-seed matrix, access/trace/canary
matrices, baselines, model calls, tokens, and cost were zero. `open_evidence: []`.
