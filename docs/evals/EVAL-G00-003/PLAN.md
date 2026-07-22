# EVAL-G00-003 Plan

## Purpose

Verify that the requirement registry is complete, traceable to the full in-scope corpus, safe to publish, and fail-closed against evidence-policy drift.

## Positive checks

- Validate all source, requirement, and evidence-matrix documents against their schemas.
- Recompute catalog category counts from source records.
- Resolve every source and requirement reference.
- Confirm exact-once matrix coverage for all 57 requirements.
- Run repository-wide Ruff, pytest, Markdown, UTF-8, local-link, and changed-asset checks.

## Negative checks

- A mandatory requirement supported only by Tier C evidence.
- A source inclusion change that drifts the frozen corpus counts.
- A requirement that references an unknown source.
- Duplicate requirement coverage in the evidence matrix.

Each negative test must fail with the intended governance error. Schema/parser crashes and unrelated failures do not count as passes.

## Publication check

Review the committed diff for raw research text, source filenames, absolute local paths, credentials, private keys, and identifying personal traces. Only anonymized metadata and original synthesis may be published.
