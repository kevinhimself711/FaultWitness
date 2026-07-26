---
active_gate: G03
active_gate_status: not_started
active_iteration: null
next_iteration: null
last_closed_gate: G02
---

# FaultWitness

FaultWitness 是一个面向微服务事故调查、受控修复与持续优化的多租户 Agent Runtime 项目。

当前状态：G00、G01、G02 已无豁免关闭。G02 在 EVAL-G02-046 中完成 14 个 phase、32 个可执行
故障场景、60/6/22 安全与可观测性矩阵、N=32 deterministic baseline、N=192 live baseline、
95% clustered bootstrap CI、reconciliation 与 close-readiness，`open_evidence=0`。

G03“只读 Agent 纵切”尚未开始。当前占位资产只授权制定 decision-complete Master Plan；在该计划
冻结前，不实施 G03 产品代码、基础设施变更或 live evaluation。

## 权威资产

- [最终项目规划](docs/blueprint/FINAL_PLAN.md)
- [G02 Gate Report](docs/gates/G02/REPORT.md)
- [G03 占位计划](docs/gates/G03/PLAN.md)
- [阶段索引](docs/roadmap/PHASES.md)
- [项目状态](PROJECT_STATE.yaml)
- [协作规则](AGENTS.md)

## 边界

- G02 只交付 32 个种子场景和 160 行 metadata-only 预登记；160 case 的实际物化仍属于 G07。
- G02 baseline 是对照测量，不声称 Naive ReAct 或 no-RAG 达到未来 Agent 的冻结质量下限。
- Ground Truth 与 locked tests 保持对 Agent runtime 不可访问。
- 不提交原始 JD、面经、密钥、私有 Trace、模型私有推理或受限数据。
