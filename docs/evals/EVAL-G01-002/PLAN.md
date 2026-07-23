# EVAL-G01-002 Plan — K3s, GPU and Isolated Runtime Foundation

## Purpose

Prove that a pinned single-node K3s foundation, network policy, snapshots, gVisor, Kata, and NVIDIA runtime can coexist with the host's existing Docker workloads without public exposure or undocumented mutation.

## Candidate protocol

1. Require passing EVAL-G01-001 and capture the signed pre-bootstrap Docker/host baseline.
2. Apply only candidate-pinned installers and manifests through the project identity.
3. Record exact versions, checksums, routes, listeners, resource reservations, RuntimeClasses, and snapshot settings.
4. Run allow/deny, RuntimeClass, GPU, snapshot/restore, reboot/recovery, and rollback dry-run cases.
5. Recollect the Docker baseline and compare containers, IDs where stability is expected, ports, networks, restart counts, and health.

## Blocking checks

- K3s compatibility preflight for kernel 5.15 and cgroup v1; unsupported combinations stop before installation.
- Traefik and ServiceLB absent; cluster services are `ClusterIP`; Kubernetes administration is not publicly reachable.
- Pod/service CIDRs do not overlap Docker; default-deny policy blocks unapproved namespace and internet flows.
- Real unprivileged runc, gVisor, and Kata pods and a separate RTX 4090 workload complete expected computation.
- Project rollback targets resolve under explicit project-owned paths and do not enumerate or modify Docker resources.

## Pass criteria

- Existing Docker stop/recreate/port/network/health regression: 0.
- Unexpected public listener: 0; NetworkPolicy allow/deny matrix: 100% expected.
- runc, gVisor, Kata, GPU, etcd snapshot, and restore cases: all pass.
- Clean rerun is idempotent and rollback verification reproduces the original Docker baseline.

## Evidence contract

Public artifacts contain sanitized topology, versions, test matrices, digests, and candidate SHA. Kubeconfig, server identity, IP, raw logs, and secrets remain private. LangSmith remains required Gate-wide but is not runtime evidence for this infrastructure Eval.
