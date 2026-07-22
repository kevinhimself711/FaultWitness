---
document_id: FW-BLUEPRINT-001
version: 1.2.0
status: frozen_for_g01
owner: project
approved_on: 2026-07-22
amendments:
  - docs/blueprint/AMENDMENTS/AMD-0001.md
  - docs/blueprint/AMENDMENTS/AMD-0002.md
---

# FaultWitness 最终项目规划

## 1. 项目定义

FaultWitness 是一个面向微服务事故调查、受控修复与持续优化的多租户 Agent Runtime。

它不是任意领域的通用 Agent 平台，也不是只会根据最近变更执行回滚的单场景 Agent。

产品边界：

- 深度主线：发布、配置、路由和版本变更的因果归因与安全回滚。
- 泛化故障：资源/容量、依赖/网络/数据面、Pod/运行时/重试。
- 主 SUT：固定 commit 的 OpenTelemetry Demo。
- 第二 SUT：Online Boutique，仅用于 diagnosis-only 泛化。
- 外部锁定基准：ITBench-Lite。
- 写动作：Deployment rollback、Config restore、Rollout restart、Scale workload。
- 不建设插件市场、跨地域高可用、任意云接入、真实生产运维或公网执行入口。

项目以三个强制工程平面共同完成为标准：

1. Agent Application
   - LangGraph 状态机、证据推理、RAG、Memory、Skills、工具调用、审批、修复验证和 Incident Console。
2. Agent Runtime/Infra
   - 多租户身份与隔离、任务调度、lease/heartbeat、checkpoint、暂停/恢复/取消、沙箱、策略和水平扩展。
3. Data/Eval/Training
   - Scenario DSL、TrajectoryIR、LangSmith Eval、badcase、数据版本和 SFT/DPO/GRPO 管线。

三者在代码和部署上解耦，在项目计划和最终验收上不可选。

## 2. 架构先行原则

项目采用“前置冻结不变量、按 Gate 细化实验设计、Gate 关闭更新 As-built”的方式。

G00/G01 必须冻结：

- 系统边界、组件职责、数据流和信任边界。
- Incident、Runtime Task、Agent Graph、ActionTransaction 四层状态模型。
- 状态所有权、命令、事件、Schema 和持久化真源。
- Tenant、安全、审批、幂等、Ground Truth 隔离和 Trace 不变量。
- 训练数据目标 Schema。

对应 Gate 再细化：

- LangGraph 节点、Prompt、Reducer、并行度和预算。
- RAG、Memory、Skill 的具体策略。
- Scheduler lease、backoff 和扩容参数。
- 模型选择、缓存、路由和 Multi-Agent。
- 训练超参数和正式训练启动条件。

架构基线变化必须先提交 ADR，说明：

- 变更动机与替代方案。
- Schema、状态、API 和数据迁移影响。
- replay 和向后兼容影响。
- 安全与失败语义影响。
- 回归集和回滚方式。

## 3. 状态与服务边界

状态所有权：

| 状态 | 唯一写入者 | 权威存储 |
|---|---|---|
| Incident Lifecycle | Control API/Incident Service | PostgreSQL |
| Runtime Task | Scheduler | PostgreSQL |
| Agent Graph State | Agent Worker/LangGraph | PostgreSQL Checkpoint |
| ActionTransaction | Action Executor | PostgreSQL |
| Agent Trace/Eval | LangSmith Instrumentation | LangSmith |
| Artifact/Dataset | Eval/Data Worker | MinIO/DVC |

跨所有权边界只能使用类型化 Command 和 Transactional Outbox Event。所有状态使用版本号或 fencing token。

核心 Incident 路径：

    NEW
    → QUEUED
    → INVESTIGATING
    → WAITING_APPROVAL
    → EXECUTING
    → VERIFYING
    → RESOLVED

失败及人工路径：

    INVESTIGATING → ESCALATED
    WAITING_APPROVAL → ESCALATED
    VERIFYING → ROLLING_BACK
    ROLLING_BACK → RESOLVED | ESCALATED
    safe non-terminal state → CANCELLED

Runtime Task 使用至少一次投递：

    PENDING → LEASED → RUNNING → SUCCEEDED
    RUNNING → PAUSED | RETRY_WAIT | FAILED
    RETRY_WAIT → PENDING | DEAD_LETTER
    non-terminal → CANCEL_REQUESTED → CANCELLED

ActionTransaction：

    PREPARED
    → APPROVAL_PENDING
    → APPROVED
    → EXECUTING
    → VERIFYING
    → COMMITTED

失败与补偿：

    APPROVAL_PENDING → REJECTED | EXPIRED | CANCELLED
    EXECUTING → UNCERTAIN
    VERIFYING → COMPENSATING
    COMPENSATING → ROLLED_BACK | UNCERTAIN | MANUAL
    UNCERTAIN → VERIFYING | MANUAL

