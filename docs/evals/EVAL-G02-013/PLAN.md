# EVAL-G02-013 Plan — Byte-Exact Remote Process Transport Corrective

## Purpose

只执行 I-0028 的本地确定性验证。真实 Windows subprocess 必须收到 byte-exact LF 输入；
privileged script 与 sudo credential 保持分离，child-process arguments 保持有界，所有终态
继续执行 cleanup 或 fail closed。

## Frozen ownership

- V-G02-009 Iteration N=4。
- V-G02-010 Iteration N=0。
- V-G02-011 Iteration N=4。
- Gate L2、远程部署、破坏性 scenario、external service 与 model call 均为 0。

## Pass criteria

- 真实 child process 的 stdin hex 与调用方 UTF-8 hex 完全一致且无 `0d0a`。
- 四个 transport cases 全部通过；无 timeout、operator adjudication 或指标变化。
- 受影响 tests 全部通过，`open_evidence: []`。
