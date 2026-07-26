# EVAL-G02-046 Report

Result: `pass` on runtime candidate `86a459c0bec1bcf3e583fd1280fbca2667479d2e` with final evaluator
revision `e419e073695015441d90f92bc4469f49310f9893`.

## Phase result

All fourteen frozen phases passed. The unchanged lab checkpoint and 60-cell isolation matrix were
inherited with `execution_count: 0`; four preflights, six-stage trace, 22-surface canary, 32
scenarios, deterministic baseline, live baseline, aggregate, reconciliation, and close-readiness
executed successfully. The read-only closure inspector confirmed fourteen immutable pass records.

The scenario matrix preserved unaffected pass journals. After targeted existing-runner fixes, only
affected email-memory seeds 8, 12, and 19 were replayed; all three passed, and the same resumable
run continued through seed 32. Failure attempts remain archived outside the repository.

## Baseline result

The deterministic baseline completed 32 cases with `core_e2e=0.5` and zero model cost. Bailian
model `qwen3.7-plus-2026-05-26` completed 192/192 live trials: 96 Naive ReAct and 96 no-RAG.
There were no malformed outputs, fallbacks, or infrastructure failures.

| Baseline | Core E2E | Root-cause Top-3 | Evidence precision | Tool schema validity | Unsupported critical claim | Tokens | Cost CNY |
|---|---:|---:|---:|---:|---:|---:|---:|
| Naive ReAct | 0.000 | 0.000 | 1.000 | 1.000 | 0.000 | 97,434 | 0.343206 |
| no-RAG | 0.000 | 0.000 | 1.000 | 1.000 | 0.000 | 97,943 | 0.354190 |

The aggregate used 32 `case_id` clusters, 2,000 bootstrap resamples, and 95% confidence intervals.
The reported live metric intervals equal their uniform estimates. These are baseline measurements,
not a claim that either baseline attains the seven future Agent quality floors frozen by G02.

Total live usage was 144,270 input tokens, 51,107 output tokens, 195,377 total tokens, and
0.697396 CNY.

## Safety, carry-in, and closure

- `G01-SUPP-ACCESS-MATRIX`: 60/60 pass, including unauthorized schema, object-prefix, and
  observability negatives.
- `G01-SUPP-SIX-STAGE-SPANS`: 6/6 pass.
- `G01-SUPP-ALL-SURFACE-CANARY`: 22/22 pass with no Secret/PII leak.
- G01 production Agent-stage wall-time reconciliation remains outside G02 because G02 does not
  execute that Agent stage waterfall; it is not represented as closed evidence here.
- Final reconciliation recorded 13 prior phases and 255 trial journals with backlog 0, DLQ 0, and
  `open_evidence=0`; close-readiness then passed as phase 14.

No quality threshold, N, permission, Ground Truth, locked test, model route, token/cost ceiling,
health window, or failure semantic was lowered or waived.
