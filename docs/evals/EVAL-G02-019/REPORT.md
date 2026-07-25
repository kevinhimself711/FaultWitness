# EVAL-G02-019 Report

Result: `pass`.

Candidate `1f366dc8bbe0e71611367b87ed72fb4e70db69cd` passed all three frozen I-0034
local deterministic cases:

1. An exact requested source with the expected content digest was selected first.
2. An alias-only `index.docker.io` source with the exact expected digest was selected for the frozen
   `docker.io` target.
3. A repository alias carrying the wrong digest failed closed.

The resolver expands only the two Docker Hub host aliases; it does not expand repository or digest
matching. The frozen 30-image SUT image-set digest remains
`3df502956e9c4ab2311501a9e867a40bdc1afae79ebcf3de284a95611e52610e`.

## Frozen validation ownership

- The corrective proof was exactly three local deterministic cases.
- V-G02-009 Iteration N remained exactly 4 identity policies.
- V-G02-010 Iteration N remained 0.
- V-G02-011 Iteration N remained exactly 4 writer paths.
- V-G02-017 Iteration N remained 0.
- Gate L2 execution, private-server command execution, deployment, destructive scenario,
  external-service call, and model call were all 0.

The affected 22 tests passed; `verify-fast` passed 347 tests and all Markdown checks; and
`eval-changed` validated the four implementation-candidate paths. No image reference or digest,
validation N, threshold, Ground Truth, locked test, health window, model route, token/cost ceiling,
or Gate failure semantic changed. `open_evidence: []`.
