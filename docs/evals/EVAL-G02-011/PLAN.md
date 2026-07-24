# EVAL-G02-011 Plan — Bounded Remote Transport Corrective

## Purpose

只执行 I-0026 的本地确定性验证。证明 oversized privileged script 不进入 Windows child
process command line，脚本和 sudo credential 分离传输，远端临时文件在 pass/failure 后均被
清理，且 G02 collector interface 保持 candidate/environment binding 与冻结失败分类。

## Frozen ownership

- V-G02-009 Iteration N=4。
- V-G02-010 Iteration N=0。
- V-G02-011 Iteration N=4。
- Gate L2、远程部署、破坏性 scenario、external service 与 model call 均为 0。

## Pass criteria

- 大于 Windows 安全命令行预算的 fixture 仍使每个 child-process command 保持固定小尺寸。
- 上传内容与原脚本逐字节一致，sudo stdin 只包含 credential，清理对所有终态执行。
- 受影响的 collector/readiness tests 全部通过，`open_evidence: []`。
