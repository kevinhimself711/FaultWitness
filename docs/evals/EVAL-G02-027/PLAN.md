# EVAL-G02-027 Plan — Baseline LangSmith TCP Egress Probe Corrective

## Purpose

Falsify the client-abstraction hypothesis on the exact existing baseline and denied probe pods,
then—only if confirmed—verify the minimal external LangSmith network-probe change through the
existing collector test entrypoint and a real candidate-bound TCP seam proof.

## Frozen checks

- Same-pod transport check confirms baseline TCP/443 allow and the two frozen policy rejects.
- Existing pytest covers the changed allow/reject command and classification branches.
- The final real seam artifact contains candidate/environment binding, sanitized outcomes, and no
  credential, response body, secret, or private reasoning.
- Gate L2, full 60-cell execution, deployment, destructive phases, Bailian, tokens, and cost remain
  zero; `open_evidence: []` is required.

No validation N, permission, quality/performance threshold, model route, token/cost ceiling, or
failure semantic changes. Elapsed estimates are not kill timeouts.
