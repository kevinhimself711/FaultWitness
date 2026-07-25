# EVAL-G02-027 Report

Result: `pass`.

Candidate `44e4f48e361110e0e3bd763069601a503c482000` changes only the pod-side external
LangSmith network assertion from BusyBox HTTPS `wget` to transport-only `nc -z`. The operator-side
credential-authenticated read and the internal Prometheus, Loki, and Tempo HTTP checks are
unchanged.

Before implementation, the same existing probe pods confirmed the hypothesis: the baseline TCP/443
connect passed while the ordinary-developer and cross-boundary controls were rejected. The existing
pytest entrypoint then passed 4/4 cases on the corrective candidate: three changed allow/reject
branches and one unchanged internal-HTTP branch. The final real seam repeated the three transport
branches on the candidate; baseline passed and both frozen policy rejects remained denied.

Execution accounting is explicit: one capability preflight, one pre-change falsification, and one
candidate proof produced three successful remote invocations with zero command errors. Gate L2
cells, deployments, policy mutations, destructive operations, credential-authenticated requests,
model calls, tokens, and model cost were all zero. No credential, response body, Pod IP, or private
endpoint was persisted.

Reviewable evidence:
`docs/evals/EVAL-G02-027/artifacts/langsmith-tcp-egress-seam-proof.json`.
`open_evidence: []`.
