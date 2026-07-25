# EVAL-G02-040 Report

Result: `fail` on candidate `17be4f2d29448bc4db49b71dafe005d7877cd99c`.

Candidate/static preflight and candidate-bound deployment passed with 24/24 Ready Deployments.
Manifest debt, G01 debt, the unchanged 60-cell isolation, six-stage trace, 22-surface canary, and
scenario seeds 1–12 were inherited with `execution_count/attempt: 0`.

SEED-G02-0013 received `FW_G02_STIMULUS_HTTP_ERROR status=504`; the runner intentionally kept this
explicit HTTP result blocking and wrote `metric_fail`. Read-only attribution recorded fleet-wide
POST 504 traces and the `accounting` container's 62nd OOM exit 137 at
`2026-07-25T22:21:37Z`. The node itself had no MemoryPressure, the candidate binding remained exact,
and the fault flag was restored to `off`. The upstream lab's default load generator was still one
replica with `LOCUST_USERS=10`.

No later scenario, deterministic baseline, live-model trial, aggregate, reconciliation, or
close-readiness phase ran. Model calls, tokens, cost, fallback, waivers, and `open_evidence` are zero.
