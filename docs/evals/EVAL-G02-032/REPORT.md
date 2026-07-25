# EVAL-G02-032 Report

Result: `fail` with complete negative evidence and `open_evidence: []`.

Candidate `df1fea44c15baaa3f2af72d2067def1d7a9f522c` passed its candidate binding, static subject
check, and candidate/runtime deployment with 24/24 Deployments ready. The unchanged manifest debt,
G01 debt, 60-cell isolation, six-stage trace and 22-surface canary evidence was explicitly inherited
from EVAL-G02-030 with execution count zero; no matrix was rerun.

The destructive scenario phase ran once. SEED-G02-0001, 0002 and 0003 passed, including the fixed
`paymentUnreachable` observer. SEED-G02-0004 then failed before injection because the runner took a
redundant one-shot control sample instead of consuming SEED-G02-0003's two healthy recovery
observations, which the frozen Master Plan explicitly permits as the next precondition. The prior
recovery ended healthy, the exact flag document was restored, and a later read-only frozen observer
sample returned `ready=true` and HTTP 200. Baselines, Bailian, tokens and cost remained zero.

The attempt is terminal. C-G02-006 owns only the prior-recovery precondition runner defect; this
report does not reopen or relabel A-G02-005.
