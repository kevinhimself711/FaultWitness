---
document_id: FW-GATE-G00-REPORT
gate: G00
plan_version: 1.0.0
status: pass
evaluated_candidate_sha: 1f36a799c27dfe0709a529448e6935d0ea3103eb
eval_run: EVAL-G00-006
closed_on: 2026-07-22
---

# G00 Gate Report：架构、治理与证据基线

## 执行摘要

- Gate 状态：PASS。
- 不可变候选：`1f36a799c27dfe0709a529448e6935d0ea3103eb`。
- 完整 Eval：`make eval-g00-close`。
- CI：Windows、Ubuntu 与 Ubuntu audit 三项均通过。
- Waiver：0。
- 决策：关闭 G00，将项目交接至尚未启动的 G01。

本 Gate 证明规划、架构、契约、证据和工程治理基线已经建立；不声称产品 Runtime、Agent、基础设施或模型质量已经实现。

## 1. 候选与不可变证据

| Evidence | Result | Immutable reference |
| --- | --- | --- |
| Local full closure Eval | pass | 51 tests, 47 Markdown files, 9 Mermaid diagrams, 354 local dependency components |
| Protected-main Windows | pass | Job 88972214159 in run 29934431213 |
| Protected-main Ubuntu | pass | Job 88972214168 in run 29934431213 |
| Protected-main Ubuntu audit | pass | Job 88972214027 in run 29934431213 |
| CycloneDX 1.6 SBOM | pass | Artifact 8535477694, bound to the exact candidate SHA |
| Remote Ruleset | pass | Active Ruleset 19545995 requires all three checks and an up-to-date PR |

Protected-main run: <https://github.com/kevinhimself711/FaultWitness/actions/runs/29934431213>

Audit artifact: <https://github.com/kevinhimself711/FaultWitness/actions/runs/29934431213/artifacts/8535477694>

## 2. Iteration 与 Eval 完整性

`eval-g00-close` 机器确认 6 个 Iteration 均为 `completed`、均绑定 commit，6 个 Eval 均为 `pass` 且 `open_evidence` 为 0：

| Iteration | Eval | Result | Evidence |
| --- | --- | --- | --- |
| I-0001 | EVAL-G00-001 | pass | [Report](../../evals/EVAL-G00-001/REPORT.md) |
| I-0002 | EVAL-G00-002 | pass | [Report](../../evals/EVAL-G00-002/REPORT.md) |
| I-0003 | EVAL-G00-003 | pass | [Report](../../evals/EVAL-G00-003/REPORT.md) |
| I-0004 | EVAL-G00-004 | pass | [Report](../../evals/EVAL-G00-004/REPORT.md) |
| I-0005 | EVAL-G00-005 | pass | [Report](../../evals/EVAL-G00-005/REPORT.md) |
| I-0006 | EVAL-G00-006 | pass | [Report](../../evals/EVAL-G00-006/REPORT.md) |

关闭验证器同时拒绝未完成 Iteration、非 pass Eval、open evidence、pending work 和 waiver；关闭变更验证器只接受精确 9 个资产路径，并拒绝夹带源码或不精确的 G01 状态。

## 3. Requirement 与来源证据

- Source Catalog：22 份 JD、84 份纳入面经、2 份空面经排除记录、1 份技术参考和 1 份上游报告。
- Requirement Registry：57 项，包括 41 项 P0、13 项 P1 和 3 项整体纳入规划的 P2。
- 100% 强制 Requirement 具有 Tier A/B 来源、角色、架构引用、Gate 和验收描述。
- Tier C 作为唯一来源的强制 Requirement：0。
- Git 中原始 JD、原始面经、受限正文和绝对本机源路径：0。

详见 [Methodology](../../requirements/METHODOLOGY.md) 与机器可读 Registry。

## 4. 架构与安全边界

