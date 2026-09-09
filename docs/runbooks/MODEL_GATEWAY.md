# Model Gateway runbook

```powershell
uv run python -m faultwitness_dev deploy-model-gateway
uv run python -m faultwitness_dev inspect-model-gateway
uv run python -m faultwitness_dev smoke-model-gateway
```

The image is keyed by actual build-context digest and annotated with producer provenance.
Inspection and smoke use the deployed image, not repository HEAD or a candidate ConfigMap. Model
catalog, route, token/cost, fallback, schema, and attribution rules are unchanged. A transport
failure remains retryable in the same trial journal; unsupported or malformed output fails closed.
