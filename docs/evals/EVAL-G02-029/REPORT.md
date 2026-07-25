# EVAL-G02-029 Report

Result: `pass`.

Candidate `b4b58546c0e97d2bebb64a1fd04208e13427e7fb` passed the three named changed
branches, the complete 374-test repository check, and `eval-changed` for exactly ten declared
files. The G02 lab handler now deploys and inspects the existing trace service for the exact
candidate before the SUT result can pass. A stale deployment summary fails closed before SUT
deployment, and the trace rollout no longer contains a preset wall-clock kill.

## Real seam

The existing deployment command completed normally in 108.9 seconds with bundle digest
`714db462bc1620b139292768e1025ab67385a87b4228521f0a8ff5cc21f76fdb`.
The existing inspect command then proved the exact candidate, `1/1` Ready, and `ClusterIP`.

The first sanitized smoke completed its Job but correctly failed the frozen outcome matrix because
the buffer was not empty at smoke start. This was not adjudicated as pass and was not retried
unchanged. The existing operator relay then exported exactly two pending traces: one left by
A-G02-003 after remote ingestion but before relay, and one created by the first smoke. It reported
zero pending traces and zero pending LangSmith delivery afterward. With that attributed state
repaired, the second unchanged smoke passed the frozen LangSmith/OTLP/archive matrix and ended with
zero pending delivery.

Gate L2, six-stage/access/canary matrices, destructive scenarios, Bailian trials, model calls,
tokens, and cost were all zero. No validation N, threshold, permission, oracle, quality/performance
criterion, Ground Truth, locked-test rule, model route, token/cost ceiling, or failure semantic
changed. `open_evidence: []`.
