# EVAL-G02-017 Plan — Digest-Pinned Probe Image Offline Staging Corrective

## Purpose

只执行 I-0032 的本地 deterministic staging proof。冻结 inventory 必须从现有 SUT image
registry 与 `config/g02/gate-probes.yaml` 合并恰好两个 probe images，并复用同一 OCI
archive、verified transfer、containerd import 与 digest-verification contract；不得连接私有
服务器或运行 Gate L2。

## Frozen cases

1. 合并 inventory 恰好包含 `busybox` 与 `minio_mc` 两项固定 probe images。
2. `docker.io` 与 `index.docker.io` reference normalization 保持 exact digest。
3. 重复 reference 被去重，archive/import inventory 无 floating tag 或 digest drift。

V-G02-017 Iteration N 保持 0；V-G02-009/010/011 Iteration N 保持 4/0/4。remote、Gate L2、
破坏性、external service 与 model call 均为 0。

## Pass criteria

- 三个 local cases 全部通过，两个 probe image digest 与冻结配置完全一致。
- 现有 30-image SUT image-set digest 不变，Gate bootstrap 不依赖节点直接 registry pull。
- 受影响 tests、`verify-fast` 与 `eval-changed` 通过，`open_evidence: []`。