安全不变量：

- Agent 只能产生 ToolCall 和 ActionProposal，不能直接执行 shell 或 Kubernetes 写操作。
- Action Executor 是唯一写入口。
- R2 动作必须绑定不可变审批摘要。
- 参数、环境或资源版本变化会使审批失效。
- COMMITTED 必须有后置条件成功证据。
- UNCERTAIN 不得盲目重试。
- 不宣称分布式 exactly-once。
- Ground Truth 和 locked test 永不暴露给 Agent。
- 不保存模型私有思维链。

## 4. 技术方向

- Python 3.12、FastAPI、Pydantic、LangGraph。
- React、TypeScript、Vite。
- PostgreSQL、Redis、Qdrant、MinIO、DVC。
- Keycloak/OIDC、OPA/Rego。
- K3s、Helm、NetworkPolicy、ResourceQuota。
- OpenTelemetry、Prometheus、Loki、Tempo、Grafana。
- LangSmith 作为 Trace、Dataset、Experiment 和 Eval 强依赖。
- SOPS + Age 管理秘密。
- TRL、PEFT、bitsandbytes、Accelerate 支撑训练 smoke。

ModelGateway 通过 Bailian live channel 调用 Qwen、DeepSeek 和 GLM 三个模型族，并保留 NewAPI-compatible channel，统一 Structured Output、Tool Calling、Streaming、timeout、retry、fallback、Token、费用和 Trace。三个模型族共享一个当前 live upstream，因此不得表述为三家独立 Provider 或跨供应商容灾；NewAPI live 证据在取得 token 后单独补齐。

默认 Agent 架构为单 Orchestrator 加确定性并行 Evidence Collectors。Multi-Agent 只有消融证明收益后才能成为默认路径。

## 5. 文档与证据控制面

项目从第一个 commit 开始维护：

- 根 AGENTS.md。
- PROJECT_STATE.yaml。
- 最终项目规划和 Gate Master Plan。
- Requirement/Evidence/Claim Registry。
- Architecture、ADR 和 Threat Model。
- Iteration Plan。
- Eval Plan、Manifest、Report 和 Badcase。
- Data Card、Model Card、Eval Card。
- Upstream、Originality 和 Third-party 清单。

资产规则：

- 行为变化和必要文档进入同一 commit。
- CI 根据候选 SHA 生成不可变 Eval manifest，不自动回写仓库。
- Iteration 和 Gate 分别使用资产关闭 commit。
- Gate 失败和负实验永久保留。
- 原始 JD、面经、密钥、私有 Trace 和受限数据不得提交。
- Tier-C 辅导答案不能成为强制需求或指标的唯一来源。
- 每项公开主张最终必须关联代码、测试、Trace、数据和可复现实验。

权威命令使用跨平台入口：

    uv run python -m faultwitness_dev <command>

Makefile 只能作为 Linux 薄封装。

## 6. Gate 路线

### G00：蓝图、架构与治理基线

交付：

- 独立私有 GitHub 仓库和受保护 main。
- AGENTS、PROJECT_STATE、Requirement/Evidence/Claims。
- 四类架构视图和四层状态机。
- OpenAPI/AsyncAPI 设计。
- 治理 Schema、验证 CLI、CI 和负向 fixture。

退出：

- Requirement、架构、状态、接口、失败语义全部机器可校验。
- 无审批绕过、状态无主、测试泄漏或来源违规。

### G01：平台、契约与 Trace 地基

交付：

- K3s 基础服务。
- Pydantic contract、状态转换服务、checkpoint 和 outbox。
- ModelGateway 和 LangSmith Instrumentation。
- gVisor/Kata、4090 和服务器能力报告。

退出：

- 非法状态转换被拒绝。
- Qwen、DeepSeek、GLM 三个模型族通过 Bailian 完成结构化输出、工具和流式 live smoke；Bailian/NewAPI 两个 channel 通过统一契约，NewAPI live 在 token 可用前保持显式 deferred。
- Trace/日志密钥泄漏为 0。

### G02：故障实验室与基线

交付：

- 四类 Scenario DSL。
- 32 个可执行种子场景。
- 最终 160 case 的 dev/validation/locked 预注册。
- Deterministic、Naive ReAct 和无 RAG 基线。

最终质量下限在本 Gate 冻结，只能提高：

- Core E2E 不低于 max(70%, best baseline + 10pp)。
- Root-cause Top-3 不低于 85%。
- Evidence precision 不低于 90%。
- Unsupported critical claim 不高于 2%。
- Tool schema validity 不低于 99%。
- Dead/no-progress loop 低于 1%。
- 任一故障族成功率不低于 55%。

### G03：只读 Agent 纵切

交付：

