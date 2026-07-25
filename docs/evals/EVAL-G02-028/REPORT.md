# EVAL-G02-028 Report

Result: `fail`.

Candidate `fbd03c464904b0969fdff9a8c89170435b80ef81` passed all four fail-fast
preflights, the real `lab-deploy-and-bind` phase, and all 60 live
`isolation-access-matrix` cells. This includes the corrected LangSmith TCP cell and the complete
Ground Truth/locked-test deny matrix. These six phase records remain immutable and each executed
exactly once.

## Blocking result

The first `trace-six-stage-matrix` invocation returned
`remote_command_or_transport_failed; exit=1` after approximately 8.2 seconds. It did not pass
through the collector's typed infrastructure handler, so no trace phase record, collection trial,
stage trial, or public matrix was written. The phase was not retried.

Frozen read-only diagnosis then established the attributable boundary. `inspect-trace-service`
failed for the current candidate, while `diagnose-trace-service` showed the service Pod `1/1
Running`, zero restarts, and a normally started Uvicorn application. Code inspection confirms that
the passed G02 lab phase deploys only `fw-sut`; it does not establish the separate
`fw-control/fw-trace-candidate` prerequisite checked by the operator relay. The remote trace action
therefore completed before `relay_langsmith` failed outside `_invoke`'s typed error wrapper.

## Adjudication

This is a deterministic runner-prerequisite gap, not a classified transient transport failure.
A-G02-003 is terminal `failed` with complete negative evidence and `open_evidence: []`. The only
forward path is C-G02-004, scoped to making the existing lab dependency deploy and verify the
candidate-bound trace service before any trace collection. A later A-G02-004 uses a new candidate
and the frozen Gate semantics; no terminal work item reopens.

No canary, destructive scenario, deterministic baseline, Bailian trial, model call, token, or model
cost phase ran. No validation N, quality/performance threshold, permission, Ground Truth,
locked-test rule, model route, token/cost ceiling, oracle, destructive-once rule, or failure
semantic changed.
