# EVAL-G02-015 Plan — Python 3.8 Probe Compatibility Corrective

## Purpose

只执行 I-0030 的本地 deterministic compatibility proof。冻结 probe 必须由实际 managed
Python 3.8 import，并执行 UTC-aware timestamp path；不得连接私有服务器或运行 Gate L2。

## Frozen ownership

- V-G02-009 Iteration N=4。
- V-G02-010 Iteration N=0。
- V-G02-011 Iteration N=4。
- remote provisioning、Gate L2、破坏性、external service 与 model call 均为 0。

## Pass criteria

- actual Python 3.8 import 与 UTC timestamp 两个 cases 均通过。
- timestamp 保持 UTC-aware `+00:00`；source 不再从 `datetime` 导入 `UTC`。
- 受影响 tests 全部通过，`open_evidence: []`。
