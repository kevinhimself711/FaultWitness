# Private server platform environment

Install or reconcile the private ClusterIP-only platform release:

```sh
helm upgrade --install fw-platform deploy/charts/faultwitness-platform \
  --namespace fw-system --create-namespace \
  -f deploy/environments/private-server/values.yaml \
  --atomic --timeout 15m
```

Secrets are created outside Helm and referenced by stable names documented in
`values.yaml`. Never commit their values. Persistent services use bounded
`local-path` PVCs; PostgreSQL backup/restore is an explicit operator workflow,
not an in-cluster privileged CronJob. All services are private `ClusterIP`s.
