# Secure bootstrap runbook

Bootstrap keeps the existing SOPS/Age store, accepted host pin, dedicated SSH key, and private
credential material outside the repository. Use the active commands shown by
`uv run python -m faultwitness_dev --help`; none requires an operator-supplied candidate SHA.

`probe-host` automatically records the current producer commit and writes only the sanitized
capability report to the requested path. SSH connect deadlines are protocol-level deadlines. Once
the user authorizes the private environment for the active task, do not request the same authority
again. A deterministic credential, interpreter, or byte-transport failure must be fixed before
retry; a classified transient failure resumes the same journal.

Never expose a password, API key, host locator, private path, reversible fingerprint, or raw remote
output. Finalization removes the plaintext handoff only after encrypted round-trip, host pin, key,
credential acceptance, and login evidence pass.
