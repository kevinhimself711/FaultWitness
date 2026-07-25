# EVAL-G02-019 Plan — Containerd Imported-Reference Alias Resolution Corrective

## Purpose

只执行 I-0034 的本地 deterministic source-resolution proof。resolver 只接受
`docker.io`/`index.docker.io` host alias、同一 repository 与 exact expected digest；不得连接
私有服务器或运行 Gate L2。

## Frozen cases

1. requested source reference 与 expected digest 精确存在时直接选择。
2. 仅等价 host alias reference 存在且 digest 精确时选择 alias 并生成 target tag/verify。
3. alias repository 存在但 digest 错误时 fail closed，不能用名称匹配冒充 digest 匹配。

V-G02-017 Iteration N 保持 0；V-G02-009/010/011 Iteration N 保持 4/0/4。remote、Gate L2、
部署、破坏性、external service 与 model call 均为 0。

## Pass criteria

- 三个 local cases 全部通过，source resolution 仅扩大 host alias 而不扩大 repository/digest。
- 冻结 probe/SUT image references、30-image SUT digest 与 Gate failure semantics 不变。
- 受影响 tests、`verify-fast` 与 `eval-changed` 通过，`open_evidence: []`。
