# EVAL-G02-002 Report

## Result

Result: pass.

Implementation candidate `ca9de48d68a2ecf0f52b9c9532c05a1dce37d6fc` passed the complete I-0017
Eval against the candidate-bound private K3s lab. The lab reported 24/24 Deployments Ready,
OpenSearch Ready, image-set digest
`3df502956e9c4ab2311501a9e867a40bdc1afae79ebcf3de284a95611e52610e`, and an exact
candidate binding before the Eval began.

V-G02-004 enumerated and schema-checked all 32 executable seed specifications without consuming
their Gate IDs. V-G02-005 exercised all six adapter/oracle contracts deterministically. V-G02-006
then ran four non-seed live scenarios, one per family, and observed
`HEALTHY -> FAULT_ACTIVE -> HEALTHY` with exact original/restored flag-document digest equality.

The runtime-data scenario retained the frozen lag criterion. The pinned SUT's exported record-lag
gauge remained zero after the consumer prefetched a record, while its exported consumer last-poll
age rose from the pre-injection baseline 0 to 11 seconds in both fault observations. Both
observations also contained the exact correlated Fraud Detection fault log. Recovery observations
were 11 then 0 seconds and did not worsen. This corrected the implementation signal source; it did
not change N, observation spacing, oracle windows, quality thresholds, or performance thresholds.

## Required evidence

- V-G02-004 Iteration N=32 specifications: pass.
- V-G02-005 Iteration N=6 fault adapters: pass.
- V-G02-006 Iteration N=4 non-seed live scenarios: pass.
- Exact restore for all four live scenarios: pass.
- L2 V-G02-017 clean-clone/candidate-binding runner readiness: pass.
- Core-case payloads created: none.
- Model calls, paid tokens, and baseline scoring: not performed.

## Failure history and attribution

Candidate `7b5b21de8c5ba942b34ee5bb5a9743a13e0a13d0` reached a blocking
`metric_fail` in the Kafka scenario because the observer consumed only the record-lag gauge. The
flag was restored exactly and the failed attempt remains in the repository-external I-0017 Eval
journal. No operator pass path was used. Candidate `ca9de48` corrected the observer to consume the
existing last-poll lag signal and reran the complete N=4 Eval.

## Open evidence

None. Gate-layer V-G02-006 N=32 and V-G02-017 execution remain future unified-candidate scope and
are not Iteration open evidence.
