---
document_id: FW-GATE-G00-PLAN
gate: G00
version: 1.0.0
status: frozen
previous_gate: null
architecture_target: 1.0.0
approved_on: 2026-07-22
---

# G00 Gate Master Plan：架构、治理与证据基线

## 1. Gate 目标

G00 建立可执行、可验证的工程治理与架构基线，使 G01 无需重新决定：

- 项目边界和三个工程平面。
- 系统组件、状态所有权和信任边界。
- Incident、Runtime Task、Agent Graph、ActionTransaction 四层状态机。
- REST、SSE、Command/Event 和核心类型契约。
- 失败、重试、取消、恢复、补偿和不确定状态语义。
- Requirement、Evidence、Claim、Iteration、Eval、Gate、ADR 资产模型。
- 跨平台验证 CLI、CI、私有 GitHub 和 main 分支规则。

本 Gate 关闭时只允许声称“规划、架构和治理基线已建立”，不得声称产品已经运行。

## 2. 范围、非目标与依赖

### 2.1 范围

- 独立 Git monorepo 和私有 GitHub。
- 根 AGENTS、PROJECT_STATE 和最终规划。
- 四类架构视图、四层状态机和 Threat Model 初版。
- OpenAPI 3.1、AsyncAPI 3.0 和核心类型目录。
- Requirement/Evidence/Claim Registry。
- Gate、Iteration、Eval、ADR Schema 和模板。
- 跨平台 faultwitness_dev 验证 CLI。
- GitHub Actions、规则集、负向 fixture 和 G00 Report。

### 2.2 非目标

G00 不得：

- 实现业务 API、LangGraph Runtime、Tool、前端或产品数据库逻辑。
- 部署 K3s、Keycloak、OPA、Qdrant、MinIO 或 LangSmith。
- 调用模型 API。
- 部署或修改 OpenTelemetry Demo。
- 构造故障数据或运行模型质量 Eval。
- 实现 RAG、Memory、Sandbox、多租户运行逻辑或训练。
- 提交原始 JD、面经、密钥、私有 Trace 或绝对本机源路径。
- 固定 Prompt、模型、Chunk、并行度、lease 时长和训练超参数。

### 2.3 固定依赖

- Git 2.45.1，默认分支 main。
- Python 3.12，使用 uv 和提交的 uv.lock。
- Node 22，使用 pnpm 和提交的 pnpm-lock.yaml。
- 权威命令：

      uv run python -m faultwitness_dev <command>

- Makefile 只允许作为 Linux 薄封装。
- 在已认证的个人 GitHub 账户创建私有仓库 FaultWitness。
- 若同名远程仓库已经存在，停止并报告，禁止覆盖或自动改名。
- Docker、kubectl、helm 和服务器不是 G00 依赖。

### 2.4 Planning bootstrap 例外

当前 planning commit 是唯一允许在 Iteration 基础设施建立前创建的提交，只能包含：

- 最终项目规划。
- G00 Master Plan 和 Report 占位。
- PROJECT_STATE。
- 根 AGENTS、README、License、Changelog 和文本规范。

它不计为 I-0001，也不得包含治理 CLI、CI、接口 Schema、状态机文件或产品代码。

## 3. Frozen Architecture

### 3.1 架构视图

G00 必须交付：

- SYSTEM_CONTEXT.md。
- CONTAINER_ARCHITECTURE.md。
- DATA_AND_CONTROL_FLOW.md。
- DEPLOYMENT_AND_TRUST_BOUNDARIES.md。
- STATE_MACHINES.md。

架构图使用 Mermaid。状态转换的机器可读 YAML 是状态机单一事实源；文档图由 YAML 生成或校验。

### 3.2 状态所有权

| 状态 | 唯一写入者 | 计划权威存储 |
|---|---|---|
| Incident Lifecycle | Control API/Incident Service | PostgreSQL |
| Runtime Task | Scheduler | PostgreSQL |
| Agent Graph State | Agent Worker/LangGraph | PostgreSQL Checkpoint |
| ActionTransaction | Action Executor | PostgreSQL |
| Agent Trace/Eval | LangSmith Instrumentation | LangSmith |
| Artifact/Dataset | Eval/Data Worker | MinIO/DVC |

规则：

- 组件不得直接修改其他组件拥有的状态。
- 跨组件协调使用类型化 Command 和 Transactional Outbox Event。
- 状态携带 state_version；Runtime lease 使用 fencing token。
- Terminal state 不可原地改写。

### 3.3 Incident 状态机

