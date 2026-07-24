# EVAL-G02-007 Report

Result: pass.

Candidate `7d6e07bc142bdd5cb0bcd1a465ae3b04931b799c` passed all five deterministic
I-0022 cases. The corrected policy grants `baseline-agent` the frozen Prometheus, Loki, and Tempo
read paths plus public HTTPS while retaining the four identity-deny contracts and rejecting the
broad/private-network negative fixture. The Gate runner selects the active standard Iteration's
`eval_id`: planned I-0023 resolves EVAL-G02-008, while terminal I-0020 cannot select or overwrite
EVAL-G02-005. Terminal transition attribution also resolves to the failed record rather than a
prior Gate closure.

## Boundary

- Deterministic cases: 5/5 pass.
- External execution, Gate phase, destructive action, live access cell, and model call: none.
- Validation N, Ground Truth, locked tests, quality/performance thresholds, health-oracle windows,
  model route, token/cost ceilings, and Gate failure semantics changed: none.
- `open_evidence`: `[]`.

## Execution note

The first command wrapper created its own log directory inside the repository, so the clean-tree
guard rejected it before any case ran. Its logs are retained under
`private://faultwitness/g02/EVAL-G02-007/wrapper-attempt-1/`. The corrected wrapper wrote logs
outside the repository and the unchanged candidate passed; this was a local launch-precondition
error, not a retry of a metric, policy, or zero-tolerance failure.
