# EVAL-G02-004 Plan — Baselines and Scoring

## Purpose

Close I-0019 by proving deterministic scorer and threshold semantics, a three-case deterministic
baseline smoke, and four non-seed live trials with per-trial interruption and resume.

## Validation set

- V-G02-012 with five scoring fixtures and V-G02-013 over all seven thresholds at L1.
- V-G02-014 Iteration layer with three non-seed cases.
- V-G02-015 Iteration layer with two non-seed cases across both live baselines.

## Pass criteria

- Scoring and thresholds are exact and reproducible.
- Four live trials use the exact model with no fallback and demonstrate trial-local resume.
- Gate seeds are not used and no Gate-scale matrix runs.
- Model usage and cost are attributable; `open_evidence` is empty.

The runner has no preset orchestration wall-clock kill timeout. This does not change N=4, the exact
model, the one internal transient retry, token/cost ceilings, latency measurement, failure scoring,
or any Gate metric. Each trial is persisted atomically; only `infra_failed` trials resume.
