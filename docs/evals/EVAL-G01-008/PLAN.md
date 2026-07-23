# EVAL-G01-008 Plan — Multi-Family ModelGateway and Compatible Channels

## Purpose

Prove one ModelGateway contract across Qwen, DeepSeek, and GLM live model families through Bailian and across the NewAPI-compatible wire protocol, without claiming independent-provider redundancy or diagnosis quality.

## Candidate protocol

1. Discover account-visible models through the secured channel, select exact non-floating tool-capable snapshots, and freeze the capability/route catalog before trials.
2. For each of three families, run complete, JSON-Schema structured output, forced tool, and streaming three times: 36 live Bailian trials total.
3. Validate every structured/tool result with the same strict Pydantic types and reconstruct streamed content/tool calls deterministically.
4. Against a controlled NewAPI fake upstream, inject success, usage missing, 408/429/5xx, auth/config 4xx, timeout, invalid JSON, invalid tool arguments, malformed chunk, and interrupted stream.
5. Correlate route, exact model, retry, repair, fallback, first-chunk boundary, usage, latency, and sanitized LangSmith run for every trial.

## Blocking checks

- Transient pre-output failure retries at most once; auth/config failures do not retry.
- Invalid structured output repairs at most once and only pre-output failures may fallback.
- Once any chunk is visible, cross-model continuation is prohibited and interruption becomes `PARTIAL_FAILED`.
- Price is recorded only from a versioned known catalog; otherwise it is typed `unknown`.
- No request sends credential, raw user identity, private reasoning, or server locator in prompt or metadata.

## Pass criteria

- Bailian live trials: 36/36; structured/tool schema validity and final stream reconstruction: 100%.
- Post-first-chunk model/channel switch, unattributed route/model/usage/trace, and secret/PII canary hit: 0.
- NewAPI offline success/failure wire matrix: 100% expected typed outcomes.
- Report explicitly states one live upstream, three model families, and no live NewAPI/cross-provider redundancy evidence.

## Evidence contract

LangSmith traces are blocking and sanitized. Public evidence includes exact non-secret model IDs, family/channel, aggregate result/latency/usage, controlled run IDs, digests, and candidate SHA; raw prompts/responses remain private unless synthetic and allowlisted.
