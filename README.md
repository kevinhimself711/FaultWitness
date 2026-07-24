---
active_gate: G02
active_gate_status: in_progress
active_iteration: I-0018
next_iteration: I-0019
last_closed_gate: G01
---

# FaultWitness

FaultWitness 是一个面向微服务事故调查、受控修复与持续优化的多租户 Agent Runtime 项目。

当前状态：G00、G01 已关闭；G02 正在执行，当前唯一 active Iteration 为 I-0018，下一
Iteration 为 I-0019。I-0017 已在统一候选上通过故障实验室 Eval，且没有 open evidence。

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
- I-0018 仅允许实现 locked-test/ground-truth 隔离、160 行预登记以及冻结的
  access/canary/span runners；不得物化 160 个 case，不得调用付费模型。
- I-0019 在 I-0018 关闭并由项目所有者复核隔离证据前保持 inactive。

代码、API、Schema 和标识符使用英文；设计、评测和复盘文档以中文为主。
