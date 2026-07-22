---
document_id: FW-GATE-G01-PLAN
gate: G01
status: not_started
---

# G01 Gate Plan Placeholder

## Current status

G01 尚未启动，本文件不是冻结的 Gate Master Plan。任何实现 Iteration 开始前，必须先基于 [Final Plan](../../blueprint/FINAL_PLAN.md)、[G00 Report](../G00/REPORT.md) 和 [repository instructions](../../../AGENTS.md) 形成 decision-complete G01 Master Plan，并通过独立 planning commit 固化。

## Inherited boundary

G01 继承 G00 已冻结的四层状态所有权、TenantContext 来源、Agent 与 Action Executor 边界、R2 审批、至少一次投递与幂等、`UNCERTAIN`/`MANUAL`、Ground Truth 隔离和公共契约路径。修改这些不变量必须先提交 ADR、迁移与 replay 分析以及针对性回归。

## Authoritative target

根据 Final Plan，G01 面向平台、契约与 Trace 地基：K3s 基础服务、Pydantic contract、状态转换服务、checkpoint、transactional outbox、ModelGateway、LangSmith instrumentation、sandbox/accelerator capability report。具体 Iteration、参数、依赖和 Gate 阈值尚待规划冻结。

## Start condition

- G01 Gate Master Plan 状态变为 `frozen`。
- `PROJECT_STATE.yaml` 指向首个已物化的 G01 Iteration。
- 每个 Iteration 具有实现范围、非目标、测试、Eval 和通过标准。

在满足以上条件前，不得开始 G01 产品实现。
