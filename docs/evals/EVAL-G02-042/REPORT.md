# EVAL-G02-042 Report

Result: `fail` on candidate `9f51ddaf8c6d2168ef6676ccb8e8b133599cd2a9`.

Manifest/G01 debt checks, candidate binding, static inheritance, clean candidate deployment, 60/60
isolation cells, all six trace stages, all 22 canary surfaces, and scenario seed 1 passed. Seed 2
(`paymentUnreachable`) then reached the end of the unchanged 90-second fault-observation window with
no correlated checkout/payment connection-error trace, so the runner wrote a blocking
`metric_fail: fault oracle did not reach FAULT_ACTIVE`.

The cleanup path completed: a read-only post-failure collection found both payment flags `off`, all
Deployments Ready, frontend HTTP 200, and no residual checkout error trace. Historical comparison
showed the same seed passed under prior ten-user ambient load; source inspection showed that only the
Kafka branch generated its own candidate-bound checkout. The clean lab's one-user ambient setting
therefore exposed a deterministic missing-workload-input defect in both payment branches. The
threshold, two-observation N, spacing, oracle, recovery contract, and failure classification behaved
as frozen.

No deterministic baseline, live-model trial, aggregate, reconciliation, or close-readiness phase
ran. Model calls, tokens, cost, fallback, waivers, and `open_evidence` are zero.