主路径：

    NEW
    → QUEUED
    → INVESTIGATING
    → WAITING_APPROVAL
    → EXECUTING
    → VERIFYING
    → RESOLVED

分支：

    INVESTIGATING
    ├─ diagnosis-only/no action → RESOLVED
    ├─ R1 authorized → EXECUTING
    ├─ R2 proposed → WAITING_APPROVAL
    └─ insufficient evidence/forbidden/budget exhausted → ESCALATED

    WAITING_APPROVAL
    ├─ approved → EXECUTING
    ├─ rejected/expired → ESCALATED
    └─ cancelled → CANCELLED

    EXECUTING
    ├─ known result → VERIFYING
    └─ uncertain effect → ESCALATED

    VERIFYING
    ├─ postconditions pass → RESOLVED
    ├─ compensable failure → ROLLING_BACK
    └─ non-compensable/uncertain → ESCALATED

    ROLLING_BACK
    ├─ system healthy → RESOLVED
    └─ still unhealthy/uncertain → ESCALATED

Terminal states：RESOLVED、ESCALATED、CANCELLED。

不变量：

- R2 未获有效审批不得进入 EXECUTING。
- RESOLVED 必须有 Final Report 和后置条件结果。
- Action 为 UNCERTAIN/MANUAL 时 Incident 必须 ESCALATED。
- 执行期间取消先设置 cancel_requested，只在安全点生效。

### 3.4 Runtime Task 状态机

    PENDING → LEASED → RUNNING → SUCCEEDED

    LEASED → RETRY_WAIT: lease expires before start
    RUNNING → PAUSED: graph interrupt
    PAUSED → PENDING: resume
    RUNNING → RETRY_WAIT: retryable failure or lease loss
    RETRY_WAIT → PENDING: attempts remain
    RETRY_WAIT → DEAD_LETTER: attempts exhausted
    RUNNING → FAILED: non-retryable failure
    non-terminal → CANCEL_REQUESTED → CANCELLED

不变量：

- Task 为至少一次投递。
- 每次 attempt 使用新 attempt_id，保留原 task_id。
- Worker 只能使用有效 lease 和 fencing token 提交。
- PAUSED 不长期持有 Worker lease。
- Runtime 不宣称 exactly-once。

### 3.5 Agent Graph 状态机

    Intake
    → ScopeAndRisk
    → BuildInitialPlan
    → RetrieveContext
    → CollectEvidence
    → NormalizeEvidence
    → GenerateHypotheses
    → VerifyHypotheses

    VerifyHypotheses
    ├─ evidence insufficient + budget remains
    │  → PlanProbes → CollectEvidence
    ├─ diagnosis complete, no action
    │  → ComposeReport → Finalize
    ├─ actionable conclusion
    │  → ProposeAction → PolicyCheck
    ├─ cannot judge safely
    │  → Escalate
    └─ budget/deadline exhausted
       → Escalate

    PolicyCheck
    ├─ R0/R1 allowed → DispatchAction
    ├─ R2 → AwaitApproval → DispatchAction
    └─ R3/rejected/expired → Escalate

    DispatchAction
    → AwaitActionResult
    ├─ known result → VerifyOutcome
    └─ uncertain → Escalate

    VerifyOutcome
    ├─ pass → Finalize
    ├─ compensable failure → RequestCompensation
    └─ non-compensable/uncertain → Escalate

不变量：

- Graph 只能产生 ToolCall 和 ActionProposal。
- LLM 决策节点与确定性策略、执行节点分离。
- Collector 通过确定性 Reducer 合并。
- 重要转换写 checkpoint。
- Approval 使用 interrupt；interrupt 前不得有非幂等副作用。
- State 包含步骤、工具次数、Token、费用、Deadline 和无进展预算。
- 不保存模型私有思维链。

G03 只能细化节点、Reducer、Prompt 和预算，不得改变这些不变量。

### 3.6 ActionTransaction 状态机

    PREPARED
    ├─ R1 policy authorization → APPROVED
    ├─ R2 → APPROVAL_PENDING
    └─ R3 → REJECTED

    APPROVAL_PENDING
    ├─ approved → APPROVED
    ├─ rejected → REJECTED
    ├─ timeout → EXPIRED
    └─ cancelled → CANCELLED

    APPROVED
    ├─ dispatch → EXECUTING
    └─ cancel before dispatch → CANCELLED

    EXECUTING
    ├─ receipt known → VERIFYING
    └─ effect uncertain → UNCERTAIN

    VERIFYING
    ├─ postconditions pass → COMMITTED
    ├─ compensable failure → COMPENSATING
    └─ non-compensable failure → MANUAL

    COMPENSATING
    ├─ rollback verified → ROLLED_BACK
    ├─ effect uncertain → UNCERTAIN
    └─ cannot compensate → MANUAL

    UNCERTAIN
    ├─ reconciled → VERIFYING
    └─ deadline exceeded → MANUAL

