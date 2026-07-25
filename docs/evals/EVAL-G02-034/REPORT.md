# EVAL-G02-034 Report

Result: `fail` on candidate `7fdb34999bef3413ccf16774440135730b23b5e4`.

Candidate binding, 23-subject static verification, candidate-bound trace-service/lab deployment,
and the explicitly inherited 60-cell isolation, six-stage trace, and 22-surface canary evidence all
passed. The lab had 24/24 Ready Deployments and an exact candidate-bound Ready trace service.

Scenario seeds 1–3 were inherited with `execution_count: 0`. Seeds 4–7 executed once and passed.
`SEED-G02-0008/emailMemoryLeak` terminated the destructive phase with
`scenario cleanup blocked and quarantined the SUT: list index out of range`. The observer tests a
monotonic two-sample memory oracle by duplicating each individual sample; the first sample therefore
cannot become active or enter `fault_samples`, and cleanup later indexes an empty list. This is a
deterministic runner defect rather than infrastructure failure.

The scenario phase executed once for the exact candidate key. Seeds 9–32, deterministic baseline,
the 192 live-model trials, aggregate, reconciliation, and close-readiness did not run. Model calls,
tokens, cost, fallback, waivers, and `open_evidence` are all zero.
