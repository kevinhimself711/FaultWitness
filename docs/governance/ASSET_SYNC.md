# Evidence Asset Synchronization

## Purpose

FaultWitness separates implementation from evidence finalization without rewriting history. An
Iteration candidate is immutable once candidate evaluation begins. The producing runner writes the
evaluated revision and artifact digests during the real run; URLs, job IDs, sanitized summaries, and
lifecycle records discovered afterward are added only through an evidence-only synchronization
commit.

## Protocol

1. Complete implementation, tests, documentation, and preliminary Eval assets in one candidate commit.
2. Freeze and pass the full `candidate_sha` explicitly to every candidate-bound runner. Do not infer
   it from the newest commit after the freeze.
3. Do not amend or force-push a candidate after evaluation starts; a functional correction creates
   a new candidate SHA and reruns the phases invalidated by the frozen dependency/cache protocol.
4. The real producing run writes `evaluated_revision`, result, timestamps, and artifact digests. In
   a separate asset-only change, synchronize the Iteration `commit`, evidence URLs, Claims,
   Changelog, and project state. Evidence sync may not edit `evaluated_revision`.
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

Current HEAD is not a third identity. A checkout at `candidate_sha` is valid, and a checkout at an
allowlisted evidence-only descendant is valid when ancestry, every intervening path, and all subject
digests are verified. The latter must not redeploy or rerun solely because HEAD differs from the
business candidate.

No tracked binding, manifest, report, or closure asset is required to contain the SHA of the commit
that contains itself. It records the execution checkpoint that existed before the artifact was
produced. The identity of the subsequent evidence/closure commit is supplied by Git ancestry and the
Gate tag, not by a self-referential content rewrite.

Completed Iterations remain completed. A post-completion defect creates a new forward corrective
Iteration with a link to the affected Iteration and evidence. It may block later work, but lifecycle
state never moves backward and the historical record is not reopened.

These identity rules are provenance controls. They never change sample sizes, locked tests, Ground
Truth, quality/performance thresholds, health windows, token/cost ceilings, or pass/fail semantics.

## Failure handling

Failed candidates, negative experiments, and superseded reports remain in Git history. A defect in
a completed Iteration creates a new forward corrective Iteration for that owning domain; it does not
reopen or rewrite the completed record. If an active Gate orchestration requires implementation,
policy, zero-tolerance, metric, quality, or performance correction, that orchestration becomes an
immutable failed record. After the corrective closes, create a new orchestration Iteration for the
new candidate. It reuses only exact-key or expressly inherited evidence allowed by the frozen
protocol and executes every invalidated phase. Transient infrastructure failure resumes the current
phase/trial, and pure synchronization of already-existing evidence remains asset-only. Never lower a
threshold or modify locked evidence to manufacture a pass.