Terminal states：COMMITTED、REJECTED、EXPIRED、ROLLED_BACK、MANUAL、CANCELLED。

不变量：

- Action Digest 绑定 Tenant、Environment、动作、参数、资源版本、前后置条件、补偿、风险、审批人、有效期和单次 token。
- 参数、资源版本或环境变化使审批失效。
- COMMITTED 必须有后置条件成功证据。
- API 响应丢失不得盲目重试。
- UNCERTAIN 只能 reconciliation 或人工处置。

## 4. 接口与数据流设计

### 4.1 REST 基线

- POST /v1/incidents
- GET /v1/incidents/{incident_id}
- GET /v1/incidents/{incident_id}/events
- POST /v1/incidents/{incident_id}/approvals
- POST /v1/incidents/{incident_id}/cancel
- POST /v1/incidents/{incident_id}/feedback
- GET /v1/tools
- GET /v1/skills

规则：

- tenant_id、user_id、roles 只从 OIDC/JWT 获取。
- 创建、审批和取消支持 Idempotency-Key。
- 状态修改携带 expected_state_version。
- 状态或 Digest 冲突返回 409。
- Quota 返回 429，依赖不可用返回 503。
- 错误信封：code、message、retryable、correlation_id、details。
- SSE 使用递增 event_id 和 Last-Event-ID。

IncidentCreate 最小字段：

- source。
- environment_id。
- service_scope。
- time_window。
- symptom_summary。
- alert_refs。
- change_events。
- mode：diagnosis_only 或 allow_actions。
- budget：deadline、steps、model calls、tokens、cost。

ApprovalRequest 最小字段：

- action_id。
- action_digest。
- decision：approve 或 reject。
- expected_state_version。
- comment。

Domain Event Envelope：

- event_id。
- event_type。
- schema_version。
- occurred_at。
- tenant_id。
- incident_id。
- optional run_id/action_id。
- correlation_id。
- causation_id。
- sequence。
- payload。

### 4.2 核心类型目录

G00 定义字段、所有者、存储和版本，但不实现 Pydantic：

- TenantContext。
- IncidentSpec、IncidentState。
- RunTask、RunState、Lease。
- ChangeEvent。
- AgentState。
- EvidenceRef。
- Hypothesis。
- ProbePlan。
- ToolDefinition、ToolCall、ToolResult。
- SkillManifest。
- ActionProposal。
- ApprovalGrant。
- ActionTransaction。
- TrajectoryIR。
- EvalResult。
- DomainEvent。

### 4.3 数据流

    Alert/User
    → Control API + OIDC TenantContext
    → Incident + Transactional Outbox
    → Scheduler Task
    → Agent Worker + LangGraph Checkpoint
    → Tool/Skill Retrieval
    → Typed Tool Gateway
    → EvidenceRef / Artifact
    → Hypothesis / ProbePlan
    → ActionProposal
    → OPA + Approval
    → Action Executor
    → Postcondition Verification / Compensation
    → Incident Finalization
    → LangSmith Eval + TrajectoryIR + DVC

### 4.4 固定失败语义

| 故障 | 固定行为 |
|---|---|
| OIDC/Tenant 无效 | Incident 创建前拒绝 |
| 重复创建 | 按 Idempotency-Key 返回原结果 |
| DB 事务失败 | 状态和 Outbox 均不提交 |
| Outbox 发布失败 | 重试；消费者按 event_id 去重 |
| Worker lease 丢失 | 旧 Worker 被 fencing；从 checkpoint 新 attempt 恢复 |
| 模型/工具临时失败 | 有界重试；耗尽后降级或 Escalate |
| 结构化输出无效 | 有界修复；仍失败则 Escalate |
| Qdrant 不可用 | 标记知识缺失；依赖知识的写动作被阻止 |
| MinIO 不可用 | 暂停大结果流程，不把无限结果塞入上下文 |
| LangSmith 不可用 | 本地缓冲；只读可继续，写动作 fail-closed，Gate 不得关闭 |
| OPA 不可用 | 所有写动作 fail-closed |
| Keycloak 不可用 | 拒绝新请求和审批；已有只读 Run 可按有效快照结束 |
| Action 响应丢失 | UNCERTAIN；先 reconciliation，禁止盲目重试 |
| 后置验证失败 | 补偿；不可补偿则 MANUAL/ESCALATED |
| 补偿结果未知 | UNCERTAIN → MANUAL |
| Cancel | 安全 checkpoint 生效；存在不确定副作用则 Escalate |
| Ground Truth | Agent、Runtime 和普通开发凭证均不可访问 |

