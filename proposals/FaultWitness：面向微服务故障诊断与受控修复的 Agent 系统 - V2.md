# FaultWitness：面向微服务故障诊断与受控修复的 Agent 系统 \- V2

## 一、项目结论



### 1\.1 正式名称



项目正式更名为：



> **FaultWitness — Evidence\-First Incident Diagnosis and Guarded Remediation**  
> 
> 面向微服务故障诊断与受控修复的 Agent 系统。
> 
> 



`OpsPilot` 必须彻底停用：它已被同赛道商业 [AI SRE 平台](https://opspilot.com/)使用，PyPI 上的 [`opspilot`](https://pypi.org/project/opspilot/) 和 [`opspilot-ai`](https://pypi.org/project/opspilot-ai/) 也已被占用。继续使用会产生品牌、包名和项目原创性混淆。



`FaultWitness` 经本轮有限公开检索暂未发现精确同名 GitHub 仓库、账户、PyPI 包或明显同类软件，可作为工作名；这不构成商标审查，正式公开前仍需再次核查 GitHub、PyPI、npm、Docker Hub、域名及主要商标数据库。



代码和部署标识统一使用：



- 仓库及 Python 包：`faultwitness`

- 服务前缀：`faultwitness-*`

- Kubernetes 命名空间：`faultwitness-system`、`faultwitness-target`、`faultwitness-chaos`、`faultwitness-bench`

- LangSmith 项目：`faultwitness-dev`、`faultwitness-staging`、`faultwitness-eval`

    

### 1\.2 定位选择



三个方案的最终判断：



|方案|深度|可评测性|差异化|实施风险|决策|
|---|---|---|---|---|---|
|通用 AI SRE 平台|低|低|低|很高|不采用|
|只支持发布/配置事故|高|高|中高|低|过度收窄|
|通用架构，发布/配置事故为 P0 主线|高|高|高|可控|**采用**|



正式定位为：



> FaultWitness 采用可扩展的微服务事故诊断与受控修复架构，但 P0 的代码、数据、评测、演示和简历主叙事集中在“发布、配置、路由、版本和运行参数变更引起的微服务事故”。
> 
> 



这意味着：



- 不对外宣称“可处理所有生产事故”。

- 编排、状态、工具和动作协议不能硬编码成发布回滚脚本。

- 非变更事故仍保留，用于验证系统不会因看到近期变更就产生确认偏差。

- P0 自动修复主要支持 Deployment 和配置回滚；其他事故优先只读诊断、拒答或升级人工。

- “通用”由真实的第二类事故适配和 OOD 测试证明，不由空泛的插件接口数量证明。

    

发布/配置事故适合作为主线，因为它同时具备：



- 可复现的事故前后版本、变更时间和 Diff；

- 确定性的根因 Oracle；

- Metrics、Logs、Traces、变更记录和 Runbook 等多源证据；

- 可逆的 Deployment/Config 回滚动作；

- 可客观验证的错误率、P95、健康检查和业务路径后置条件；

- “近期有变更但变更并非根因”的高质量反事实场景。

    

核心差异化固定为：



> 将变更作为一等证据，但不把“最近变更”直接视为根因；Agent 必须通过时序、服务拓扑、版本范围和遥测信号验证因果假设，再通过审批、幂等、后置验证和补偿协议执行受控恢复。
> 
> 



### 1\.3 三大核心能力顺序



项目主次顺序固定为：



1. **基本盘：Agent 应用与完整业务闭环**

2. **第二重点：Agent Infra、可靠性与安全执行**

3. **第三重点：数据与训练就绪管线，但不承诺实际训练**

    

这个顺序是验收优先级，不代表数据和评测等到最后才建设：



- 第一个可交付结果必须是告警到诊断、审批、恢复、验证、报告的完整纵向切片。

- Infra 必须让纵向切片具备持久化、恢复、幂等、审计和安全边界。

- 数据管线从第一天记录 Trace 和 Ground Truth，但模型训练只有在数据质量和收益条件满足后才启动。

- 实际 SFT/DPO/RL 不属于项目完成条件；可复现的数据导出和训练接口属于强制交付。

    

### 1\.4 最终系统目标



开发一个可验证、可回放、可评测、具备生产约束的 SRE Agent：



> 在真实 Kubernetes 微服务中接收告警，自主收集指标、日志、链路、Kubernetes 事件、部署与配置变更和运维知识，形成证据链与根因假设；经策略检查和人工审批后执行有限修复，并验证结果、失败回滚、生成事故报告。
> 
> 



最终必须形成：



- 一套真实运行的微服务故障实验环境。

- 一套基于 LangGraph 的持久化、可中断、可恢复 Agent 工作流。

- 一套 LangSmith Trace、Offline Eval、Online Eval 和 Badcase 数据飞轮。

- 一套公开数据获取、知识库构建、故障注入、轨迹生产和训练就绪流水线。

- 一套带权限、审批、审计、幂等、验证和回滚的副作用闭环。

- 一份通过对照实验和置信区间证明设计收益的实验报告。

- 一套能够说明竞品参考边界和个人原创贡献的可审计材料。

    

### 1\.5 最终演示路径



必须覆盖：



1. 成功闭环：注入变更故障 → 告警 → 多源取证 → 证据化 RCA → 修复方案 → OPA 策略检查 → 人工审批 → 执行 → 健康验证 → 自动结案。

2. 失败闭环：错误或无效修复 → 后置条件未满足 → 自动停止或补偿回滚 → 保留现场 → 升级人工。

3. 反事实闭环：存在近期发布，但真正根因是网络、流量或下游依赖 → Agent 找到反证 → 拒绝盲目回滚 → 给出正确诊断或升级人工。

4. 恢复闭环：Worker 在工具调用、审批或动作执行前后崩溃 → 从 Checkpoint 恢复 → 不重复产生外部副作用。

    

### 1\.6 明确不做



- 不把任何 LangGraph 示例或 AI SRE 仓库改名包装。

- 不 fork、翻译或轻度改写竞品的核心 Agent 实现。

- 不把公开微服务 SUT 本身计入个人原创贡献。

- 不把调用多个数据源包装成多 Agent。

- 不让模型持有管理员 kubeconfig、任意 Shell、数据库写权限或 Chaos Mesh 权限。

- 不以 LLM\-as\-a\-Judge 作为唯一评测方式。

- 不把实际训练模型作为项目完成前提。

- 不建设插件市场、完整企业多租户、跨地域高可用或任意云厂商集成。

- 不宣称整体能力超过 HolmesGPT、OpenSRE 等成熟竞品。

- 不把 staging 实验环境宣传成企业生产系统。

    

---



## 二、开源参考、公共依赖与采用边界



### 2\.1 四类外部项目



外部项目严格分为：



1. **通用依赖**：LangGraph、PostgreSQL、OPA、OTel 等，可作为正式运行时依赖。

2. **公开 SUT 和故障实验设施**：OpenTelemetry Demo、Chaos Mesh，只作为被诊断对象和实验环境。

3. **数据集与外部基准**：AIOpsLab、ITBench、RCAEval、OpenRCA，用于锁定测试或评测设计。

4. **AI SRE 竞品**：只允许学习架构模式、阅读实现、形成 ADR，并通过独立部署作为黑盒基线；不进入 FaultWitness 源码树或运行时依赖。

    

### 2\.2 采用清单



|项目|用途|采用边界|
|---|---|---|
|[OpenTelemetry Demo](https://github.com/open-telemetry/opentelemetry-demo)|主业务实验环境|锁定 Commit，通过 Overlay、故障注入器和适配器扩展；不修改核心源码，不宣称其为自研业务系统|
|[LangGraph](https://github.com/langchain-ai/langgraph)|Agent 状态机|使用 Typed State、Reducer、Checkpoint、Interrupt、Streaming 和恢复执行|
|[LangSmith](https://docs.langchain.com/langsmith/evaluation)|Trace 与评测|所有模型、工具、检索和图节点接入，运行 Offline/Online Eval 和回归实验|
|[AIOpsLab](https://github.com/microsoft/AIOpsLab)|外部在线基准|编写适配器，验证 detection、localization、analysis、mitigation 泛化|
|[ITBench](https://github.com/itbench-hub/ITBench)|任务设计参考|对齐真实 Kubernetes SRE 场景与评测口径，不复制其 Agent|
|[ITBench\-Lite](https://huggingface.co/datasets/ibm-research/ITBench-Lite)|离线公开测试|作为锁定外部测试集，不进入训练和调参集|
|[RCAEval](https://github.com/phamquiluan/RCAEval)|RCA 泛化测试|使用许可证明确的数据和基线|
|[OpenRCA](https://github.com/microsoft/OpenRCA)|跨行业 RCA 测试|Ground Truth 与 Agent 运行环境物理隔离|
|[AgentRx](https://github.com/microsoft/AgentRx)|轨迹诊断参考|学习失败归因思想，独立实现 TrajectoryIR 和 Badcase Pipeline|
|[Chaos Mesh](https://github.com/chaos-mesh/chaos-mesh)|故障注入|独立命名空间运行，Agent 无权直接调用|
|[OPA](https://github.com/open-policy-agent/opa)|动作授权|用 Rego 实现确定性风险、资源和审批策略|
|[Qdrant](https://github.com/qdrant/qdrant)|知识检索|Hybrid Retrieval、元数据过滤、版本和权限隔离|



### 2\.3 允许学习的竞品工程模式



本轮 GitHub 实现复核带来的局部修订如下：



|竞品|允许学习的成熟模式|FaultWitness 的独立实现|
|---|---|---|
|[HolmesGPT](https://github.com/HolmesGPT/holmesgpt)|工具注册、超大工具结果外置、上下文控制、Tool Approval、受控工具执行|自行定义 Typed Tool Contract、Artifact Spill、Action Digest、OPA 策略和 LangGraph 审批恢复|
|[OpenSRE](https://github.com/Tracer-Cloud/opensre/blob/main/docs/investigation-pipeline-architecture.md)|分阶段调查、预先工具选择、Seed Probe、有界 ReAct、重复调用缓存、停滞终止、上下文预算|自行设计 LangGraph 图、Probe Policy、Evidence/ChangeEvent 契约和 Eval Dataset|
|[Aurora](https://github.com/Arvo-AI/aurora/blob/main/server/chat/backend/agent/workflow.py)|单 Agent 默认路径、可选编排、输入/输出 Guardrail、异步工具处理|P0 坚持单 Agent\+并行确定性 Collector；Verifier 由消融决定|
|[K8sGPT](https://github.com/k8sgpt-ai/k8sgpt)|确定性 Analyzer 先提取问题，再交给模型解释|规则明确的场景优先走 Workflow Baseline，Agent 处理证据不完备和路径动态的场景|
|[IncidentFox](https://github.com/incidentfox/incidentfox)|渐进式工具披露和隔离上下文|仓库当前已归档，只作历史设计参考，不作依赖或正式基线|



可以学习：



- 模块职责和服务边界；

- 有界工具循环；

- Tool Schema 裁剪和渐进式披露；

- 大结果外置与摘要；

- 重复调用和停滞检测；

- 确定性 Seed Probe；

- 读写平面隔离；

- 审批绑定和短期凭证；

- Provider 降级与部分结果保留；

- 单 Agent、多 Agent 的路由与退出策略；

- 测试维度和故障分类方法。

    

### 2\.4 禁止事项



- 不 fork 任何 AI SRE Agent。

- 不复制、翻译或轻度改写其 Agent Loop、Graph、Prompt、Skill、State Schema、Tool Adapter、数据库 Schema、评测样例、Ground Truth 或前端。

- 不通过更换 LangGraph、模型、UI、变量名或目录结构声称原创。

- 不将竞品代码作为 Git Submodule、Vendored Source 或内部包。

- 不把竞品的数据和评测指标当成自己的项目数据。

- 竞品只能通过公开 CLI、API 或独立容器作为黑盒基线运行。

- 必要的代码级复用必须保留许可证、上游 Commit 和修改声明，且不得计入个人核心贡献。

    

### 2\.5 独立实现与来源治理



仓库必须提供：



- `UPSTREAM.md`：列出依赖、SUT、数据集、竞品、许可证、版本和固定 Commit。

- `ORIGINALITY.md`：逐模块说明参考过的概念、独立设计内容和本人实现内容。

- `THIRD_PARTY.md`：第三方代码、资产和再分发边界。

- SBOM、锁文件和许可证扫描结果。

- 关键 ADR：说明为什么采用该设计、比较过什么替代方案、与竞品模式有何差异。

- 竞品学习记录只总结问题、模式和权衡，不保存或粘贴竞品核心代码。

- Git 历史、LangSmith Experiment 和 Badcase 记录用于证明设计演进。

    

OpenTelemetry Demo 明确只是 SUT。FaultWitness 的个人核心贡献是：



- Incident/Change/Evidence 数据契约；

- LangGraph 诊断与恢复状态机；

- 多源 Tool Gateway；

- 变更—症状因果验证；

- OPA\+HITL 受控动作协议；

- Checkpoint、幂等、补偿和故障恢复；

- LangSmith 全链路评测体系；

- 自建事故 DSL、数据和实验结论。

    

---



## 三、系统设计



### 3\.1 总体架构



```Plain Text
flowchart LR
    UI["Incident Console<br/>React + TypeScript"] --> API["FastAPI Control Plane"]
    API --> LG["LangGraph Agent Runtime"]
    LG --> CP["PostgreSQL Checkpoint<br/>Incident / Audit / Outbox"]
    LG --> TG["Typed Tool Gateway"]
    LG --> RAG["Knowledge Service<br/>Qdrant + Reranker"]
    LG --> POL["OPA Policy Engine"]
    LG --> LS["LangSmith<br/>Trace / Dataset / Eval"]

    TG --> OBS["Prometheus / Loki / Tempo<br/>Kubernetes / Git / Change Events"]
    TG --> ACT["Restricted Action Executor"]
    ACT --> K8S["Target Kubernetes Namespace"]
    CHAOS["Chaos Mesh<br/>独立权限"] --> K8S
    K8S --> OTEL["OpenTelemetry Demo"]
    OTEL --> OBS

    OBS --> OBJ["MinIO Artifact Store"]
    LG --> OBJ
    OBJ --> DATA["DVC Data Pipeline<br/>TrajectoryIR / Parquet / JSONL"]
```



架构使用五类稳定契约解耦：



- `IncidentInput`

- `EvidenceSource`

- `ChangeEvent`

- `ActionPolicy/ActionAdapter`

- `PostconditionVerifier`

    

P0 优先实现发布和配置变更适配器，但不建立专用的“发布故障 Agent”分叉。



### 3\.2 技术栈



- Python 3\.12、FastAPI、Pydantic v2、LangGraph。

- 官方 PostgreSQL Checkpointer，服务路径使用异步 Saver。

- PostgreSQL：Incident、Checkpoint、审计、Outbox、反馈和数据版本。

- Redis：Provider 限流、短期缓存、分布式信号量和易失租约；不作为事实源。

- MinIO：原始 Telemetry、工具大结果、报告和评测产物。

- Qdrant：Dense\+Sparse Hybrid Retrieval、RRF、元数据过滤。

- Cross\-encoder：Rerank；是否保留由检索消融决定。

- OPA/Rego：确定性授权和风险裁决。

- OpenTelemetry Collector、Prometheus、Loki、Tempo、Grafana。

- React、TypeScript、Vite。

- DVC：数据、索引和评测产物版本。

- `ModelGateway`：归一化模型 Tool Calling、结构化输出、Streaming、超时和降级。

- 首版直接实现候选 Provider Adapter；LiteLLM 只能位于 Gateway 后，不允许业务代码绑定某一网关。

- SOPS\+Age：加密配置；密钥不得进入浏览器、Trace 或仓库。

- K3s：服务器主部署；Docker Compose 用于单机开发和可复现集成测试。

    

### 3\.3 LangGraph 主状态机



```Plain Text
stateDiagram-v2
    [*] --> Intake
    Intake --> ScopeAndRisk
    ScopeAndRisk --> InitialPlan
    InitialPlan --> RetrieveContext
    RetrieveContext --> CollectEvidence
    CollectEvidence --> NormalizeEvidence
    NormalizeEvidence --> GenerateHypotheses
    GenerateHypotheses --> VerifyHypotheses
    VerifyHypotheses --> CollectEvidence: 证据不足且预算允许
    VerifyHypotheses --> ProposeAction: 形成可执行结论
    VerifyHypotheses --> Escalate: 无法安全判断
    ProposeAction --> PolicyCheck
    PolicyCheck --> AwaitApproval: 需要审批
    PolicyCheck --> Execute: 低风险且策略允许
    PolicyCheck --> Escalate: 禁止动作
    AwaitApproval --> Execute: 批准
    AwaitApproval --> Escalate: 拒绝或超时
    Execute --> VerifyOutcome
    VerifyOutcome --> Close: 后置条件满足
    VerifyOutcome --> Rollback: 失败且可补偿
    Rollback --> VerifyOutcome
    VerifyOutcome --> Escalate: 超预算或不可补偿
    Close --> IncidentReport
    Escalate --> IncidentReport
    IncidentReport --> [*]
```



关键约束：



- 使用强类型 `AgentState`，不能用无结构 Message History 承载业务状态。

- 节点输入输出必须有 Schema；并行采集通过确定性 Reducer 合并。

- 重要状态转换均写 Checkpoint，支持断点恢复和 Time Travel。

- 审批使用 LangGraph `interrupt()`；Interrupt 前的操作必须可重放或幂等。

- 设置最大步骤、同类工具调用、总时长、Token、费用、无进展次数和 Deadline。

- 不保存模型私有思维链，只保存结构化决策摘要、证据引用、工具调用和 State Delta。

- P0 为单 Agent\+并行确定性 Collector。

- P1 最多加入一个隔离上下文的 Verifier，只有消融证明收益后才保留。

- Intake 将 Deployment、Rollback、Helm Values、ConfigMap、Secret 引用、环境变量、Feature Flag 和路由变更统一为 `ChangeEvent`。

- Evidence Planner 先检查变更是否与症状在时间、拓扑、版本和服务范围上吻合；证据不足时必须回到通用指标、日志、Trace 和依赖调查。

    

### 3\.4 状态与公共类型



核心类型：



- `IncidentCase`：告警、环境、服务范围、时间窗、状态、预算和版本信息。

- `ChangeEvent`：`change_id/change_type/service/environment/revision/occurred_at/source/diff_ref/provenance`。

- `EvidenceRef`：证据 ID、来源、查询、时间范围、服务、摘要、Artifact URI、内容哈希和 ACL。

- `Hypothesis`：根因实体、机制、支持证据、反证、缺失证据、置信度和下一步验证。

- `ProbePlan`：候选 Probe、辨别能力、覆盖增益、新鲜度、延迟、成本和风险。

- `ActionProposal`：规范化动作、目标、参数、风险级别、Dry\-run、前后置条件、补偿动作和不可变动作摘要。

- `ApprovalDecision`：动作摘要、审批人、有效期、理由、范围和单次使用 Token。

- `ToolEvent`：输入摘要、结果引用、耗时、错误、重试和幂等键。

- `ActionTransaction`：执行状态、资源版本、回执、后置验证和补偿结果。

- `TrajectoryIR`：图节点、State Delta、工具事件、模型元数据、结构化决策、人工反馈和最终结果。

- `EvalResult`：数据集、版本、Evaluators、指标、费用、延迟和失败标签。

- `IncidentSpec`：SUT 版本、故障注入、Ground Truth、必需证据、允许动作、后置条件和清理逻辑。

    

状态枚举：



- Incident：`NEW / INVESTIGATING / WAITING_APPROVAL / EXECUTING / VERIFYING / ROLLING_BACK / RESOLVED / ESCALATED / CANCELLED`

- Risk：`R0_READ / R1_SAFE_REVERSIBLE / R2_APPROVAL_REQUIRED / R3_FORBIDDEN`

- Action：`PREPARED / APPROVAL_PENDING / APPROVED / EXECUTING / VERIFYING / COMMITTED / COMPENSATING / ROLLED_BACK / UNCERTAIN / MANUAL`

    

### 3\.5 API 与流式事件



固定接口：



- `POST /v1/incidents`：从告警或人工输入创建事件；支持可选 `change_events[]`。

- `GET /v1/incidents/{id}`：获取状态、证据、假设和动作。

- `GET /v1/incidents/{id}/events`：SSE；支持 `Last-Event-ID` 断线续传。

- `POST /v1/incidents/{id}/approvals`：批准或拒绝指定 Action Digest。

- `POST /v1/incidents/{id}/cancel`：请求安全取消。

- `POST /v1/incidents/{id}/feedback`：提交根因、证据、动作和报告反馈。

- 故障注入和评测接口独立鉴权，不暴露给普通用户或 Agent。

    

Typed SSE 事件包括：



- `incident.status.changed`

- `change.correlated`

- `evidence.added`

- `hypothesis.updated`

- `action.proposed`

- `approval.requested`

- `tool.completed`

- `checkpoint.created`

- `verification.failed`

- `rollback.completed`

- `incident.finalized`

    

PostgreSQL Transactional Outbox 保证状态提交和事件发布的一致性；SSE 事件使用递增 `event_id` 去重和补发。



### 3\.6 工具体系



只读工具：



1. 告警聚合与时间线。

2. PromQL 指标查询和异常检测。

3. LogQL 日志聚合、聚类和样本提取。

4. TraceQL/Tempo 错误链路和 Critical Path。

5. Kubernetes 对象、事件和状态读取。

6. 服务拓扑构建。

7. Git、Deployment、Helm、配置和 Feature Flag Diff。

8. Runbook、文档和历史事故检索。

9. 资源与依赖健康检查。

10. 动作后置条件验证。

11. 变更—症状时序和拓扑关联。

    

受控写工具分级实现：



- P0：回滚到已知 Deployment Revision。

- P0：恢复到已知配置版本。

- P1：Rollout Restart。

- P1：Scale 调整。

- P1：白名单配置 Patch。

- 所有阶段：补偿或回滚动作。

    

工具治理：



- 模型只看到 Tool Schema，不接触凭证。

- Reader 与 Action Executor 使用不同 ServiceAccount。

- Agent 永远拿不到 Chaos Mesh 权限。

- 禁止任意 Shell、任意 URL、任意 SQL 和任意 Kubernetes Manifest。

- 大结果存入 MinIO；上下文只注入摘要、统计和 Artifact ID。

- 写工具必须支持 Dry\-run、幂等键、资源版本、前置条件、后置条件、超时、审计和补偿。

- MCP 可以作为接入协议，但服务端 Gateway 和 OPA 才是安全边界。

    

---



## 四、公开数据、RAG 与训练就绪流水线



### 4\.1 数据来源优先级



1. 自己运行微服务并注入故障产生的真实 Telemetry。

2. 自己生成的 Deployment、Git、Manifest、Helm 和配置变更历史。

3. 有许可证、可固定 Commit 的官方仓库和文档。

4. ITBench\-Lite、RCAEval、OpenRCA 等公开基准。

5. 自己编写的 Runbook、故障模板、变更记录和 Incident Spec。

6. 公开事故复盘只作补充知识，不作为核心 Ground Truth。

    

知识获取不使用无边界爬虫。采用 Allowlist Registry，记录：



- URL或仓库；

- Commit、版本或抓取时间；

- 许可证和允许用途；

- 内容哈希；

- 原始文件位置；

- 更新频率；

- 是否允许重新分发。

    

无明确再分发许可的网页只保存 URL、必要元数据和原创摘要。



### 4\.2 自建核心场景集



主 SUT 固定为 OpenTelemetry Demo，首版保留不少于八类故障：



**P0 变更主线：**



1. 错误代码、镜像、Canary 或 API/Schema 版本发布。

2. Endpoint、端口、路由、环境变量、Feature Flag 或配置版本错误。

3. Timeout、Retry、Circuit Breaker 等韧性参数回归。

4. CPU/内存 Limit、连接池、队列、并发和扩缩容参数回归。

    

**非变更反事实和泛化场景：**



5. 运行时 CPU/内存资源耗尽。

6. Pod Crash、Readiness/Liveness 或单实例故障。

7. 网络延迟、丢包、DNS 或连接异常。

8. 数据库、消息队列或其他下游依赖故障。

    

150 个唯一 Eval Case 的互斥主分区固定为：



- 105 个发布/配置变更相关核心 Case；

- 30 个“症状相似但根因不是变更”的反事实/OOD Case；

- 15 个控制面、安全、恢复和不确定执行 Case。

    

同时保留以下非互斥覆盖标签，一个 Case 可以具有多个标签：



- 至少 72 个 Live Scenario Variants；

- 至少 24 个安全、Prompt Injection、越权或审批攻击 Case；

- 至少 18 个模型、工具和依赖失败 Case；

- 至少 18 个 RAG 版本、引用、冲突和权限 Case；

- 至少 18 个噪声、冲突证据和 OOD Case。

    

每个核心事故族必须包含：



- 无噪声基础版；

- 多个近期变更候选版；

- 误导性最近变更版；

- 一路或多路遥测缺失版；

- Runbook 过期或冲突版；

- 修复成功返回但服务未恢复版；

- 回滚失败或结果不确定版。

    

每个 `IncidentSpec` 必须包含：



- SUT Commit 和初始状态；

- Workload、故障注入和清理逻辑；

- `change_id` 和变更 Diff；

- 根因 Oracle；

- 必需、可选和干扰证据；

- 允许动作、禁止动作和可接受替代动作；

- 前置条件、后置条件和观察窗；

- 回滚 Oracle；

- 风险、难度、Split 和数据来源。

    

Ground Truth 不得挂载到 Agent 可见容器、知识库或工具响应。



### 4\.3 RAG 实现



采集内容：



- OpenTelemetry Demo 代码、配置和 Deployment Manifest；

- Git、Helm、配置和发布历史；

- Kubernetes、OpenTelemetry、Prometheus、Grafana、Chaos Mesh 官方文档；

- 项目 Runbook、服务目录、SLO 和故障处置规范；

- 已验证 Incident、人工确认结果和复盘。

    

实时指标、日志和 Trace 必须通过 Tool 查询，不能向量化后伪装成实时诊断。



索引流水线：



```Plain Text
acquire
→ license_validate
→ parse
→ normalize
→ redact
→ structure-aware chunk
→ deduplicate
→ enrich_metadata
→ embed
→ sparse_index
→ qdrant_upsert
→ retrieval_regression_test
```



检索策略：



- 先按环境、服务、版本、权限和有效时间做 Metadata Filter。

- Dense\+Sparse 后使用 RRF 融合。

- Cross\-encoder 对候选重排。

- 返回父文档上下文和精确引用。

- 模型结论必须引用 `EvidenceRef` 或知识文档 ID。

- 比较 Dense\-only、Sparse\-only、Hybrid、Hybrid\+Reranker。

- 是否保留 Dense 和 Reranker 由 Eval 结果决定，不预设高级方案必然更优。

    

事故经验只有在根因、动作和后置条件完成验证后才写入 Episode Memory。失败动作、误诊和人工否定必须保存为负例。Checkpoint、Knowledge 和 Episode Memory 使用不同 Schema 和读取路径。



### 4\.4 数据与算法优化流水线



DVC 流水线固定为：



```Plain Text
acquire
→ license_validate
→ normalize
→ deduplicate
→ redact
→ split
→ materialize_scenarios
→ build_index
→ export_langsmith_dataset
→ run_experiment
→ export_trajectory_ir
→ label_badcases
→ build_training_artifacts
```



存储格式：



- 指标、日志统计和 Trace Features：Parquet。

- Agent 轨迹、反馈和标签：JSONL。

- 场景、Ground Truth 和动作约束：YAML。

- 大型原始对象：MinIO\+DVC。

- Schema、Manifest 和流水线：Git。

    

数据标签至少包括：



- `fault_family`

- `change_type`

- `service`

- `difficulty`

- `risk`

- `evidence_availability`

- `ood`

- `failure_stage`

- `dataset_version`

    

切分按 Fault Family、服务、环境、场景模板和时间分组，禁止随机逐行切分。外部 Benchmark 永远作为锁定测试集。



训练就绪产物包括：



- SFT：状态、可用工具到下一步结构化 Action。

- Preference：成功/失败或人工修正后的 Chosen/Rejected 轨迹片段。

- RL Episode：Observation、Action、Rule Reward、Done 和 Failure Reason。

- Dataset Card：来源、许可证、去重、泄漏检查、Split 和限制。

    

只有同时满足以下条件才进入实际训练：



- 不少于 500 条经审计的高价值成功/失败轨迹或偏好对；

- 失败集中于模型可学习且可稳定标注的类别；

- Prompt、Tool、RAG 和确定性流程优化进入平台期；

- 标注一致性达到预设门槛；

- 存在独立验证集；

- 预期收益能够覆盖训练和维护成本。

    

---



## 五、LangSmith Trace、评测与实验设计



### 5\.1 Trace 规范



所有 LangGraph 根运行、节点、模型、工具、检索和 Evaluator 接入 LangSmith。每条根 Trace 至少记录：



- `git_sha`

- `graph_version`

- `prompt_version`

- `tool_schema_version`

- `state_schema_version`

- `dataset_version`

- `rag_index_version`

- `model_provider/model_name`

- `scenario_id/fault_id`

- `incident_id/task_id`

- `change_id/change_type`

- `checkpoint_id`

- `action_digest`

- `opa_decision`

- `postcondition_result`

- `rollback_result`

- Token、费用、延迟、重试和 Fallback

- LangSmith Run ID 与 OTel Trace ID 的双向关联字段

    

所有外发 LangSmith 数据先脱敏。失败、人工复核和高价值 Trace 提升为 Dataset Example，并同步保存本地 TrajectoryIR。



### 5\.2 固定对照组



必须实现四种可切换内部配置：



- A：确定性 Runbook Workflow。

- B：通用 ReAct 单 Agent。

- C：证据驱动、有界 LangGraph Agent。

- D：C\+独立 Verifier。

    

增加以下消融：



- 有结构化 `ChangeEvent` vs 无 `ChangeEvent`；

- 无 Evidence Constraint vs 有 Evidence Constraint；

- 无后置验证 vs 有后置验证；

- 无 Episode Memory vs 有 Episode Memory；

- 正常执行 vs Worker Kill/Retry/Checkpoint Recovery。

    

外部黑盒基线固定为：



- HolmesGPT：共同适用的只读 RCA 子集；

- K8sGPT：Kubernetes Analyzer 共同子集；

- AIOpsLab/ITBench：外部任务和泛化能力。

    

OpenSRE、Aurora 用于架构研究，不作为必须二次开发的代码基底。外部基线不要求全部击败，但必须逐场景报告胜负、失败原因和适用边界。



### 5\.3 LangSmith 数据集



建立隔离数据集：



- `core-live-diagnosis-remediation`

- `change-attribution-counterfactual`

- `rag-citation-regression`

- `tool-reliability-recovery`

- `security-policy-adversarial`

- `itbench-lite-external`

- `rcaeval-openrca-external`

    

任何 Prompt、模型、Tool Schema、Graph、检索策略或知识版本变更，都运行对应 Offline Eval。Staging 流量运行 Online Evaluator 抽样；失败 Trace 复核后进入 Regression Dataset。



### 5\.4 Evaluator 分层



确定性 Evaluator：



- 根因实体、机制和 Top\-k 命中；

- Change Correlation Precision/Recall；

- “错误归因到最近变更”的比率；

- 必需证据覆盖；

- 支持证据与反证是否完整；

- 工具选择、Schema、参数和调用顺序；

- 权限、审批、Action Digest 和策略符合性；

- 后置条件、回滚和最终服务健康；

- 引用存在性、支持性、版本和 ACL；

- 重复查询、无进展、预算和死循环；

- 延迟、Token、费用和工具错误率。

    

LLM Evaluator 只评价难以规则化的部分：



- 诊断解释是否忠于证据；

- 是否主动寻找反证；

- 报告是否完整、清楚且不过度推断；

- 两条轨迹的相对质量。

    

Judge 使用与被评系统不同的模型家族，隐藏系统名称，并随机抽样 10%–20% 双人人工复核，报告 Judge 与人工一致性。



### 5\.5 规模与验收门槛



至少运行 1,000 条完整轨迹，覆盖：



- 四个内部对照配置；

- 模型和参数变化；

- 多随机种子和重复运行；

- 常规、困难、噪声、工具故障和安全场景；

- 有变更、无变更和误导性变更场景。

    

初始门槛：



- 常规核心场景端到端成功率 ≥80%。

- 困难场景成功率 ≥60%。

- 根因 Top\-3 和证据质量显著优于 ReAct Baseline。

- 工具 Schema 合法率 ≥99%。

- 可重试工具最终成功率 ≥95%。

- RAG Recall@10 ≥90%。

- 引用正确率 ≥95%。

- 无证据支持的重要结论 ≤3%。

- 死循环率 \<1%。

- 未授权写操作必须为 0。

- R2 动作绕过审批必须为 0。

- 测试中的重复外部副作用必须为 0。

- 修复成功返回但健康未恢复时，必须回滚或升级人工。

- P0 变更事故子集必须独立过门，不能用简单非 P0 Case 的均分掩盖。

- 误导性近期变更场景中，未经证据直接回滚的次数必须为 0。

    

门槛可在 Baseline 后向上校准，安全零容忍指标不得降低。报告必须包含置信区间、重复次数、模型版本、成本和失败分布。



---



## 六、安全、可靠性与部署



### 6\.1 权限模型



- `R0_READ`：只读，可自动执行。

- `R1_SAFE_REVERSIBLE`：明确白名单、可逆且可验证。

- `R2_APPROVAL_REQUIRED`：必须等待人工批准。

- `R3_FORBIDDEN`：删除数据、任意命令、修改安全边界等永久禁止。

    

审批绑定：



- Action Digest；

- 动作类型和不可变参数；

- 目标环境、服务和资源版本；

- Revision 或 Diff Hash；

- 前置条件、后置条件和补偿动作；

- 审批人、有效期和单次消费 Token。

    

任何参数、资源版本或目标变化都会使旧审批失效。



通用执行协议：



```Plain Text
prepared
→ approval_pending
→ approved
→ executing
→ verifying
→ committed
或 compensating → rolled_back
或 uncertain/manual
```



系统采用“至少一次任务领取\+动作幂等”保证受支持动作不重复产生外部效果，不宣称分布式 Exactly\-once。



### 6\.2 服务端部署



服务器使用 K3s，命名空间：



- `faultwitness-system`

- `faultwitness-target`

- `faultwitness-chaos`

- `faultwitness-bench`

    

要求：



- NetworkPolicy、ResourceQuota 和独立 ServiceAccount。

- PostgreSQL、MinIO、Qdrant 使用持久卷和定期快照。

- Grafana、LangSmith Key、审批接口仅通过 LAN、VPN 或 SSH 隧道访问。

- PC 通过 Remote SSH 开发；本地只运行单测和轻量组件。

- GPU 仅用于 Embedding、Reranker 或可选模型实验；P0 不依赖本地推理。

- 公共 CI 只运行单测、契约测试、静态检查和无特权集成测试。

- PR 不得触发服务器特权 Runner。

- 完整故障注入和修复评测在受控服务器手动或受保护流水线触发。

- Staging 至少持续运行 2–4 周，保留真实 Incident Journal 和 LangSmith Run。

    

### 6\.3 可靠性验证



必须覆盖：



- 模型 429、5xx、超时和无效结构化输出；

- Tool 超时、部分结果、重复结果和 Schema 变化；

- Worker 在 Checkpoint 前后被杀死；

- 重复任务领取和重复消息；

- PostgreSQL、Redis、MinIO 短时不可用；

- 审批超时、拒绝、过期和参数变化；

- 动作已执行但 API 响应或回执丢失；

- 动作成功返回但服务健康未恢复；

- 补偿动作失败；

- 日志、Runbook 或检索内容包含 Prompt Injection；

- SSE 断线、重连、丢失和重复；

- 1、10、25、50 个并发 Incident 下的队列、P95、数据库连接、Provider Throttling、CPU、内存和费用。

    

Worker Kill Matrix 必须覆盖：



- Tool 调用前后；

- Checkpoint 前后；

- 审批前后；

- 动作提交前；

- 外部动作成功但回执未落库；

- 后置验证前；

- 补偿动作前后。

    

每种结果只能是安全恢复、进入 `UNCERTAIN/MANUAL` 或安全终止，禁止盲目重放写操作。



---



## 七、12–16 周实施顺序



### 第 1 周：工程与服务器基线



- 建立 Monorepo、开发规范、CI、配置和秘密管理。

- 建立 `UPSTREAM.md`、`ORIGINALITY.md`、`THIRD_PARTY.md` 和首批 ADR。

- 在服务器安装 K3s、Helm、存储和观测组件。

- 部署固定版本的 OpenTelemetry Demo。

- 部署 PostgreSQL、Redis、MinIO、Qdrant 和 OPA。

- 建立 LangSmith 环境隔离和最小 Trace。

    

退出条件：PC 提交代码后可部署；Grafana 可查看 SUT Telemetry；LangSmith 可看到包含 Tool Span、版本元数据和脱敏结果的测试 Trace。



### 第 2–3 周：故障实验室与 Ground Truth



- 实现至少一类发布变更和一类配置变更事故。

- 同时实现至少一个无近期变更的非 P0 故障。

- 逐步完成八类故障模板、负载脚本、恢复脚本和健康 Oracle。

- 生成 Scenario Manifest、ChangeEvent、Ground Truth、证据要求和动作约束。

- 禁止 Agent 访问 Ground Truth 和 Chaos Mesh。

    

退出条件：至少 24 个场景变体可重复注入、判定和清理；发布、配置和非变更事故均有完整证据。



### 第 4 周：确定性 Baseline



- 完成告警接入、只读查询工具、简单 RCA 规则和确定性处置流程。

- 建立核心 Schema、Tool Contract、Artifact Store 和基础 Eval。

- 得到首份成功率、延迟和成本基线。

    

退出条件：无需 LLM 也能处理规则明确的事故，形成对照组 A。



### 第 5–6 周：LangGraph 单 Agent



- 实现 Typed State、Checkpoint、Stream、Bounded Loop、恢复和取消。

- 实现 ChangeEvent 摄取、多源证据采集、假设生成、反证验证和报告。

- 接入 LangSmith 全链路 Trace。

- 实现 ReAct Baseline B 和最终候选 C。

- 跑通首个完整纵向切片：ChangeEvent → Evidence → RCA → OPA/Interrupt → 受控修复 → Postcondition。

    

退出条件：Agent 中断后可恢复；重要结论均能定位 EvidenceRef；无证据时会拒答或升级人工。



### 第 7–8 周：知识库与数据流水线



- 实现来源 Registry、许可证校验、解析、去重、脱敏和版本化。

- 完成 Qdrant Hybrid Retrieval、Reranker 和引用。

- 建立 DVC Pipeline 和 TrajectoryIR 导出。

- 导入 ITBench\-Lite 和选定外部测试数据，但保持 Locked Test。

- 建立 Verified Episode Memory 写入门控。

    

退出条件：检索回归通过；任意数据可追溯到来源、版本、许可证和哈希。



### 第 9–10 周：受控修复与安全



- 实现 OPA 策略、风险分级、LangGraph Interrupt 和审批 UI。

- 完成 Action Transaction、Dry\-run、幂等、后置验证和补偿。

- P0 完成 Deployment Rollback 和 Config Restore。

- 建立 Prompt Injection、越权、恶意 Runbook、审批篡改和秘密泄漏测试。

    

退出条件：成功闭环和失败回滚闭环可重复演示；未授权写、审批绕过和重复副作用均为 0。



### 第 11–12 周：LangSmith 评测体系



- 建立所有 LangSmith Dataset 和确定性/Trajectory Evaluator。

- 对 A/B/C/D 配置运行重复实验。

- 增加有无 ChangeEvent、Verifier、Memory 和 Reranker 消融。

- 建立 Online 抽样、人工反馈、Badcase 分类和 Dataset Promotion。

- 使用同一 30\-Case 子集比较至少三个模型通道，按成功率、Schema 合法率、延迟和成本确定角色模型。

    

退出条件：任何 Prompt、模型、Tool 和 RAG 变更都能通过统一命令复测并生成对比报告。



### 第 13–14 周：外部基准与架构消融



- 接入 AIOpsLab 代表性在线任务。

- 运行 ITBench\-Lite、RCAEval RE2/RE3 和 OpenRCA 选定任务。

- 运行 HolmesGPT 和 K8sGPT 共同适用子集的黑盒对比。

- 比较单 Agent、Verifier 和并行 Specialist。

- 验证第二环境 Online Boutique；若工期紧，仅做 Diagnosis\-only 泛化。

- 用无近期变更事故证明系统不会将所有问题误判为变更故障。

    

退出条件：可以回答各设计真实贡献、竞品对比胜负、多 Agent 是否有收益以及未见服务上的退化。



### 第 15–16 周：性能、交付与面试材料



- 完成 1/10/25/50 并发测试和恢复测试。

- 固化 150\+ Core Cases、1,000\+ Trajectories 和实验报告。

- 完成架构文档、威胁模型、数据卡、模型卡、评测卡和来源审计。

- 准备至少 10 个深度 Badcase 复盘。

- 准备三段演示：正常闭环、错误回滚闭环、Worker 崩溃恢复闭环。

- 准备 60 秒、3 分钟、10 分钟和30分钟项目讲述材料。

- 提供一键入口：环境启动、故障注入、单场景运行、核心 Eval 和报告生成。

    

最终退出条件：新环境按文档可复现；所有项目主张均能用代码、Trace、数据和对照实验回答。



如进度延迟，裁剪顺序固定为：



1. 第二外部 Benchmark；

2. Online Boutique 第二 SUT；

3. P1 的 K3s 扩展实验；

4. P1 Episode Memory；

5. 前端视觉优化。

    

不得裁剪：



- 完整应用闭环；

- LangGraph Checkpoint/Interrupt；

- LangSmith Trace/Eval；

- ChangeEvent 和 Evidence 契约；

- OPA、审批、幂等、后置验证和回滚；

- 150\+ Case 和训练就绪数据管线；

- 至少一个竞品黑盒基线。

    

---



## 八、最终交付物与决策门



必须交付：



- 完整源码和基础设施配置。

- 可重复故障实验环境。

- Agent UI、API、LangGraph Runtime 和 Tool Gateway。

- LangSmith Dataset、Experiment 链接和评测报告。

- 150\+ 自有场景、1,000\+ 可追溯轨迹及版本信息。

- 数据源、许可证、SBOM 和第三方资产清单。

- 威胁模型、安全策略和审计示例。

- 架构消融、RAG 消融、模型 Bakeoff 和竞品对比报告。

- 至少 10 个深度 Badcase 复盘。

- SFT、Preference、RL\-ready 数据导出和 Dataset Card。

- `UPSTREAM.md`、`ORIGINALITY.md`、`THIRD_PARTY.md` 和关键 ADR。

- Staging Incident Journal 和可定位的 LangSmith Run ID。

    

正式准入门：



- Agent 核心不是任何 AI SRE 竞品的 Fork 或改名版本。

- 所有第三方代码、SUT 和数据均可追溯。

- P0 演示必须展示变更证据和反证，不能只说“最近发布所以是根因”。

- 修复必须经过独立 Postcondition Verifier。

- 未授权写、审批绕过和重复副作用为 0。

- Checkpoint Kill Matrix 全部通过。

- P0 变更事故子集独立过门。

- 非变更反事实场景不存在系统性盲目回滚。

- 任意简历指标可以由 Git Commit、Dataset Version、配置和 LangSmith Experiment 重算。

- 所有最终根因均能定位到 Evidence、Tool、State Delta 和 OTel Trace。

    

多 Agent 决策门：



- Verifier/Specialist 只有在重复实验中显著改善任务成功率、证据质量或安全性，且成本和延迟可接受时才保留。

- 如果收益仅来自更多 Token、更多调用或 Judge 偏好，则删除多 Agent 层。

- Supervisor/Swarm 不因“面试看起来高级”进入核心架构。

    

训练决策门：



- 数据管线和导出格式必须就绪。

- 实际训练只有满足第四章的数据质量和收益条件后才启动。

- 没有训练结果不影响项目完成；没有训练就绪数据管线则项目未完成。

    

---



## 九、默认假设



- 开发周期为 12–16 周，默认按16周完整路线执行。

- 每周投入约20–30小时。

- PC 只承担编码、Code Review 和轻量单测。

- Ubuntu 服务器约32核、126GB内存、1 GPU、48TB磁盘，具备 sudo 并可长期运行 Staging。

- 首版采用单节点 K3s，不虚构多节点高可用。

- 默认可使用至少两个模型 API 通道，角色模型由 Bakeoff 决定。

- GPU 不是项目卖点，P0 不依赖本地推理。

- 核心代码、数据构建脚本和可再分发的合成数据公开；受许可证限制的数据只提供下载和转换脚本。

- 没有私有垂直数据不改变方案：核心数据来自公开 SUT、自建故障注入、公开文档和外部锁定基准。

- “发布/配置事故为 P0 主线”表示开发和验收优先级，不表示系统只能处理这一类事故。

- 竞品仓库允许阅读、研究和作为黑盒基线，但不作为代码基底或运行依赖。

- LangGraph 是固定主编排框架，LangSmith Trace/Eval 是强制依赖。

- 模型训练不属于交付承诺，训练就绪数据管线属于强制交付。

- FaultWitness 当前只是低冲突工作名，不代表完成正式商标和域名审查。

