# EVAL-G02-031 Report

Result: `pass`.

The fixed read-only attribution query compared the EVAL-G02-030 failure window without mutating
the SUT. `service=checkout` returned 18 connection-error spans; `service=payment` returned zero.
The affected traces contained an errored checkout `PlaceOrder` server span and an errored
checkout-side `oteldemo.PaymentService/Charge` client span. This confirmed the single caller/callee
trace-selection root cause before implementation.

Candidate `679d756dde799bc61d97655efbcf0ad91bfa25c6` changes only the
`paymentUnreachable` live trace source and same-trace correlation. Four targeted branches, 378
repository tests, and `eval-changed` for exactly three files passed. `paymentFailure`, the oracle
state machine, two-observation N, 30-second spacing, and 90-second window remain unchanged.

The existing lab runner bound all 24/24 Deployments to the candidate. The existing scenario runner
then executed only `SEED-G02-0002` once. Both fault observations had checkout failure plus correlated
PaymentService connection error; both recovery observations were healthy; the original and
restored flag digests matched exactly. Gate L2, the 32-scenario matrix, access/trace/canary matrices,
baselines, Bailian trials, model calls, tokens, and cost were zero. `open_evidence: []`.
