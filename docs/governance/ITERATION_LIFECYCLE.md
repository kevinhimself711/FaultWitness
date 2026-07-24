# Forward-Only Iteration Lifecycle

This file is the machine-detected policy epoch for forward-only Iteration history.

## Allowed transitions

- `planned -> in_progress`
- `planned -> failed`
- `in_progress -> completed`
- `in_progress -> failed`
- an unchanged status

`completed` and `failed` are immutable terminal audit states. A terminal record may not be deleted,
renamed, or changed to another status. A later defect creates a higher-numbered forward corrective
Iteration with an explicit `corrects` link. After that correction, a new orchestration Iteration
evaluates the new candidate; the earlier orchestration is not reactivated.

## Gate failure classification

- Candidate readiness is the deterministic front of Gate Eval. Passing it authorizes expensive
  phases but does not close the Gate.
- A classified transient infrastructure or transport failure resumes the same phase or atomic trial
  on the same candidate.
- A temporarily unavailable external prerequisite stops progress and later resumes the same
  candidate when no bound subject changed.
- An implementation, runner, fixture, policy, zero-tolerance, cleanup, metric, quality, or
  performance failure terminates that orchestration Iteration. It requires a forward corrective
  Iteration, a new candidate where behavior changed, and a new orchestration Iteration.
- A pure evidence synchronization may update only allowlisted evidence/status assets derived from
  already-existing artifacts. It may not alter `evaluated_revision`, thresholds, samples, failure
  classification, or runtime identity.

## Revalidation boundary

After correction, run the failed check and its affected dependency closure. Reuse exact-key or
explicitly inherited evidence only under the frozen digest protocol. Never rerun an unchanged
deterministic failure, repeat a destructive/soak phase for the same key, discard completed live
trials, or launch an open-ended extra readiness audit.