## 5. Iteration 拆分

### I-0001：仓库与工具链 Bootstrap

范围：

- 校验 planning baseline。
- 创建私有 GitHub remote。
- 固定 Python/Node/uv/pnpm。
- 提交 pyproject、package manifest 和锁文件。
- 启用基本文本、路径和 clean-clone 检查。

Eval：EVAL-G00-001。

通过：

- Windows 与 Ubuntu clean checkout 可复现。
- GitHub private、default main、remote 正确。
- 父目录研究材料不被跟踪。

计划 commit：

    chore(g00): bootstrap repository toolchain and remote

### I-0002：治理 Schema、CLI 与基础 CI

范围：

- PROJECT_STATE、Requirement、Claim、Iteration、Gate、Eval、ADR Schema。
- faultwitness_dev CLI。
- pytest、Ruff、Schema、Markdown、本地链接检查。
- GitHub Actions 和 main Ruleset。

Eval：EVAL-G00-002。

负向 fixture：

- 缺字段。
- 重复 ID。
- 不存在的 Gate/Iteration。
- 缺文档的行为变化。
- 非法状态和阈值下降。

计划 commit：

    feat(governance): add schemas validators and baseline CI

### I-0003：Requirement、Evidence 与来源治理

范围：

- Source Catalog、Requirements、Evidence Matrix。
- 覆盖 22 份 JD 和报告口径下 84 份非空面经材料。
- Tier C 不得成为强制要求唯一来源。
- 映射到角色、架构和 G00–G10。
- UPSTREAM、ORIGINALITY、THIRD_PARTY。

Eval：EVAL-G00-003。

通过：

- ID 唯一。
- 每条强制 Requirement 有 Tier A/B 来源、Architecture Ref 和 Gate。
- Git 中无原始文本、绝对本机路径和受限内容。

计划 commit：

    docs(requirements): establish evidence-backed requirement registry

### I-0004：总体架构与信任边界

范围：

- 五份架构文档。
- 状态所有权、Command/Event 边界和数据真源。
- Threat Model 初版。
- ADR：三平面、Outbox、LangSmith、本地 Artifact、至少一次投递、Action 安全边界。

Eval：EVAL-G00-004。

Walkthrough：

- 只读成功。
- R2 审批成功。
- 审批拒绝/过期。
- Worker lease 丢失。
- Action 响应丢失。
- 验证失败与补偿。
- 补偿不确定。
- Cancel。
- LangSmith/OPA/Keycloak 故障。
- 跨租户访问。

计划 commit：

    docs(architecture): freeze system boundaries and control flows

### I-0005：状态机、接口与失败语义

范围：

- 四套机器可读状态转换表。
- Mermaid 图。
- OpenAPI、AsyncAPI 和核心类型目录。
- Command/Event Catalog。
- 状态机和接口 conformance validator。

Eval：EVAL-G00-005。

通过：

- initial、terminal、owner 完整。
- 必要状态可达且非终态可达终态。
- 转换有 Actor、Guard、Command/Event。
- 无 R2 绕过、UNCERTAIN 自动重复和 lease 丢失后提交路径。
- OpenAPI/AsyncAPI/Schema 可解析。

计划 commit：

    feat(contracts): define state machines APIs and failure semantics

### I-0006：G00 全量门禁与候选审计

范围：

- CI 硬化、PR/Issue 模板、资产同步。
- Secret、SBOM、License、Mermaid、Markdown 和 link checks。
- 对固定候选 SHA 运行完整 G00 Eval。
- 不关闭 Gate。

Eval：EVAL-G00-006。

CI：

- Windows：bootstrap、CLI、Schema、状态机。
- Ubuntu：相同检查、Markdown、Mermaid、SBOM、Secret。
- 外部链接为非阻塞 scheduled job；本地链接阻塞。
- G00 manifest 将 LangSmith 标记为 not applicable，因为没有 Runtime Trace。

计划 commit：

    ci(g00): enforce architecture governance and gate checks

## 6. 完整 Gate 通过标准

