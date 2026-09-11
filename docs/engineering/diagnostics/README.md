# Diagnostic observations

Read-only instrument checks that run *before* model budget is spent, per
`docs/governance/GOVERNANCE_V2.md` (leakage probe → discrimination → disclosure symmetry → only
then buy trials).

Every artifact here carries `diagnostic_only: true` and **can never be promoted to readiness
evidence**. These are not Gate attempts, they register no work item, and they do not change
`PROJECT_STATE.yaml`. `ADR-0014` and `AMD-0005` restrict new diagnostic tooling for Gate attempts
and A/C work items; commit `1c46820` limited those clauses so they do not restrict read-only
observations marked `diagnostic_only`.

They live under `docs/` rather than `.audit/` because `.audit/**` is gitignored, and
`AGENTS.md` §3 holds that an artifact that is not committed means the run did not happen.

## Contents

| Artifact | Question | Verdict |
| --- | --- | --- |
| `g03-metric-v3-descriptions-leakage-probe.json` | Can `trace_errors.descriptions` text alone name the metric-v3 fault family, without reading `error_count` / `connection_error_count`? | `localized_leakage_trace_errors_families` — yes, on 16/16 cases of the three families that share the `trace_errors` kind |

### Reading the leakage probe

- `verdict` is decided against classifier **C** (majority class) and against the
  trio-versus-other split. It is **not** decided against classifier **B**: B thresholds on the
  bare per-family quantum rather than the frozen leave-one-case-out healthy p99, so
  `adHighCpu`'s `1e-6` quantum falls below ambient drift and distorts B's ranking. Read
  `classifiers.B_root_signal_only.qualification_detail` before comparing A to B.
- `keyword_table` is the human-facing output. It is computed over all 32 cases for inspection
  only; the predictions come from the per-fold tables in `folds`, each built from 31 cases.
- `n = 32`, so no confidence intervals and no significance tests are reported — point estimates
  and full confusion matrices only.
- Boundaries are biased toward *reporting* leakage: a false positive costs one redaction pass, a
  false negative builds every downstream decision on sand.

## Reproducing

```sh
uv run python -m faultwitness_dev g03-leakage-probe \
  --dataset .audit/g03-readiness/<run>/scenarios.json \
  --output docs/engineering/diagnostics/g03-metric-v3-descriptions-leakage-probe.json
```

Zero model calls. The source dataset is recorded in the artifact as `source_run`, with
`source_run_invalidated` set when that run directory is marked `-invalidated-*`.
