# EVAL-G01-003 Plan — Platform Services and Operational Observability

## Purpose

Prove that all G01 data, identity, policy, artifact, vector, and operational observability services are reproducibly deployed, bounded, isolated, backed up, and supply-chain attributable.

## Candidate protocol

1. Deploy only digest-pinned candidate Charts into the frozen namespaces with project identities.
2. Wait for readiness convergence, then hold the required service set Ready for 15 minutes.
3. Execute identity/network/schema/object-prefix denial tests and authorized control cases.
4. Write a deterministic dataset, snapshot PostgreSQL, restore into a fresh target, and compare canonical digests.
5. Restart services, verify persistent recovery and telemetry ingestion, then generate SBOM/license/image provenance evidence.

## Blocking checks

- PostgreSQL, Redis, Qdrant, MinIO, Keycloak, OPA, OTel Collector, Prometheus, Loki, Tempo, and Grafana readiness.
- Least-privilege workload identities and denial of cross-schema, cross-prefix, unapproved network, and secret access.
- PVC/storage-class behavior, backup retention, restore runbook, resource requests/limits, and disk-pressure alerts.
- Metric, log, and trace control signals correlate without placing secrets in labels or logs.
- Every image resolves to a digest and passes the frozen license/vulnerability policy.

## Pass criteria

- Required workloads remain Ready for 15 minutes and recover after controlled restart.
- PostgreSQL restore digest equality: exact.
- Unauthorized network, secret, schema, object-prefix, or observability access: 0.
- Floating image tags, missing SBOM components, and incompatible licenses: 0.

## Evidence contract

Public evidence records synthetic identities, sanitized service/version/resource facts, aggregate readiness, restore digest, and candidate SHA. Raw database, IdP, object-store, and cluster credentials remain private.
