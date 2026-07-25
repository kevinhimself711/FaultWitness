# EVAL-G02-043 Report

Result: `pass` on candidate `bd374683de25b824af8669a993c8c7b771c6001e`.

All 38 G02 lab tests passed. The existing deployer recreated `fw-sut` and reached 24/24 Ready on the
exact candidate. One existing-runner `paymentUnreachable` scenario then sent one cart (HTTP 200) and
one expected-failing checkout (HTTP 500). Each of the two unchanged fault observations found a
correlated checkout error and payment connection error; exact restoration matched the original
digest and both recovery observations were healthy.

The state sequence was `HEALTHY → FAULT_ACTIVE → HEALTHY`. The run used the frozen two-observation
N, 30-second spacing, 90-second window, trace oracle, cleanup, and recovery semantics. Gate L2
phases, model calls, fallback, threshold changes, waivers, and `open_evidence` are zero.
