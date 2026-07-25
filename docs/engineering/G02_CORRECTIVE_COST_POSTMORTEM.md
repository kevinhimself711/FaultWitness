# G02 Corrective Cost Postmortem

## 结论

G02 corrective 成本过高是真实治理缺陷，不是 Gate 指标本身过高。Master Plan 对外部 seam
readiness 的证明设计不足，而 lifecycle 又把 corrective、Gate attempt 和全局同步捆绑，导致
微小修复承担数倍于实现本身的流程成本。

## 可核算证据

| Work | Commit role | Files touched | Changed lines |
| --- | --- | ---: | ---: |
| I-0034 | plan corrective | 24 | 408 |
| I-0034 | activate | 7 | 30 |
| I-0034 | implementation candidate | 4 | 198 |
| I-0034 | evidence | 3 | 131 |
| I-0034 | close | 11 | 74 |
| Legacy I-0036 | plan before implementation | 24 | 393 |
| Legacy I-0036 | activate before implementation | 7 | 33 |

I-0034 一个 corrective 因而使用 5 个 commit 和累计 49 次文件触碰。Legacy I-0036 在一行
client command 尚未修改前已经使用 31 次文件触碰。这不是可接受的 corrective 比例。

## 根因

1. `I-####` 同时表示 frozen work、corrective 和 Gate attempt，新增成本被伪装成正常计划。
2. I-0018/I-0024 用 memory backend 验证 matrix shape，却没有对真实 MinIO client operation
   做最小 semantic conformance proof；完整 Gate Eval 成为第一次真实集成测试。
3. 每次失败都创建一对 corrective/replacement Iteration，并重定向 Master Plan、VALIDATIONS、
   Claims、Gate Report 与多个状态镜像。
4. 小修复新增专用 Iteration evaluator；I-0036 草案中一条命令修复曾对应约 120 行 evaluator，
   再次接近 G01 最终审计现场造 harness 的反模式。
5. 诊断缺少复用的最小观测路径；EVAL-G02-020 后 8 次诊断中有 5 次是诊断命令构造错误。
6. 成本核算把 corrective engineering、Gate execution 和 governance synchronization 合并，
   无法看见真实倍率。

## Master Plan 与 Gate N 判断

Master Plan 的 seam-readiness 划分质量较差：它正确地把完整 live matrix 放到 L2，却错误地
把所有真实 client/platform semantics 也推迟到 L2。最小真实 seam proof 应属于 owning work
的 bootstrap/compatibility evidence，不需要运行完整 Gate N。

目前没有证据表明冻结 Gate N 是 corrective 成本根因。失败候选尚未进入 60-cell matrix 的
第 26 个 cell，6-stage、22-surface、32-scenario 与 192 live model trials 均未执行，模型调用
为 0。因而本次不降低任何 N 或指标；若未来完整 phase 的实际数据证明 N 成本不合理，必须
单独提出 metric-design amendment，不能借 corrective 偷降。

## 固化措施

- ADR-0014 与 AMD-0005 分离 I/C/A namespace。
- `work-item-lifecycle-v2.yaml` 机器拒绝 C 中的 full Gate Eval、Gate L2、bespoke harness 与
  全局 Gate 资产；机器拒绝 A 中的实现路径或行为/阈值变化。
- C record 必须登记单一 root cause、受影响 validation、变化分支和 real-seam 要求。
- 外部 seam 变化在 C 关闭前做最小真实 proof；完整规模与统计一致性只在 A 执行。
- 四类成本分别报告，不再把 A execution 或 closure synchronization 计入 C。
- 后续计划内 I 必须为每个 external seam 登记 real runner、只读 diagnostic 与 artifact；
  memory/mock-only readiness 被机器拒绝。
- A 只能调用冻结诊断入口，禁止现场造工具；失败 artifact 必须披露 invocation 与
  command-construction error 数量，避免把无效诊断隐藏进“debug 时间”。

这些规则控制实施路径和成本归属，不改变任何 Eval N、指标、阈值或性能裁决。若将来完整
phase 的真实执行数据证明某个 N 本身成本异常，必须另立 metric-design amendment；不能在
corrective 中修改。
