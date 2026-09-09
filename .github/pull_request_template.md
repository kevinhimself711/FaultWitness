## Semantic change

- Observable behavior or invariant:
- Gate scope, when applicable: `G__`

## Boundaries

- [ ] The change stays inside the frozen Gate scope and non-goals when a Gate is active.
- [ ] No locked test or ground-truth asset was modified.
- [ ] No Gate threshold was lowered.

## Verification

- [ ] `make verify-fast`
- [ ] Targeted tests and, when applicable, one real external-seam proof
- [ ] Only affected trials and dependencies were replayed
- [ ] Security, tenant, approval, uncertainty, and publication boundaries reviewed

## Experiment evidence, when applicable

- [ ] Trial journals record execution attempts separately from document versions.
- [ ] Runtime evidence records producer and subject digests without binding to governance HEAD.
