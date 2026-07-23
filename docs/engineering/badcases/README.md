# Process Badcases

该命名空间只记录 AI 协作开发、Gate 治理和 Eval 执行流程的可复现缺陷，使用
`BC-PROC-*` 标识。它与未来面向产品的 incident case、Scenario DSL、Agent trajectory、
训练样本和 locked Eval case 严格分离；过程 badcase 不得进入产品质量分母，也不能
作为修改 Ground Truth 的依据。

| ID | 主题 | 当前状态 |
| --- | --- | --- |
| [BC-PROC-0001](BC-PROC-0001.md) | 900 秒后才暴露 manifest debt | 规则已接受，工装待实现 |
| [BC-PROC-0002](BC-PROC-0002.md) | 单 SHA 导致证据级联失效 | ADR 已接受，工装待实现 |
| [BC-PROC-0003](BC-PROC-0003.md) | 稳定窗口被重复执行 | 规则已接受，工装待实现 |
| [BC-PROC-0004](BC-PROC-0004.md) | generic transport error 无阶段归因 | pass 分支已移除 |
| [BC-PROC-0005](BC-PROC-0005.md) | 36 次模型矩阵全有或全无 | 规则已接受，工装待实现 |
| [BC-PROC-0006](BC-PROC-0006.md) | Gate handoff 占位资产偏离权威路线 | 当前漂移已修正 |
