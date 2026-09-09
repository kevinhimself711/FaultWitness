# Evidence and release synchronization

## Purpose

Evidence synchronization records what actually ran; it does not create a second implementation
identity or block the next experiment.

## Runtime evidence

Each trial or phase journal atomically records its producer commit, named runtime checkpoint
digests, configuration/data/model/environment facts, start/end timestamps, terminal status, and
artifact digests. `execution_attempt` changes only when work executes; `record_version` changes on
document updates.

Passed evidence remains valid while its explicit inputs and required checkpoints remain unchanged.
Reports, Claims, roadmap text, `PROJECT_STATE.yaml`, and other documentation do not participate in
cache identity.

## Gate closure

At closure, aggregate existing journals without re-executing them, write the Gate Report once, and
create one release manifest containing:

- one release commit SHA and the factual producer SHA(s);
- image, config, dataset, model, locked-test, Ground-Truth, and environment digests as applicable;
- result artifact paths and digests;
- the frozen metric sample sizes, thresholds with the measured reference values they resolved
  against, and the terminal verdict.

Advance `PROJECT_STATE.yaml` once at the Gate boundary and tag the release when explicitly
authorized. There is no candidate/evidence/governance multi-SHA protocol, evidence-only commit
allowlist, HEAD equality, lifecycle-front-matter synchronization, or self-referential revision
rewrite.

## Failure handling

Persist the failed journal, fix one root cause in the existing implementation/runner, prove the
changed seam, replay affected work only, and resume the same experiment. Failed evidence remains in
the journal or Git history. A new Gate Plan amendment is required only for new scope, metric,
threshold, or substantial framework—not for a minimal deterministic debug fix. Resolving a
threshold's pending reference value from the first run that passes the instrument-validity checks is
not a threshold change: the target's form and margin are unchanged. Correcting a reference value
already anchored to a demonstrated instrument defect does need an amendment, and that amendment
names the defect rather than the inconvenience.

The G00–G02 synchronization protocol remains available only at its Gate tags; see
[the legacy governance boundary](LEGACY_GOVERNANCE_EPOCH.md).
