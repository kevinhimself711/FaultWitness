# EVAL-G02-017 Report

Result: `pass`.

Candidate `fc167c8bc98021cb4718ec6ab254c2525441326c` passed all three frozen I-0032
local deterministic cases. The offline archive inventory now contains the five existing Docker Hub
SUT images plus exactly these two probe images:

- `probe-busybox` → `docker.io/rancher/mirrored-library-busybox@sha256:101b4afd76732482eff9b95cae5f94bcf295e521fbec4e01b69c5421f3f3f3e5`
- `probe-minio-mc` → `docker.io/minio/mc@sha256:eb4ea9884b77704230e2423e9004d2fa738dc272876b9cc41a297d29443b8780`

The existing 30-image SUT image-set digest remains
`3df502956e9c4ab2311501a9e867a40bdc1afae79ebcf3de284a95611e52610e`.
`index.docker.io` normalization preserved repository and digest, an equivalent normalized reference
was deduplicated, and a same-repository digest change failed closed.

## Frozen validation ownership

- The corrective proof was exactly three local deterministic cases.
- V-G02-009 Iteration N remained exactly 4 identity policies.
- V-G02-010 Iteration N remained 0.
- V-G02-011 Iteration N remained exactly 4 writer paths.
- V-G02-017 Iteration N remained 0.
- Gate L2 execution, private-server command execution, destructive scenario, external-service call,
  and model call were all 0.

The affected 28 tests passed; `verify-fast` passed 344 tests and all Markdown checks; and
`eval-changed` validated the four implementation-candidate paths. No image reference or digest,
validation N, threshold, Ground Truth, locked test, health window, model route, token/cost ceiling,
or Gate failure semantic changed. `open_evidence: []`.
