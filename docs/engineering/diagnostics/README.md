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
| `g03-r8-r9-live-divergence/` | r8 and r9 share a byte-identical dataset, yet r9's live arms score 5–6× r8's. Which round is broken? | r8. Its root-cause accuracy is *higher* (0.9583 vs 0.9479); the whole gap is evidence-citation completeness (0.1458 vs 0.8924), caused by a prompt that never disclosed the completeness rule its scoring enforced |
| `g03-metric-v3-root-signal-separability.json` (+ `-README.md`) | If `descriptions` is redacted, do the six declared numeric root signals alone still identify the family? | Yes — a six-way lookup. All six signals recover their own family at recall 1.000 alone, 24/32 cases have exactly one offset signal and it is always the true family, and a zero-model classifier over the frozen leave-one-case-out p99 reaches 0.9062 |

### Reading the r8/r9 divergence record

- The verdict rests on a decomposition of `core_e2e` into root-cause correctness and
  evidence-set completeness, recomputed independently from the 288 per-trial journals of each
  round; all six arm scores reproduce `aggregate.json` exactly.
- One inference is not a direct measurement: trial journals persist no prompt text and no prompt
  digest, so "the +64 turn-1 tokens are that completeness instruction" is triangulated from token
  counts, `relevant_source_digest`, and the behavioural consequence. `README.md` marks this.
- Both rounds ran on the same host, SUT, and model — this is *not* an ADR-0016/0017
  incomparability case.
- The runner hostname is redacted to `<redacted-runner-hostname-A>` in 4 files, using the same
  placeholder in both rounds so that "same hostname" remains checkable. Nothing else is redacted.

### Reading the separability probe

- It exists to split the two readings of the leakage probe's classifier **B**, which scored 32/32 on
  its own threshold test using the bare per-family quantum. Those readings — genuinely orthogonal
  signals versus false qualifications cancelling into a coincidence — point opposite ways on whether
  redaction is sufficient. Measured answer: orthogonal. **Cleaning the threshold raised
  discrimination** (0.9062 vs 0.5938), so the pre-registered contamination hypothesis is falsified.
- `adHighCpu` is the one impure channel. Its whole p99 rests on a single nonzero drift out of 124
  pooled samples, so holding out either contributing case collapses the threshold to the quantum.
  All 3 of D1's errors and all 13 of D2's are cases this channel steals; the other five signals fire
  zero times on foreign cases under either rule.
- Every off-diagonal co-occurrence except `adHighCpu`'s is 0: faults do not propagate across
  services in this dataset. Remove CPU's 8 false qualifications and the single-offset fraction is
  32/32.
- The single-offset fraction is 0.7500, sitting exactly on the registered floor rather than clearing
  it. Read the `orthogonality` counts before treating that reading as settled.
- `-README.md` carries the five human-readable tables (per-case offsets, false qualifications,
  co-occurrence, per-family accuracy, D1−D2 delta). The JSON is the machine record.

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

uv run python -m faultwitness_dev g03-separability \
  --dataset .audit/g03-readiness/<run>/scenarios.json \
  --output docs/engineering/diagnostics/g03-metric-v3-root-signal-separability.json
```

Zero model calls. The source dataset is recorded in the artifact as `source_run`, with
`source_run_invalidated` set when that run directory is marked `-invalidated-*`.
