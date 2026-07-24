---
active_gate: G02
active_gate_status: in_progress
active_iteration: null
next_iteration: I-0022
last_closed_gate: G01
---

# FaultWitness

FaultWitness 是一个面向微服务事故调查、受控修复与持续优化的多租户 Agent Runtime 项目。

当前状态：G00、G01 已关闭；G02 正在执行。I-0020 因 V-G02-009 的确定性策略失败已终态
关闭且证据完整；I-0022 是下一前向纠错 Iteration，I-0023 是其后的替代统一候选编排。
两次 Iteration 之间当前没有 active Iteration，任何已终态记录都不会重开。

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
- I-0018 已交付 locked-test/ground-truth 隔离、160 行预登记以及冻结的
  access/canary/span runners，未物化 160 个 case，未调用模型。
- I-0019 在项目所有者确认前保持 planned/inactive。

代码、API、Schema 和标识符使用英文；设计、评测和复盘文档以中文为主。
