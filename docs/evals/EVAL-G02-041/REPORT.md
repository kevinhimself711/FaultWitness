# EVAL-G02-041 Report

Result: `pass` on candidate `9f51ddaf8c6d2168ef6676ccb8e8b133599cd2a9`.

The first implementation candidate rendered one ambient user and 24/24 Ready Deployments but its
single no-fault checkout still returned 504. That negative seam proved the long-lived namespace
retained contaminated Kafka/PostgreSQL and Pod state; it is preserved in
`artifacts/ambient-load-seam-attempt-1.json`.

The final candidate recreated only the disposable `fw-sut` namespace without a timeout, rendered
`LOCUST_USERS=1`, and reached 24/24 Ready with flag `off` and accounting restart count zero. The
existing one-checkout stimulus then returned cart 200 and checkout 200. Postcondition inspection
kept all 24 Deployments Ready, flag `off`, and restart count zero.

Gate L2 phases, scenario trials, model calls, fallback, threshold changes, waivers, and
`open_evidence` are all zero.
