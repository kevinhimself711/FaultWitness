# EVAL-G02-045 Report

Result: `pass` on candidate `86a459c0bec1bcf3e583fd1280fbca2667479d2e`.

The first implementation candidate was replay-stable but retained the commit's `-04:00` offset;
the frozen strict `TraceEnvelope` contract accepts only UTC `+00:00`, so its first real submission
was rejected. The failure reproduced locally through the actual downstream parser and remained
inside the still-open corrective rather than creating another work item.

The final candidate normalizes the immutable commit timestamp to UTC in the controller and again in
the remote probe. Twenty-one collector tests, the 394-test repository suite, 250 Markdown files,
`verify-fast`, and `eval-changed` passed. The exact trace-service candidate deployed 1/1 Ready,
provisioning passed, and the same existing trace operation ran twice. Both invocations returned the
same trace ID and the same six observed stages; the second produced no payload conflict.

Access, canary, scenarios, baselines, Gate L2 phases, and model calls remained zero. No N, stage,
threshold, permission, health window, model route, token/cost ceiling, or failure meaning changed.
`open_evidence` is empty.
