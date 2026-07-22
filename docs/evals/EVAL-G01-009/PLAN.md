# EVAL-G01-009 Plan — G01 Candidate Audit and Failure Matrix

## Purpose

Audit one immutable G01 candidate for cross-platform reproducibility, private-server deployment, contract/state reliability, authenticated API/SSE behavior, sanitized tracing, model compatibility, publication safety, and all fourteen frozen failure walkthroughs. Passing does not itself close G01.

## Candidate protocol

1. Create the I-0015 candidate commit, record its full SHA, and prohibit amend/force-push or behavior/threshold changes.
2. Require Windows and Ubuntu public verification/build/audit plus private-server clean-clone deployment for the same SHA and image digests.
3. Resolve EVAL-G01-001–008 evidence to that candidate or an explicitly replayed candidate-equivalent artifact set; stale evidence fails.
4. Execute all fourteen G01 walkthroughs, full supply-chain/publication audit, G00 regressions, migration/queue/trace reconciliation, and rollback rehearsal.
5. Run close-mode as a readiness test; it must reject incomplete evidence and must not change repository state or close the Gate.

## Frozen walkthroughs

1. Secret migration, rotation, deletion, and public-repository scan.
2. K3s coexistence with zero existing-Docker regression.
3. runc, gVisor, Kata, and RTX 4090 capability smoke.
4. Duplicate Incident creation returns the original result.
5. Database failure cannot partially commit state and Outbox.
6. Publisher/consumer crash and duplicate-delivery convergence.
7. Lease loss and crash before/after fenced checkpoint.
8. Invalid OIDC, Keycloak outage, role denial, and cross-tenant denial.
9. SSE reconnect, retention gap, future cursor, and slow consumer.
10. LangSmith outage, bounded buffer, idempotent replay, and drain.
11. Secret/PII/private-reasoning canaries rejected across every persistence/egress surface.
12. Qwen, DeepSeek, and GLM structured/tool/stream live capability.
13. Invalid model output, retry, repair, fallback, and partial-stream failure.
14. OPA outage fail-closed plus clean-clone deployment and project-only rollback.

## Blocking checks

- All nine Iterations are completed with immutable commits; all nine Eval manifests pass with no open evidence.
- Public CI and private server use one full SHA, digest-pinned images/Charts, compatible licenses, and zero secret/private-path finding.
- All frozen G00 contract/security regressions remain passing; threshold decreases and locked-test mutations are absent.
- State/Outbox/Inbox/DLQ/checkpoint/SSE/trace/model failure matrices meet their zero-tolerance and numeric thresholds.
- Candidate completion has no unexplained migration drift, queue backlog, DLQ, stale lease, trace buffer, waiver, or pending work.

## Pass criteria

- Required public/private checks and fourteen of fourteen walkthroughs pass for one candidate.
- Open evidence, waiver, P0/P1 finding, publication violation, secret/PII/private-reasoning leak, and pending production trace: 0.
- Model evidence retains the one-live-upstream limitation; single-node evidence retains the no-HA limitation.
- `eval-g01-close` accepts readiness and rejects every incomplete or extra-asset negative fixture without closing G01.

## Evidence contract

LangSmith is directly applicable and blocking. Public evidence stores only sanitized run IDs, summaries, digests, full candidate SHA, CI references, and controlled private evidence URLs. Gate closure is a later exact nine-asset commit and tag `gate/G01-v1`.
