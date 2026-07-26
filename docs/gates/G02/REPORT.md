---
document_id: FW-GATE-G02-REPORT
gate: G02
status: passed
evaluated_candidate_sha: 86a459c0bec1bcf3e583fd1280fbca2667479d2e
evaluator_revision: e419e073695015441d90f92bc4469f49310f9893
closed_on: "2026-07-26"
---

# G02 Gate Report — 故障实验室与基线

## Decision

G02 is `PASSED` without waiver. EVAL-G02-046 passed all fourteen phases and the read-only closure
inspector confirmed fourteen immutable phase records. Final reconciliation reported backlog 0,
DLQ 0, and `open_evidence=0`.

## Delivered scope

- Four Scenario DSL families, six fault classes, and 32 executable seed scenarios with exact
  injection, detection, restoration, and recovery evidence.
- A metadata-only 160-row dev/validation/locked preregistry. No G07 case payload or answer was
  materialized.
- Identity, namespace, storage-prefix, package, Ground Truth, and locked-test isolation contracts.
- Deterministic, Naive ReAct, and no-RAG baselines on shared observation packets, plus 95% clustered
  bootstrap confidence intervals.
- The seven authoritative future Agent quality floors were preserved exactly; G02 measures
  baselines and does not require a baseline to attain those floors.

## Final evidence

| Evidence | Result |
|---|---|
| Preflight phases | 4/4 pass |
| Lab deployment checkpoint | pass, inherited with execution count 0 |
| `G01-SUPP-ACCESS-MATRIX` | 60/60 pass, inherited with execution count 0 |
| `G01-SUPP-SIX-STAGE-SPANS` | 6/6 pass |
| `G01-SUPP-ALL-SURFACE-CANARY` | 22/22 pass |
| Scenario matrix | 32/32 pass |
| Deterministic baseline | N=32 pass; Core E2E 0.500 |
| Naive ReAct live baseline | N=96; Core E2E 0.000; evidence precision 1.000; schema validity 1.000 |
| no-RAG live baseline | N=96; Core E2E 0.000; evidence precision 1.000; schema validity 1.000 |
| Bootstrap aggregate | 32 case clusters, B=2,000, confidence=95% |
| Live usage | 195,377 tokens; 0.697396 CNY; fallback 0 |
| Reconciliation and close-readiness | pass; 255 trial journals; backlog 0; DLQ 0; open evidence 0 |

The two live baselines both measured Root-cause Top-3 at 0.000 and unsupported critical claims at
0.000. This negative quality result is retained honestly; it is a comparison baseline for later
Agent Gates, not a G02 quality-floor waiver.

## Validation registry

All seventeen items in `docs/gates/G02/VALIDATIONS.yaml` passed under their frozen L1/L2/L3
ownership. Zero-tolerance items retained named runners, negative fixtures, and reviewable artifact
paths. No N, threshold, permission, Ground Truth, locked test, model route, token/cost ceiling,
health window, or failure semantic was lowered.

The three G01 carry-in matrices above are closed forward without modifying G01 audit assets. G01's
production Agent-stage wall-time reconciliation remains explicitly not covered by G02 because the
production Agent stage waterfall begins later; G02 does not misrepresent phase timestamps as that
evidence.

## Execution lesson

The final scenario phase used the project-owner-authorized short debug loop: read the failed trial,
fix one existing-runner root cause, run the existing targeted tests, and replay only the affected
semantic branch and real dependencies. It introduced no new framework, fixture family, metric,
threshold, sample, or waiver. This removed repeated corrective/attempt governance without changing
experimental rigor; the post-G02 overhaul lessons are preserved in
`docs/engineering/GOVERNANCE_REFACTOR_LESSONS_LOG.md`.

## Handoff

G03 is handed off as `not_started`. Its placeholder is not a Master Plan and authorizes no
implementation. G03 must first freeze a decision-complete plan for the read-only Agent vertical
slice.