### 6.1 仓库

- 私有 GitHub、main、remote 和 Ruleset 正确。
- Windows/Ubuntu clean clone 均可复现。
- 验证后 Git status clean。
- 不依赖全局 make、Docker、kubectl 或 helm。
- Lockfile 和第三方 Action 固定版本或完整 SHA。

### 6.2 治理

- AGENTS、PROJECT_STATE、Final Plan、G00 Plan/Report 通过 Schema。
- CI 能拒绝：
  - 缺 Iteration。
  - Requirement 无来源。
  - 修改 locked-test。
  - 行为变化不更新资产。
  - 降低 Gate 阈值。
  - 非法状态转换。
  - Tenant 请求体注入。
  - R2 绕过审批。
- 本地链接错误、Secret、不兼容 License 和未归属代码均为 0。

### 6.3 Requirement 与证据

- Source Catalog 覆盖 22 份 JD 和 84 份非空面经材料。
- 100% 强制 Requirement 具有 ID、Tier A/B 来源、Role、Architecture Ref、Gate 和验收描述。
- Tier C 作为唯一来源的强制 Requirement 为 0。
- Git 中原始面经/JD、绝对本机源路径和长引用为 0。

### 6.4 架构

- 五份架构文档完成并互链。
- 所有组件有职责、信任级别、输入、输出和数据真源。
- 四层状态所有权无重叠。
- 所有跨组件写入经过 Command/Event。
- Agent 到 Action Executor、Ground Truth 和 Sandbox 无旁路。
- Mermaid 全部可渲染。

### 6.5 状态机与接口

- 未归属状态：0。
- 不可达必要状态：0。
- 不能到达终态的非终态：0。
- 缺 Guard/Actor/Command/Event 的转换：0。
- Terminal 非法出边：0。
- R2 审批绕过路径：0。
- UNCERTAIN 自动重复路径：0。
- lease 丢失后提交路径：0。
- OpenAPI/AsyncAPI/Schema 解析错误：0。
- 所有状态修改接口都有幂等、版本冲突和错误语义。

### 6.6 必须完成的 Walkthrough

1. 只读诊断成功。
2. Diagnosis-only 结束。
3. R1 自动安全动作。
4. R2 审批成功。
5. 审批拒绝。
6. 审批过期。
7. Worker 在 checkpoint 前退出。
8. Worker 在 checkpoint 后退出。
9. Action 已执行但响应丢失。
10. 后置验证失败并补偿成功。
11. 补偿结果不确定。
12. Cancel 在动作前和动作中到达。
13. LangSmith、OPA、Keycloak、Qdrant、MinIO 故障。
14. 跨租户和 Ground Truth 访问。

### 6.7 不允许豁免

- 缺失架构视图。
- 缺失或矛盾状态机。
- 审批、安全、租户和 Ground Truth 边界缺陷。
- Secret、License 或来源违规。
- Requirement 无 Tier A/B 证据。
- CI 不能阻止资产漂移。

外部链接网络失败可以非阻塞，但必须记录；本地复现和本地链接不能豁免。

## 7. Gate 关闭协议

EVAL-G00-006 全部通过后，使用独立资产 commit：

- 生成 G00 REPORT。
- 记录 evaluated candidate SHA 和 CI run。
- 更新 PROJECT_STATE：

      last_closed_gate: G00
      active_gate: G01
      active_gate_status: not_started
      active_iteration: null
      architecture_version: 1.0.0
      requirements_version: 1.0.0
      governance_schema_version: 1.0.0

- 更新 Claims、Changelog 和 ADR Index。
- 创建：

      chore(gate): close G00 architecture and governance baseline

- 打标签：

      gate/G00-v1

关闭 commit 不得包含产品实现、架构语义变化或 Gate 阈值变化。

## 8. G01 交接边界

G01 可以直接实现：

- Pydantic/domain contract。
- PostgreSQL 状态、checkpoint 和 outbox。
- 状态转换服务。
- ModelGateway。
- LangSmith Instrumentation。
- K3s 基础服务。

G01 不得重新决定：

- 四层状态及所有权。
- Tenant 来源。
- Agent 与 Action Executor 边界。
- R2 审批不变量。
- 至少一次投递和 Action 幂等。
- UNCERTAIN/MANUAL 语义。
- Ground Truth 隔离。
- 公共 API 路径和 Domain Event Envelope。

若实现证明基线不可行，必须停止并新增 ADR、Migration Plan 和 Architecture Version，不得在代码中静默偏离。
