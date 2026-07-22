## Iteration

- Iteration: `I-____`
- Gate: `G__`
- Candidate SHA: filled after commit

## Scope and evidence

- [ ] The change stays inside the frozen Iteration scope and non-goals.
- [ ] Behavioral changes include tests and documentation in the same commit.
- [ ] Requirement, Claim, Eval, Changelog, and project-state assets are updated as applicable.
- [ ] No locked test or ground-truth asset was modified.
- [ ] No Gate threshold was lowered.

## Verification

- [ ] `make verify-fast`
- [ ] `make eval-changed`
- [ ] Iteration-specific Eval commands
- [ ] Security, tenant, approval, uncertainty, and publication boundaries reviewed

## Asset sync

- [ ] Cross-platform CI evidence is recorded after the candidate commit.
- [ ] Evidence-only synchronization contains no implementation or threshold change.
