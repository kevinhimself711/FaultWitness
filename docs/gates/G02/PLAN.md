---
document_id: FW-GATE-G02-PLAN
gate: G02
status: placeholder
authoritative: false
---

# G02 Gate Plan — Fault Laboratory and Baselines

## Status

G02 is `not_started`. This placeholder records the G01 handoff only; it is not a
decision-complete Master Plan and authorizes no implementation Iteration.

## Inherited baseline

G02 inherits candidate `4c843553bad7a13023259d474e8fea1b8c174d40`: the
waiver-free G01 platform, contracts, durable state, authenticated API, replayable
Trace, Model Gateway, runtime isolation, and operational recovery baseline.

## Planning requirement

Before implementation, a dedicated planning turn must freeze G02 scope,
non-goals, state-machine deltas, interfaces, data flow, failure semantics,
Iterations, Evals, thresholds, and closure assets. G01 evidence must not be
weakened or reinterpreted during that planning.

## Retrospective rule register

The following entries are workflow inputs for the future Master Plan, not the
Master Plan itself. `accepted` means the repository workflow decision is active;
it does not authorize implementation. `under_review` means the planning turn must
resolve the rule before freezing G02.

| ID | Candidate rule | Status |
| --- | --- | --- |
| GR-01 | Every Iteration completes its own real Eval before closure. The planning turn must first define which evidence is Iteration-local and which can only be valid on a unified Gate candidate. | under_review |
| GR-02 | The final Gate-audit Iteration only orchestrates frozen checks, reverifies one candidate, and synchronizes evidence; it adds no product behavior or substantial Eval framework. | accepted |
| GR-03 | Expensive Eval work is split into attributable phases with immutable results keyed by candidate, runtime/config digests, and environment fingerprint. | accepted |
| GR-04 | Destructive, long-running, and external-service Eval runners provide phase selection and continuation from failed or pending work. | accepted |
| GR-05 | Deterministic manifests, bindings, schemas, publication, and other preflight checks run before soak, recovery, or paid live matrices. | accepted |
| GR-06 | A stability window runs once for an unchanged runtime artifact and environment fingerprint, under failure semantics frozen before execution. | accepted |
| GR-07 | Gate walkthroughs aggregate immutable phase evidence instead of rerunning remote work. | accepted |
| GR-08 | Eval harnesses, negative fixtures, and close-readiness fixtures pass before the business candidate is frozen. | accepted |
| GR-09 | Candidate-bound evaluation uses separate `candidate_sha` and asset-only `evidence_head_sha` identities under ADR-0009. | accepted |
| GR-10 | Gate closure covers the controlled root documents and status assets, and lifecycle fields agree before verification. | accepted |
| GR-11 | Live external-service matrices persist every trial atomically, resume failed or pending trials, and do not discard completed trials after one attributable transport failure. | accepted |
| GR-12 | A verified root cause removes any generic operator-adjudicated pass path; the affected phase returns to normal blocking semantics. | accepted |

GR-03, GR-04, GR-09, and GR-11 are accepted design constraints whose tooling is
explicitly not implemented by this retrospective change. Their implementation
scope and Eval must be assigned by the future G02 Master Plan.
