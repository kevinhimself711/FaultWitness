---
document_id: FW-ROADMAP-001
version: 1.6.0
status: planned
active_gate: G03
active_gate_status: not_started
active_iteration: null
next_iteration: null
last_closed_gate: G02
---

# Gate Roadmap

| Gate | 主题 | 状态 | 权威计划 |
|---|---|---|---|
| G00 | 蓝图、架构与治理基线 | Passed | ../gates/G00/PLAN.md |
| G01 | 平台、契约与 Trace 地基 | Passed | ../gates/G01/PLAN.md |
| G02 | 故障实验室与基线 | Passed | ../gates/G02/PLAN.md |
| G03 | 只读 Agent 纵切 | Not started — placeholder only | ../gates/G03/PLAN.md |
| G04 | RAG、Memory、Skills 与多模态 | Not started | 待 G03 关闭后规划 |
| G05 | 受控修复与动作事务 | Not started | 待 G04 关闭后规划 |
| G06 | 多租户 Runtime、调度与沙箱 | Not started | 待 G05 关闭后规划 |
| G07 | 完整评测、数据飞轮与泛化 | Not started | 待 G06 关闭后规划 |
| G08 | 模型、架构和性能消融 | Not started | 待 G07 关闭后规划 |
| G09 | 训练就绪与三条 Smoke Pipeline | Not started | 待 G08 关闭后规划 |
| G10 | 发布、Dogfooding 与面试资产 | Not started | 待 G09 关闭后规划 |

## 推进规则

- 日期不是推进依据，前一 Gate 的关闭标签才是。
- 每个 Gate 在实施前必须冻结 decision-complete Master Plan。
- 负向 baseline 结果可以通过 Gate，前提是实验预注册、执行完整、结论真实。
- 安全、租户隔离、Ground Truth、locked-test、质量与性能标准不得因实施简化而放宽。
