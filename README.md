---
active_gate: G02
active_gate_status: in_progress
active_iteration: null
next_iteration: I-0027
last_closed_gate: G01
---

# FaultWitness

FaultWitness 是一个面向微服务事故调查、受控修复与持续优化的多租户 Agent Runtime 项目。

当前状态：G00、G01 已关闭；G02 正在执行。I-0020、I-0023 与 I-0025 均已因确定性失败
终态关闭且负面证据完整；I-0024 与 I-0026 已完成 candidate-bound collector 和 bounded
remote transport 前向纠错。I-0027 是下一项替代统一候选编排。任何终态记录都不会重开。

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
- I-0018 已交付 locked-test/ground-truth 隔离、160 行预登记和三个验证接口；I-0024
  已前向补齐并单测 EVAL-G02-008 证明缺失的 candidate-bound provisioner/collector。
- EVAL-G02-010 在首个访问 cell 前证明 Windows command-line transport 缺陷；没有执行
  Gate matrix cell、破坏性实验或模型。I-0026 已以本地证据关闭；I-0027 只编排冻结 phase。

代码、API、Schema 和标识符使用英文；设计、评测和复盘文档以中文为主。
