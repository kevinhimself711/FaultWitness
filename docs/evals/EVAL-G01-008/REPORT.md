# EVAL-G01-008 Report

## Result

Result: pass.

Final candidate `cea2e63948d86bac3a3ae5d3afa68b477f20e3c2` passed EVAL-G01-008. Qwen `qwen3.7-plus-2026-05-26`, DeepSeek `deepseek-v3.2`, and GLM `glm-5.2` each passed complete, strict structured output, named forced-tool, and streaming capabilities three times: 36/36 live Bailian trials. Every trial used its primary route with zero unplanned fallback, returned attributable usage, and exported one allowlist-only LangSmith Trace.

The controlled NewAPI-compatible suite passed success, explicit missing usage, transient `408/429/5xx`, permanent authentication/configuration failures, timeout, invalid JSON, invalid tool arguments, malformed chunks, bounded retry/repair/pre-output fallback, and post-first-chunk `PARTIAL_FAILED` behavior. Publication scanning passed with no credential, prompt, response, private reasoning, user identity, or server locator committed.

Aggregate live evidence: 3,156 total tokens, median latency 5,030.299 ms, p95 latency 6,862.43 ms. Catalog digest: `488dd005b1964742391059a27c45a430204d430bfa4d88b25c9184df7445ca60`. Private evidence digest: `49eeaf12d5842d6e00b112a912edf91b7e91dd46083977a4e862820c525cb681`. Controlled LangSmith boundary IDs are `ba747876-6e61-543e-be5a-7156d098fc47` and `2d8042a7-b6a2-597c-90ab-9a7ee1c18d33`; independent GET returned HTTP 200 with the exact candidate SHA and a payload digest for both.

Failed candidate `49767b27813b9b9bcbfd9ec445f1c68f964c0867` is retained in history. Its live Eval failed closed when DeepSeek returned no call for generic `tool_choice=required`. Candidate `21c2a96` corrected the adapter to force the selected function by name; no threshold or locked test changed.

## Required evidence

- Full candidate SHA and catalog digest: pass.
- Qwen, DeepSeek, and GLM capability matrix: 36/36 pass.
- Strict structured/tool validation, stream reconstruction, attributed usage, and zero unplanned fallback: pass.
- Controlled NewAPI success/failure matrix and zero post-first-chunk continuation: pass.
- One sanitized LangSmith Trace per live trial and publication-boundary scan: pass.

## Open evidence

None. NewAPI live redundancy remains a frozen non-goal, and all live trials use one Bailian upstream.
