---
document_id: FW-GATE-G03-PLAN
gate: G03
status: placeholder
authoritative: false
---

# G03 Gate Plan — 只读 Agent 纵切

## Status

G03 is `not_started`. This G02 handoff placeholder is not a decision-complete Master Plan and
authorizes no implementation Iteration, infrastructure mutation, credential use, deployment, or
live evaluation.

## Authoritative boundary

The final project plan defines G03 delivery as Typed State, checkpoint, interrupt, SSE/outbox;
Evidence, Hypothesis, ProbePlan, and ChangeEvent; metric, log, trace, Kubernetes, and change tools;
and a minimum Incident Console loop.

Its frozen exits are: validation E2E at least 5 percentage points above the best G02 baseline,
100% of critical conclusions traceable to EvidenceRef, and Worker/SSE recovery without lost or
duplicated state. Planning may make these decisions complete but may not lower them.

> 本条已由 [ADR-0018](../../adr/ADR-0018.md) 处置：margin 的数值因锚点失效回到待定，目标形式不变。

## Planning requirement

Before implementation, a dedicated planning turn must freeze scope, non-goals, state changes,
interfaces, data flow, tool permissions, failure semantics, Iterations, Evals, budgets, and closure
assets. G00–G02 evidence remains immutable.

## Readiness prerequisites

[AMD-0007](../../blueprint/AMENDMENTS/AMD-0007.md) freezes forward-only metric v3 without changing
metric v1, metric v2, AMD-0006, the seven Gate values, or any closed G02 asset.

Before a decision-complete G03 Master Plan can be frozen, one metric-v3 run directory must:

- contain a fresh 32-case replay with five healthy and two fault windows per case;
- pass the six-group completeness, presence-only, ambiguity, independent deterministic, and
  four-turn token-headroom preflight;
- be resumed in place for the registered live arms, without replay or definition drift; and
- satisfy the direction-neutral statistical acceptance frozen by AMD-0007.

The exact two-stage procedure is defined in
[G03_BASELINE_READINESS.md](../../runbooks/G03_BASELINE_READINESS.md). A completed but blocked run
does not authorize threshold, deterministic, prompt, packet, budget, or dataset tuning. G03 remains
`not_started` even if readiness becomes `ready`.

The five forward contract additions described by the 2026-07-28 audit remain part of G03 I-01.
Landing them during readiness work would start implementation and is therefore outside this
placeholder's authority.
