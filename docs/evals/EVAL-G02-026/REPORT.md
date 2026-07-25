# EVAL-G02-026 Report

Result: `fail`.

Candidate `c51072931984865c900a5cac43ec907be82d0bb1` passed all four fail-fast
preflights and the real `lab-deploy-and-bind` phase. The private K3s lab retained the frozen
30-image digest and reported all 24 Deployments ready.

## Blocking result

`isolation-access-matrix` persisted 58 of 60 live cells. The first 57 cells passed, including the
credential-authenticated `obs:langsmith|canonical-owner` cell that blocked A-G02-001. Cell 58,
`obs:langsmith|baseline-agent`, entered the expected NetworkPolicy-denied path, but the frozen
BusyBox `wget` probe had no event-driven terminal condition for a dropped connection. The same
remote `gate_probe.py` and `wget` processes remained on the same request while the trial journal
made no progress from `2026-07-25T15:04:57.453089+00:00` through the recorded stop at
`2026-07-25T15:21:08.681881+00:00`.

This is not a threshold or permission failure. It is a runner-liveness defect: a deny result cannot
be represented without waiting for an external client's internal retry/timeout behavior. After
verifying unchanged PID/request/journal state, the operator terminated only the stalled SSH child;
the existing runner then recorded `access-58: infra_failed` and closed the phase normally. No cell
was adjudicated as passing by the operator.

## Adjudication

A-G02-002 is terminally failed with complete negative evidence and `open_evidence: []`. A forward
`C-G02-003` must repair only the denied-egress probe's terminal-event contract. The corrective must
not add a preset orchestration kill timeout, reduce the 60-cell matrix, weaken any permission, or
convert no-progress into an operator pass. A later Gate attempt uses a new candidate-bound journal.

No trace, canary, destructive scenario, deterministic baseline, Bailian call, model token, or model
cost phase ran. No validation N, quality/performance threshold, Ground Truth or locked-test
isolation rule, health-oracle window, model route, token/cost ceiling, destructive-once rule, or
failure semantic changed.
