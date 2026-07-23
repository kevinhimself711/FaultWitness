# EVAL-G01-009 Report

## Result

Result: **PASS** on immutable candidate `cea2e63948d86bac3a3ae5d3afa68b477f20e3c2`.

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

After that private checkpoint, audit-head `aad15e2f8a617386864c6232f0cf79d6ba113019`
added the operator-approved post-window transport adjudication with fail-closed
boundary tests, 10,000-event/100-reconnect SSE and 10,000-delivery/100-crash
reference matrices, upstream-Eval debt blocking, and the exact nine-asset G01
closure boundary. `verify-fast` passes 220 tests. That intermediate audit head was
superseded by the deployed candidate below.

Candidate `16294bc617e4dadac9591df325e57622f96b67b6` subsequently incorporated
those audit changes and was redeployed across all private components. It passed
the eleven-workload readiness inspection, migrations, real OIDC Control API,
sanitized three-sink Trace, authenticated Model Gateway, four RuntimeClass,
five-case NetworkPolicy, and zero-Docker-regression smokes. This is now the
manifest's evaluated private checkpoint; the remaining evidence debt still keeps
the Eval pending.

I-0015 later passed candidate-bound durable reconciliation on `16294bc`: all six
deployment bindings and three migrations matched, while DLQ, four-owner Outbox
backlog, stale leases, and pending Trace deliveries were zero. The same candidate
passed fresh-target PostgreSQL restore with exact schema/data digest equality.
Public PR `#18` then ran audit-head `72aff8f5d23acaa1141a8b30404b9512f24a11a0`;
Ubuntu verify, Windows verify, and Ubuntu audit all passed. These public and
private checkpoints are not yet the same SHA, so final binding remains open.

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
- Reconciliation/recovery: zero DLQ, Outbox backlog, stale lease, and pending Trace;
  fresh-target PostgreSQL restore with matching schema/data digests.
- Public CI: PR `#18`, run `30001508078`, passed all three protected required checks.
- Disaster recovery: real embedded-etcd snapshot/restore recovered the K3s node
  and project services Ready; project-only Helm rollback/reinstall preserved the
  existing Docker estate.
- Durable failures: 82/82 real PostgreSQL transitions, 10,000 duplicate delivery
  attempts, 100 crash injections, fencing, and 100-message Redis consumer
  recovery passed with zero partial commit or final pending work.
- Trace/API load: live uncertain-ACK LangSmith replay preserved stable identity
  and drained to zero; the production PostgreSQL API delivered 10,000 ordered
  events across 100 reconnects with retention and backpressure checks.
- Control API: candidate `c297dc6` passed the expanded live path and denial
  matrix. Candidate `5638eb9` passed cold-JWKS Keycloak outage fail-closed with
  HTTP 401 before state mutation and recovered both services Ready.

## Open evidence at earlier checkpoints

- Replay EVAL-G01-001 through EVAL-G01-008 on the final candidate-equivalent
  artifact set and clear every manifest's declared evidence debt.
- Complete remaining failure walkthrough evidence: OPA unavailability/default
  deny, all-surface canary/correlation, supply-chain,
  clean-clone, and final same-SHA reconciliation.
- Bind required Windows and Ubuntu public checks and private evidence to one final
  full SHA, then run positive and negative close-readiness without closing G01.

## Final candidate adjudication

- Public PR run `30014259936` passed Ubuntu verify, Windows verify, and Ubuntu audit.
- Six deployment bindings and three migrations matched the candidate with zero
  DLQ, Outbox backlog, stale lease, or pending Trace delivery.
- K3s snapshot/restore, fresh-target PostgreSQL restore, Helm rollback/reinstall,
  and the operator-approved clean 15-minute readiness window passed.
- All 82 PostgreSQL transitions, 10,000 duplicate deliveries, 100 crash
  injections, fencing, Redis recovery, uncertain-ACK LangSmith replay, and the
  live 10,000-event/100-reconnect API matrix passed with final zero backlog.
- All 14 frozen walkthroughs and the 36/36 live multi-family model matrix passed.
- Final open evidence: none. Waivers: none.
