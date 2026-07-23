---
document_id: FW-GATE-G01-REPORT
gate: G01
plan_version: G01-master-plan-v1.1
status: pass
evaluated_candidate_sha: 4c843553bad7a13023259d474e8fea1b8c174d40
eval_run: EVAL-G01-009
closed_on: 2026-07-23
---

# G01 Gate Report — Platform Contracts and Trace Foundation

## Executive decision

G01 is **PASS** on immutable candidate
`4c843553bad7a13023259d474e8fea1b8c174d40` with zero waiver and zero open
evidence. All nine Iterations, nine Evals, and fourteen frozen walkthroughs are
complete. G02 is handed off as `not_started`; this closure authorizes no G02
implementation.

## Immutable evidence

| Evidence | Result |
| --- | --- |
| Ubuntu verify | pass, GitHub run `30018691533` |
| Windows verify | pass, GitHub run `30018691533` |
| Ubuntu audit | pass, GitHub run `30018691533` |
| Iterations and manifests | 9/9 completed and 9/9 pass |
| Frozen failure walkthroughs | 14/14 pass |
| Waivers and open evidence | 0 / 0 |

Public run: <https://github.com/kevinhimself711/FaultWitness/actions/runs/30018691533>

## Platform and recovery

- Eleven project workloads were candidate-bound and Ready on the private
  single-node K3s cluster while the existing Docker estate retained zero
  regression and no public control-plane listener.
- runc, gVisor, Kata, and NVIDIA workload smokes and all five frozen
  NetworkPolicy cases passed.
- Embedded-etcd snapshot/restore recovered one Ready node; fresh-target
  PostgreSQL restore matched schema and data digests; project-only Helm rollback
  and idempotent reinstall preserved the Docker baseline.
- The 15-minute readiness requirement passed under the frozen operator rule: an
  unspecialized transport error occurring only after a clean window is
  non-blocking. Every specific error and every individual matrix remained
  blocking until explicitly passed.

## Contracts, durability, and API

- All 82 legal transitions and 492 frozen rejection cases remained deterministic
  across public Ubuntu and Windows verification.
- The real PostgreSQL matrix passed all 82 transitions, 10,000 duplicate
  deliveries, 100 crash injections, and fencing checks with zero partial commit.
- Redis recovered and ACKed 100 pending messages after consumer loss; final DLQ,
  Outbox backlog, stale leases, and pending deliveries were zero.
- The authenticated Control API passed create, read, feedback, cancel, tool and
  skill paths; tenant injection, cross-tenant access, false approval, invalid
  OIDC, and future cursor attempts failed closed.
- Cold-JWKS Keycloak outage returned HTTP 401 before state mutation and recovered
  both services. The production PostgreSQL API matrix passed 10,000 ordered
  events, 100 exact reconnects, retention gap, and slow-consumer closure.

## Trace and model evidence

- Sanitized Trace delivery passed LangSmith, OTLP, and archive sinks with stable
  identity through uncertain-ACK replay and final zero pending delivery.
- Secret canaries were rejected before persistence; published evidence contains
  no credential, private locator, raw private reasoning, or reversible tenant
  identity.
- Qwen, DeepSeek, and GLM each passed complete, structured-output, forced-tool,
  and streaming capabilities three times: 36/36 live Bailian trials, zero
  unplanned fallback, attributable usage, and one sanitized LangSmith Trace per
  successful trial. NewAPI remains the frozen offline-compatible channel and is
  not claimed as an independent live provider.

## Scope boundary

G01 proves the platform, contracts, durable state, authenticated API, Trace, and
Model Gateway foundation. It does not claim G02 Agent orchestration, G03
retrieval quality, G04 privileged Action execution, G05 training/data pipeline,
or G06 multi-node scale and sandbox security.

## Closure

`eval-g01-close` passed for candidate `4c84355` with nine manifests and nine
completed Iterations. The closure commit is restricted to the exact nine frozen
asset paths and contains no implementation, test, deployment, or threshold
change.
