# EVAL-G01-008 Report

## Result

Result: pending immutable candidate.

I-0014 implementation now contains the versioned three-family capability catalog, unified Bailian/NewAPI-compatible adapter, strict structured/tool validation, deterministic stream reconstruction, typed usage, bounded retry/repair/pre-output fallback, post-first-chunk `PARTIAL_FAILED` behavior, publication checks, and a candidate-bound 36-trial live Eval entry point. Offline and live results are not claimed until an immutable candidate is committed and evaluated.

## Required evidence

- Full candidate SHA and catalog digest.
- Qwen, DeepSeek, and GLM complete/structured/forced-tool/stream results repeated three times: 36/36.
- Strict structured/tool validation, stream reconstruction, attributed usage and zero unplanned fallback.
- Controlled NewAPI success/failure matrix and zero post-first-chunk continuation.
- One sanitized LangSmith Trace per live trial and a final publication-boundary scan.

## Open evidence

All EVAL-G01-008 evidence remains open until the implementation candidate is committed and the candidate-bound command passes.
