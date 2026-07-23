---
active_gate: G02
active_gate_status: in_progress
active_iteration: I-0017
next_iteration: I-0018
last_closed_gate: G01
---

# FaultWitness

FaultWitness 是一个面向微服务事故调查、受控修复与持续优化的多租户 Agent Runtime 项目。

当前状态：G00、G01 已关闭；G02 正在执行，当前唯一 active Iteration 为 I-0017，下一
Iteration 为 I-0018。仓库已经具备
G01 证明的平台、契约、持久化、认证 API、Trace、Model Gateway 与恢复地基，但尚未
实现或声称 G02 故障实验室、G03 只读 Agent 纵切及后续能力。

## 权威资产

- [最终项目规划](docs/blueprint/FINAL_PLAN.md)
- [G01 Gate Report](docs/gates/G01/REPORT.md)
- [G02 Master Plan](docs/gates/G02/PLAN.md)
- [阶段索引](docs/roadmap/PHASES.md)
- [项目状态](PROJECT_STATE.yaml)
- [协作规则](AGENTS.md)
- [AI 开发与复盘日志](docs/engineering/AI_DEVELOPMENT_LOG.md)

## 当前边界

- 不把 G01 平台地基包装为已经完成的 Agent 产品。
- 不提交原始 JD、面经、密钥、私有 Trace 或受限数据。
- I-0017 仅实现冻结的故障实验室、Scenario DSL、32 个种子、oracle、恢复和 clean-clone
  runner；不授权 locked-test/ground-truth 身份、160 case 物化、基线或付费模型调用。
- 下一步是完成并关闭 I-0017，不得跳到后续 Iteration 或最终 Gate Eval。

代码、API、Schema 和标识符使用英文；设计、评测和复盘文档以中文为主。
