# Platform services runbook

Deploy and inspect the private ClusterIP-only platform with:

```powershell
uv run python -m faultwitness_dev deploy-platform
uv run python -m faultwitness_dev inspect-platform --stability-seconds 900
```

The CLI records the current producer commit, actual chart/values digest, and dirty/clean fact. A
dirty targeted debug is allowed and cannot collide with a clean build because content digest is
recorded separately. Inspection reads observed workloads and images from Kubernetes; it does not
compare the repository HEAD or require a binding ConfigMap.

Secrets remain outside Helm. All workloads remain private, digest-pinned, resource-bounded, and
covered by their existing health, persistence, isolation, backup/restore, and publication checks.
The 900-second stability observation is an Eval oracle window, not an orchestration kill.

Deploy and inspection have no preset wall-clock termination. On a deterministic failure, preserve
the diagnostic artifact, fix the existing path, and replay only the affected operation.
