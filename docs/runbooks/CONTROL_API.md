# Control API runbook

```powershell
uv run python -m faultwitness_dev deploy-runtime-schema
uv run python -m faultwitness_dev deploy-control-api
uv run python -m faultwitness_dev inspect-control-api
uv run python -m faultwitness_dev provision-keycloak-realm
uv run python -m faultwitness_dev inspect-keycloak-realm
uv run python -m faultwitness_dev smoke-control-api
```

The image tag includes producer commit and the actual build-context digest. Deployment annotations
record both; inspection and smoke use the observed workload image. Documentation or governance
commits do not invalidate the deployment, and no binding ConfigMap or HEAD comparison is involved.

PostgreSQL and OIDC still fail closed. Tenant identity comes only from the authenticated principal;
body/header overrides, cross-tenant reads, false approvals, stale versions, invalid tokens, and
same-key/different-payload requests retain their frozen denial semantics. HTTP connect/read
deadlines remain protocol-level safety boundaries; the surrounding deployment and smoke runner has
no preset wall-clock kill.