- 三个工程平面与五个逻辑责任平面完整保留，没有把 Agent、Runtime Infra、Data/Eval/Training 降为可选插件。
- 15 个组件、9 个权威存储、6 类状态资产、9 个信任边界和 4 条强制禁止路径均有机器校验。
- Incident、Runtime Task、Agent Graph、ActionTransaction 的唯一写入者无重叠。
- Agent 无直接 SUT 写权限、无 Ground Truth 访问、无跨租户旁路、无非沙箱任意代码执行路径。
- R2 审批、Action digest、幂等、fencing、`UNCERTAIN` reconciliation 和 compensation 语义已冻结。
- 6 份 ADR 均保持 accepted；Threat Model 已评审，无关闭期语义修改。

详见 [System Context](../../architecture/SYSTEM_CONTEXT.md)、[Trust Boundaries](../../architecture/DEPLOYMENT_AND_TRUST_BOUNDARIES.md) 与 [Threat Model](../../security/THREAT_MODEL.md)。

## 5. 状态机与接口契约

- 4 套状态机、52 个状态、82 条转换；不可达状态、非终态无法收敛、terminal 非法出边均为 0。
- 8 个 REST/SSE path、8 个 AsyncAPI channel、21 个核心类型。
- 34 个 Command、43 个 Event、10 个错误码、17 条固定失败语义均可解析并相互引用。
- R2 绕过、`UNCERTAIN` 自动重试、stale lease 提交、请求体 tenant 注入路径均为 0。
- 所有 9 个 Mermaid block 已用固定 CLI 和真实浏览器渲染为 SVG。

详见 [Contract Index](../../contracts/README.md) 与 [State Machine Diagrams](../../contracts/STATE_MACHINE_DIAGRAMS.md)。

## 6. 十四条 Gate Walkthrough

14/14 场景通过并绑定 I-0005 的机器契约：只读诊断、diagnosis-only、R1、R2、审批拒绝、审批过期、checkpoint 前后 Worker 退出、Action 响应丢失、补偿成功、补偿不确定、动作前后 Cancel、五类依赖故障、跨租户与 Ground Truth 访问。

机器结果见 [WALKTHROUGHS.yaml](../../evals/EVAL-G00-006/WALKTHROUGHS.yaml)。

## 7. 供应链、发布边界与仓库治理

- Python/Node lockfile frozen resolution 通过；第三方 Actions 全部固定 40 位 commit SHA。
- Secret、本机绝对路径、不兼容或未知许可证、未归属源码发现数均为 0。
- CycloneDX 1.6 SBOM 中组件具有唯一 `bom-ref`、版本和许可证；Ubuntu 与 Windows 的平台组件差异显式保留。
- 公开仓库 `main` 禁止删除和 non-fast-forward，要求 PR、最新分支和三项必需检查。
- 外链检查为记录型 scheduled job；本地链接始终阻塞。

## 8. 保留的失败与纠偏

- 首个审计 artifact 因隐藏目录默认排除而失败；改为显式包含隐藏文件，未降低审计阈值。
- 中间 artifact 名称使用 PR merge-ref；后续候选将名称和内容都绑定到 head SHA。
- Gate readiness review 发现 `not_started` 交接 Schema 缺口并新增回归。
- Completion audit 发现普通 Eval 未阻止未完成证据，新增 fail-closed close mode。
- Closure dry run 发现无 Iteration 的关闭提交无法通过治理，新增精确 9 资产协议。

失败 run、被替代候选和修复记录均保留在 Git 与 GitHub Actions 历史中。

## 9. 限制与下一 Gate

- G00 没有产品 Runtime，因此 LangSmith runtime trace 明确为 `not_applicable`；该例外不得继承到 G01 及后续 Runtime Gate。
- 未实现业务 API、LangGraph Agent、Tool、Sandbox、K3s、数据管线、训练或模型质量 Eval。
- G01 仅进入 `not_started`；其 decision-complete Master Plan 尚未冻结，禁止直接开始实现。

## Gate 决策

G00 的所有冻结通过标准均已满足，无 waiver。决策为 **PASS AND CLOSE**，架构版本、Requirement 版本、契约版本和治理 Schema 版本均保持 `1.0.0`，交接至 G01 规划阶段。
