# EVAL-G01-007 Plan — Sanitized LangSmith and OTel Trace Foundation

## Purpose

Prove that G01 platform/model activity produces complete, correlated, sanitized, outage-tolerant traces in LangSmith and the self-hosted OTel stack, with durable evidence independent of backend retention.

## Candidate protocol

1. Require I-0007-secured LangSmith and cluster credentials; select one immutable candidate and a dedicated project/run namespace.
2. Execute synthetic API, persistence, Outbox, checkpoint, model-stub, and export flows with known stage/correlation expectations.
3. Place unique secret/PII/private-reasoning canaries in every accepted and rejected input surface and scan every persistence/egress surface.
4. Interrupt LangSmith and OTel endpoints before enqueue, during export, and after acknowledgement; restore and replay the bounded buffer.
5. Compare LangSmith, Tempo, logs, metrics, local manifest, and wall-clock records; drain the candidate buffer and archive sanitized digests.

## Blocking checks

- Trace allowlist excludes raw identity, server locator, credentials, private chain of thought, and rejected payloads.
- Required stages have one attributable span only when the stage occurred; correlation/causation and version bundle are preserved.
- Export idempotency prevents duplicate spans after uncertain acknowledgement; buffer overflow fails new work closed.
- LangSmith and operational telemetry outage do not corrupt business state; Gate cannot close while export remains pending.
- Critical-path interval union, not naive child-span sum, reconciles root duration to independent wall time.

## Pass criteria

- Missing required spans, cross-run contamination, canary hits, rejected-payload egress, and duplicate/lost replay spans: 0.
- Wall-time difference is at most `max(50 ms, 5%)` for every measured root.
- Every public evidence record resolves to candidate SHA, run ID, route/version bundle, artifact digest, and controlled private evidence reference.
- Pending/rejected unexplained production traces at candidate completion: 0; LangSmith usage: at most 1,500 base traces.

## Evidence contract

LangSmith is applicable and blocking. Its key, raw traces, prompts, identifiers, and private failure payloads remain outside Git. Public artifacts contain sanitized schemas, aggregates, run IDs, digests, candidate SHA, and scanner outcomes only.
