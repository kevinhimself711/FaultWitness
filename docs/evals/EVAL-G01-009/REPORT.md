# EVAL-G01-009 Report

## Result

Result: pending.

Candidate `bc8c040a1529c2b60702ed6db7d9b0358fc06661` is the current immutable
I-0015 audit candidate. It passed `verify-fast` with 210 tests, `eval-changed`,
candidate-bound deployment of the platform schema and three private services,
real OIDC Control API, sanitized Trace, authenticated Model Gateway, four-runtime,
five-case NetworkPolicy, and Docker-coexistence smokes.

All eleven platform workloads remained Ready and candidate-bound during two
separate 15-minute observation windows. Both audit invocations subsequently
returned the same unspecialized remote-command/transport error after the window;
the operator explicitly adjudicated that post-window generic error as non-blocking
for the 15-minute readiness criterion. The failed invocations remain in terminal
history and are not represented as successful full EVAL-G01-009 runs.

This checkpoint does not complete EVAL-G01-009. Earlier Eval debt, the complete
fourteen failure walkthroughs, public cross-platform evidence, clean-clone and
rollback rehearsal, reconciliation, and positive close-readiness remain open.

## Passing checkpoint evidence

- Candidate deployment: platform, migrations `001_i0011` through `003_i0013`,
  Control API, Keycloak realm, Trace Service, and Model Gateway.
- Private readiness: Control API, Trace Service, and Model Gateway each `1/1 Ready`
  behind `ClusterIP`; eleven managed platform workloads Ready.
- Live behavior: OIDC create/read/SSE and tenant/role/approval denials; sanitized
  LangSmith/OTLP/archive delivery with zero pending; OIDC-to-Bailian Qwen with
  attributable usage.
- Runtime: runc, gVisor, Kata, and NVIDIA workload smokes; all five frozen
  NetworkPolicy cases; existing Docker baseline with zero regression.

## Open evidence

- Replay EVAL-G01-001 through EVAL-G01-008 on the final candidate-equivalent
  artifact set and clear every manifest's declared evidence debt.
- Complete all fourteen failure walkthroughs, including persistence, queue,
  checkpoint, SSE load, trace outage, canary, policy-outage, clean-clone, restore,
  rollback, and reconciliation matrices.
- Bind required Windows and Ubuntu public checks and private evidence to one final
  full SHA, then run positive and negative close-readiness without closing G01.
