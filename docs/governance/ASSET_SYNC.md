# Evidence Asset Synchronization

## Purpose

FaultWitness separates implementation from evidence finalization without rewriting history. An Iteration candidate is immutable once cross-platform evaluation begins; URLs, job IDs, and evaluated SHA values discovered afterward are added only through an evidence-only synchronization commit.

## Protocol

1. Complete implementation, tests, documentation, and preliminary Eval assets in one candidate commit.
2. Run the candidate through every required status check on the exact full SHA.
3. Do not amend or force-push a candidate after evaluation starts; a functional correction creates a new candidate SHA and reruns every required check.
4. In a separate asset-only change, set the Iteration `commit`, Eval `evaluated_revision`, result, evidence URLs, Claims, Changelog, and project state.
5. The evidence-only change may not alter source, tests, schemas, contracts, thresholds, lockfiles, or workflow behavior.
6. Merge the evidence sync through the same protected `main` workflow and preserve its CI URL in the Eval report.

## Gate closure

Gate closure is stricter than Iteration evidence sync. It evaluates one already-merged candidate SHA, produces the immutable Gate report, advances `PROJECT_STATE.yaml`, and creates a separate close commit and Gate tag. A closure commit may contain only governance and evidence assets and may not retroactively change the evaluated candidate.

From the G01 retrospective maintenance protocol onward, Gate closure uses a generated exact
allowlist for two consecutive Gates instead of a copied nine-path constant. The allowlist requires
`AGENTS.md`, `README.md`, `PROJECT_STATE.yaml`, `docs/roadmap/PHASES.md`, Changelog, ADR/Claim
indexes, the closing report, the next Gate placeholder plan/report, and both machine Gate records.
Source, tests, schemas, workflows, lockfiles, thresholds, and deployment assets remain forbidden.

`verify-fast` compares lifecycle front matter in the root/status Markdown surfaces with
`PROJECT_STATE.yaml`. Closure cannot pass while active Gate, Gate status, active Iteration, or last
closed Gate disagree.

## Candidate and evidence identities

ADR-0009 separates `candidate_sha`, which identifies evaluated behavior and runtime artifacts, from
`evidence_head_sha`, which identifies an allowlisted asset-only descendant. An evidence-only commit
does not retroactively rename the runtime candidate. Any behavior, test-semantic, evaluator,
threshold, workflow, dependency, deployment, dataset, or runtime-artifact change creates a new
candidate and invalidates the affected evidence.

## Failure handling

Failed candidates, negative experiments, and superseded reports remain in Git history. Fix the owning Iteration, produce a new candidate, and rerun the full Gate Eval; never lower a threshold or modify locked evidence to manufacture a pass.
