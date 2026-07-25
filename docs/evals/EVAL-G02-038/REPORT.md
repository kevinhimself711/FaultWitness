# EVAL-G02-038 Report

Result: `fail` on candidate `9adf0ba62f618b15bb41bbb56cec5fdc6229cc8a`.

Candidate binding, 23-subject static verification, candidate-bound trace-service/lab deployment,
and the explicitly inherited 60-cell isolation, six-stage trace, and 22-surface canary evidence all
passed. The lab had 24/24 Ready Deployments and an exact candidate-bound Ready trace service.

Scenario seeds 1–12 were inherited with `attempt: 0`. SEED-G02-0013 completed its one synthetic
checkout and emitted the exact Kafka sleep log. A subsequent remote source-collection command exited
1 before returning any observation, and the frozen runner incorrectly converted that
`GovernanceError` into `metric_fail`.

The same read-only collection succeeded after the concurrently OOM-restarted `accounting` pod
recovered, with the fault flag exactly restored. No metric observation existed on which to apply the
fault oracle, so this is an infrastructure-classification defect rather than a threshold failure.
N, deadline, oracle, thresholds, and failure meaning remain unchanged.

The scenario phase executed once for the exact candidate key. Seeds 14–32, deterministic baseline,
the 192 live-model trials, aggregate, reconciliation, and close-readiness did not run. Model calls,
tokens, cost, fallback, waivers, and `open_evidence` are all zero.
