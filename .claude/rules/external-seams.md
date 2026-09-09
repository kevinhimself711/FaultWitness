---
paths: ["deploy/**", "tools/**", "config/**"]
---

## External seams

- Before a Gate-scale live run, execute every new client/platform/credential/image/interpreter/
  protocol operation once in the target environment. Mocks and schema checks prove shape only.
- Use explicit bytes and decoding for subprocess, SSH, credential, script, and structured stdin
  transport. Cross-platform claims require a real child-process byte comparison.
- Journal side-effect checkpoints before later relay, collection, or aggregation can fail.
  Deterministic identities must bind deterministic payloads or persist a nonce before side effects.
- Repeated environment attempts have no numeric or time ceiling, but a known deterministic cause
  must be fixed before retry. Unchanged retry is reserved for classified transient infrastructure.
