---
document_id: FW-ROADMAP-001
version: 1.1.0
status: planned
---

# Gate Roadmap

| Gate | 主题 | 状态 | 权威计划 |
|---|---|---|---|
| G00 | 蓝图、架构与治理基线 | Passed | ../gates/G00/PLAN.md |
| G01 | 平台、契约与 Trace 地基 | Planned — plan frozen | ../gates/G01/PLAN.md |
| G02 | 故障实验室与基线 | Not started | 待 G01 关闭后规划 |
| G03 | 只读 Agent 纵切 | Not started | 待 G02 关闭后规划 |
| G04 | RAG、Memory、Skills 与多模态 | Not started | 待 G03 关闭后规划 |
| G05 | 受控修复与动作事务 | Not started | 待 G04 关闭后规划 |
| G06 | 多租户 Runtime、调度与沙箱 | Not started | 待 G05 关闭后规划 |
| G07 | 完整评测、数据飞轮与泛化 | Not started | 待 G06 关闭后规划 |
| G08 | 模型、架构和性能消融 | Not started | 待 G07 关闭后规划 |
| G09 | 训练就绪与三条 Smoke Pipeline | Not started | 待 G08 关闭后规划 |
| G10 | 发布、Dogfooding 与面试资产 | Not started | 待 G09 关闭后规划 |

## 推进规则

- 日期不是推进依据，前一 Gate 的关闭标签才是。
- 每个 Gate 在实施前必须先通过 Plan Mode 形成 Master Plan。
- Master Plan 固化为 planning commit 后才能建立 Iteration。
- 下一 Gate 可以调研，但不得在前一 Gate 关闭前提交其产品实现。
- 实验结果为负可以通过 Gate，前提是实验预注册、执行完整、结论真实。
- 安全、审批、租户隔离、Ground Truth 和 locked-test 泄漏指标不得豁免。
