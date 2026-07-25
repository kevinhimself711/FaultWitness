# EVAL-G02-044 Report

Result: `fail` on candidate `bd374683de25b824af8669a993c8c7b771c6001e`.

All four deterministic preflights passed. The clean exact-candidate SUT checkpoint remained 24/24
Ready, the candidate trace service was deployed and inspected Ready, and the fresh 60/60 isolation
matrix passed. The first six-stage collection invocation failed outside its trial writer after
persisting the trace. A second invocation produced a terminal `blocked: remote_command_failed` trial.

The frozen sanitized diagnostic found `PayloadConflict: trace reference reused with different
payload` in trace-service logs. `gate_probe.trace_envelope()` derived the trace ID from candidate and
environment, but generated `emitted_at` and every span timestamp from a fresh wall clock. Replay
therefore reused the ID with a different payload. No stage result, canary, scenario, deterministic
baseline, live-model trial, aggregate, reconciliation, or close-readiness phase ran after the block.
Model calls, tokens, cost, fallback, waivers, and `open_evidence` are zero.
