# Observability runbook

```powershell
uv run python -m faultwitness_dev deploy-trace-service
uv run python -m faultwitness_dev inspect-trace-service
uv run python -m faultwitness_dev smoke-trace-service
```

The deployed image and annotations expose producer and source digests. Inspection and relay read the
actual workload and private service state; they do not require a candidate-binding ConfigMap. The
operator relay journals claim/retry/ack semantics and preserves stable remote identity after an
uncertain acknowledgement.

Sanitization, six-stage correlation, bounded product buffers, Secret/PII rejection, and zero lost or
duplicate delivery semantics are unchanged. HTTP deadlines and buffer/oracle limits remain product
semantics. The outer deployment, smoke, and relay loops have no preset wall-clock termination.