- Typed State、checkpoint、interrupt、SSE/outbox。
- Evidence、Hypothesis、ProbePlan、ChangeEvent。
- 指标、日志、链路、Kubernetes 和变更工具。
- Incident Console 最小闭环。

退出：

- Validation E2E 比最佳基线提高至少 5pp。
- 关键结论 100% 回溯到 EvidenceRef。
- Worker 和 SSE 恢复不丢失或重复状态。

### G04：RAG、Memory、Skills 与多模态

交付：

- 文档、表格、架构图和 Dashboard 摄取。
- Dense/Sparse/Hybrid/Reranker。
- Working、Knowledge、Episode、Preference、Conversation Summary。
- 3–5 个领域 Skill 和动态 Tool/Skill Retrieval。

退出：

- Recall@10 不低于 85%，Citation precision 不低于 90%。
- 无收益机制不得进入默认架构。
- Memory 和动态 Skill 通过独立消融和安全回归。

### G05：受控修复与动作事务

交付：

- 四种类型化写动作。
- OPA、Action Digest、审批、幂等、后置验证、补偿和审计。

退出：

- 未授权写、审批绕过、Digest 篡改接受和重复外部副作用均为 0。
- 后置验证成功率不低于 95%。
- 失败进入补偿或人工升级为 100%。

通过来源、License 和 Secret 审计后，仓库可以首次公开；运行环境继续私有。

### G06：多租户 Runtime、调度与沙箱

交付：

- Keycloak 四角色。
- PostgreSQL RLS、Qdrant ACL、MinIO 隔离。
- Quota、task queue、lease、heartbeat、deadline 和 backpressure。
- 1–4 Worker。
- gVisor；不兼容时使用 Kata。二者均不可用则 Gate 失败。

退出：

- 跨租户泄漏、任务丢失和重复动作副作用为 0。
- Worker 在 lease 到期后 30 秒内恢复。
- 1 到 4 Worker 的 Mock 吞吐提高至少 2.5 倍。
- Sandbox escape、Secret 读取和未授权网络为 0。

### G07：完整评测、数据飞轮与泛化

交付：

- 160 个均衡 case。
- 至少 24 个误导性最近变更场景。
- 1,000 条以上 TrajectoryIR。
- 七类 badcase 和至少 10 个深度报告。
- Online Boutique 20 个 diagnosis-only case。
- ITBench-Lite locked eval。

退出：

- 达到 G02 冻结质量下限。
- Judge-human agreement 不低于 0.80。
- 数据、Ground Truth 和失败标签全部可追溯。

### G08：模型、架构与性能消融

比较：

- Deterministic、Naive ReAct 和最终 Agent。
- 单 Agent 与 Planner/Investigator/Verifier。
- 静态与动态 Tool/Skill。
- GLM、DeepSeek、Qwen。
- RAG、Memory、Reranker、Cache、Batch 和 Routing。

Multi-Agent 进入默认架构必须满足质量提高至少 5pp、95% CI 不跨 0，且成本和延迟增加不超过 30%；或危险建议下降至少 50%且质量不退化。

### G09：训练就绪与真实 Smoke

交付：

- SFT：State + Tools 到 Structured Next Action。
- DPO：Chosen/Rejected 计划或轨迹。
- GRPO：环境、规则 Reward 和轨迹采样。

退出：

- SFT、DPO 各至少 20 个 optimizer step。
- GRPO 至少 10 个 optimizer update。
- 三条路径均完成 checkpoint 保存、恢复、加载和推理。
- 不使用 validation、locked test 或外部 benchmark。
- 不把 smoke loss/reward 包装为质量提升。

### G10：发布、Dogfooding 与面试资产

交付：

- 私网运行 4–6 周。
- 至少 3 名使用者和 20 次事故调查或回放。
- Runbook、Threat Model、Data/Model/Eval Card。
- 成功、补偿、误导性变更、Worker 恢复和租户隔离演示。
- 应用、Infra、算法三套面试叙事。

最终退出：

- G00–G09 全部通过，无 P0/P1 缺陷。
- 新环境仅按文档即可部署。
- Claims 100% 关联代码、测试、Trace、数据和实验。
- 三条训练管线有真实 4090 smoke 证据。

## 7. 全局评测原则

- 确定性 evaluator 优先。
- 同一模型不得同时生成测试、答案并作为唯一 Judge。
- 随机实验至少三次并报告 95% CI。
- 安全、审批、隔离和测试泄漏为零容忍。
- Baseline 后阈值只能提高。
- 失败 Gate、负实验和 rejected architecture 均保留。
- 所有性能结果报告硬件、并发、数据集、模型、成本和失败分布。

项目以全部 Gate 和架构一致性检查通过为完成标准，不以日期、代码量、框架数量或单次演示成功作为完成标准。
