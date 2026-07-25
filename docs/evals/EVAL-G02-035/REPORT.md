# EVAL-G02-035 Report

Result: `pass` on candidate `0ef51cdb5987aa8b1c5cf17e712fe513f1d33b74`.

Three targeted memory-observer branches, all 384 repository tests, Markdown validation, and
changed-asset validation passed. The first sample is retained without declaring it active; the
second sample uses the unchanged monotonic oracle; non-growth retains a cleanup comparator and
remains a metric failure.

The existing lab deployment runner bound 24/24 Deployments to the candidate. The existing scenario
runner executed only `SEED-G02-0008`, consuming the two healthy recovery observations from
EVAL-G02-034 `SEED-G02-0007`. Its working set grew from 54,370,304 to 57,614,336 bytes, both recovery
observations were healthy, and original/restored flag digests matched exactly. Gate L2, the full
scenario matrix, baselines, model calls, tokens, and cost were zero. `open_evidence: []`.
