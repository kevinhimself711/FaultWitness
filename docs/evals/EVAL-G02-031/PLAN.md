# EVAL-G02-031 Plan — Payment-Unreachable Caller-Trace Observation Corrective

## Purpose

Falsify or confirm the single caller/callee trace-source hypothesis, then—only if confirmed—verify
the minimum `paymentUnreachable` observer correction without running a Gate L2 matrix.

## Frozen checks

1. Read-only attribution compares the frozen failed interval using identical Jaeger query fields
   except `service=checkout` versus `service=payment`; it records only counts, error status,
   sanitized status descriptions, and service names.
2. Existing G02 lab pytest covers caller connection error, absence of connection error, and the
   unchanged `paymentFailure` callee branch.
3. The existing scenario runner executes only `SEED-G02-0002` once, requires two
   `FAULT_ACTIVE` observations, restores the exact flag document, and proves healthy recovery.
4. The real-seam artifact is candidate/environment bound and contains no credential, endpoint,
   raw trace, secret, PII, response body, or private reasoning.
5. Gate L2, full 32-scenario execution, access/trace/canary matrices, baselines, Bailian, model
   calls, tokens, and cost remain zero; `open_evidence: []` is required.

The exact attribution operation is the existing host-pinned `run_remote_script` transport running
a fixed read-only Python query against the in-cluster Jaeger API for the EVAL-G02-030 failure
interval. It performs no flag write and no workload mutation. Elapsed estimates are observability
only and never kill execution.
