# FaultWitness：面向微服务故障诊断与受控修复的 Agent 系统 \- V1

## 一、项目结论



开发一个可验证、可回放、可评测的生产级 SRE Agent：



> 在真实 Kubernetes 微服务中接收告警，自主收集指标、日志、链路、Kubernetes 事件、部署变更和运维知识，形成证据链与根因假设；经策略检查和人工审批后执行有限修复，并验证结果、失败回滚、生成事故报告。
> 
> 



它不是聊天机器人，也不是简单的 RAG 或 ReAct Demo。最终必须形成：



- 一套真实可运行的微服务故障实验环境。

- 一套基于 LangGraph 的持久化、可中断、可恢复 Agent 工作流。

- 一套 LangSmith trace、offline eval、online eval 和 badcase 数据飞轮。

- 一套公开数据获取、知识库构建、故障注入、轨迹生产和训练就绪的数据流水线。

- 一套带权限、审批、审计、幂等、验证和回滚的真实副作用闭环。

- 一份可量化证明设计有效性的实验报告，而不只是一段演示视频。

    

项目优先体现应用 Agent 能力，同时必须包含足以支撑面试追问的 Agent Infra、数据治理、评测和算法优化管线。PC 仅用于开发；Ubuntu 服务器承担 Kubernetes、故障注入、全量数据、批量评测和压力测试。



### 最终演示必须覆盖两条路径



1. 成功闭环：注入故障 → 告警 → 诊断 → 证据链 → 修复方案 → 人工审批 → 执行 → 健康验证 → 自动结案。

2. 失败闭环：错误或无效修复 → 后置条件未满足 → 自动停止或补偿回滚 → 保留现场 → 升级人工处理。

    

### 明确不做



- 不把 LangChain/LangGraph 示例改名包装成项目。

- 不把“调用几个工具”包装成多 Agent。

- 不让模型持有管理员 kubeconfig、任意 Shell 或故障注入权限。

- 不以 LLM\-as\-a\-Judge 作为唯一评测方法。

- 不把训练模型作为项目完成前提；先把数据管线和启动条件做好。

- 不为追求功能数量引入不必要的 supervisor、swarm 或复杂前端。

    

---



## 二、开源基底与采用策略



核心 Agent 从零实现；外部项目分别作为实验环境、数据集、外部基准或设计参考，避免形成“套壳项目”。



|项目|用途|采用方式|
|---|---|---|
|[OpenTelemetry Demo](https://github.com/open-telemetry/opentelemetry-demo)|主业务实验环境|固定上游版本，用 Kustomize/Helm overlay 增加故障、告警和业务约束，不修改其核心源码|
|[LangGraph](https://github.com/langchain-ai/langgraph)|Agent 状态机|核心编排框架；使用 checkpoint、interrupt、stream、reducer 和可恢复执行|
|[LangSmith](https://docs.langchain.com/langsmith/evaluation)|Trace 与评测|所有模型、工具、检索和图节点接入；同时运行 offline/online evaluation|
|[AIOpsLab](https://github.com/microsoft/AIOpsLab)|外部在线基准|编写适配器，选择代表性 detection/localization/analysis/mitigation 场景验证泛化|
|[ITBench](https://github.com/itbench-hub/ITBench)|任务和评测设计参考|对齐其真实 Kubernetes SRE 场景与可解释指标，不复制现成 Agent|
|[ITBench\-Lite](https://huggingface.co/datasets/ibm-research/ITBench-Lite)|离线公开数据|35 个 SRE telemetry snapshot 作为锁定外部测试集|
|[RCAEval](https://github.com/phamquiluan/RCAEval)|RCA 泛化测试|使用 RE2/RE3 多源数据；仅采用许可证明确的基线|
|[OpenRCA](https://github.com/microsoft/OpenRCA)|跨行业 RCA 测试|作为大规模外部诊断基准；ground truth 与 Agent 运行环境物理隔离|
|[HolmesGPT](https://github.com/HolmesGPT/holmesgpt)|工具治理参考|借鉴只读默认、服务端过滤、上下文预算等设计，不依赖其 Agent|
|[K8sGPT](https://github.com/k8sgpt-ai/k8sgpt)|安全与分析器参考|借鉴 analyzer、脱敏和 MCP 边界设计|
|[AgentRx](https://github.com/microsoft/AgentRx)|轨迹诊断参考|借鉴 Trajectory IR 和失败归因体系，构建自己的 badcase pipeline|
|[Chaos Mesh](https://github.com/chaos-mesh/chaos-mesh)|故障注入|在独立命名空间运行，权限不暴露给 Agent|
|[OPA](https://github.com/open-policy-agent/opa)|动作授权|用 Rego 实现确定性风险策略和审批要求|
|[Qdrant](https://github.com/qdrant/qdrant)|知识检索|混合检索、元数据过滤、版本和权限隔离|



以下项目不作为基础：



- Sock Shop：仓库已归档，不作为主环境。

- MicroRemed：场景有参考价值，但许可证和维护成熟度不足。

- OpenSRE：可研究证据化 RCA 设计，但公开版本仍偏早期。

- 已归档的 LangGraph 示例仓库：不进入依赖链。

- 任意缺少明确许可证的代码、数据或 baseline：只能阅读思路，不复制和分发。

    

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

    TG --> OBS["Prometheus / Loki / Tempo<br/>Kubernetes / Git"]
    TG --> ACT["Restricted Action Executor"]
    ACT --> K8S["Target Kubernetes Namespace"]
    CHAOS["Chaos Mesh<br/>独立权限"] --> K8S
    K8S --> OTEL["OpenTelemetry Demo"]
    OTEL --> OBS

    OBS --> OBJ["MinIO Artifact Store"]
    LG --> OBJ
    OBJ --> DATA["DVC Data Pipeline<br/>TrajectoryIR / Parquet / JSONL"]
```



### 3\.2 技术栈



- 后端：Python 3\.12、FastAPI、Pydantic、LangGraph。

- Checkpoint：官方 PostgreSQL checkpointer，生产路径使用异步 saver。

- 业务存储：PostgreSQL。

- 队列、分布式锁、限流、短期缓存：Redis。

- 原始 telemetry、工具大结果、评测产物：MinIO。

- RAG：Qdrant dense\+sparse hybrid retrieval \+ RRF \+ cross\-encoder reranker。

- 策略：OPA/Rego。

- 可观测性：OpenTelemetry Collector、Prometheus、Loki、Tempo、Grafana。

- 前端：React、TypeScript、Vite。

- 数据版本：DVC；Git 只保存 manifest、schema 和流水线定义。

- 模型接入：内部定义 `ModelGateway`，首版直接实现候选供应商适配；第二阶段可在接口后接 LiteLLM，不让业务代码绑定某个网关。

- 密钥：SOPS\+Age 管理加密配置；密钥不进入 trace、浏览器或仓库。

    

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



- 使用强类型 `AgentState`，禁止依赖无结构 message history 表达业务状态。

- 每个节点输入输出有 schema；并行采集通过 reducer 合并。

- 每次重要状态转换写 checkpoint，可以断点恢复和 time travel。

- 等待审批使用 LangGraph `interrupt()`；interrupt 前的副作用必须幂等。

- 设置最大步骤、最大同类工具调用、总时长、token、费用和无进展次数。

- 不保存模型私有思维链；仅保存结构化决策摘要、证据引用、工具调用和状态变化。

- 多 Agent 不是首版默认。先完成单 Agent\+并行工具节点；只有实验表明独立 verifier 或 specialist 显著改善效果，才固化为多 Agent。

    

### 3\.4 状态与公共类型



核心类型至少包括：



- `IncidentCase`：告警、环境、服务范围、时间窗口、状态、预算和版本信息。

- `EvidenceRef`：证据 ID、来源、查询、时间范围、服务、摘要、对象存储 URI、内容哈希。

- `Hypothesis`：根因实体、机制、支持证据、反证、置信度、下一步验证。

- `ActionProposal`：规范化动作、目标、参数、风险级别、dry\-run、前置/后置条件、补偿动作、动作哈希。

- `ApprovalDecision`：动作哈希、决策人、有效期、理由和单次使用 token。

- `ToolEvent`：工具输入摘要、结果引用、耗时、错误、重试和幂等键。

- `TrajectoryIR`：图节点、状态差异、工具事件、模型元数据、结构化决策、人工反馈和最终结果。

- `EvalResult`：数据集、版本、evaluators、指标、费用、延迟和失败标签。

    

状态机枚举：



- Incident：`NEW / INVESTIGATING / WAITING_APPROVAL / EXECUTING / VERIFYING / ROLLING_BACK / RESOLVED / ESCALATED / CANCELLED`。

- Risk：`R0_READ / R1_SAFE_REVERSIBLE / R2_APPROVAL_REQUIRED / R3_FORBIDDEN`。

    

### 3\.5 API 与流式事件



首版固定接口：



- `POST /v1/incidents`：从告警或人工输入创建事件。

- `GET /v1/incidents/{id}`：获取当前状态、证据、假设和动作。

- `GET /v1/incidents/{id}/events`：SSE 流；支持 `Last-Event-ID` 断线重连。

- `POST /v1/incidents/{id}/approvals`：批准或拒绝指定动作哈希。

- `POST /v1/incidents/{id}/cancel`：请求安全取消。

- `POST /v1/incidents/{id}/feedback`：根因、证据、动作和报告反馈。

- 评测和故障注入接口单独鉴权，不暴露给普通用户或 Agent。

    

SSE 只传递带版本的 typed events，例如：



- `incident.status.changed`

- `evidence.added`

- `hypothesis.updated`

- `action.proposed`

- `approval.requested`

- `tool.completed`

- `verification.failed`

- `rollback.completed`

    

数据库采用 transactional outbox，避免 checkpoint 已提交但前端事件丢失。



### 3\.6 工具体系



只读工具：



1. 告警聚合与时间线。

2. PromQL 指标查询和异常检测。

3. LogQL 日志聚合、聚类和样本提取。

4. TraceQL/Tempo 错误链路和 critical path。

5. Kubernetes 对象、事件和状态读取。

6. 服务拓扑构建。

7. Git、配置和部署变更 diff。

8. runbook、文档和历史事故检索。

9. 资源与依赖健康检查。

10. 动作后置条件验证。

    

受控写工具：



- rollout restart。

- scale 调整。

- 回滚到已知 deployment revision。

- 沙箱环境中的白名单配置 patch。

- 执行补偿动作。

    

工具治理：



- 模型只看到工具 schema，不接触 kubeconfig。

- reader 与 action\-executor 使用不同 Kubernetes ServiceAccount。

- Agent 永远拿不到 Chaos Mesh 权限。

- 禁止任意 Shell、任意 URL 和任意 Kubernetes manifest。

- 大结果保存在 MinIO；上下文只注入摘要、统计和 artifact ID。

- 每个写工具必须支持 dry\-run、幂等键、前置条件、后置条件、超时、审计和补偿。

- MCP 可以作为工具接入协议，但安全边界仍由服务端 gateway 和 OPA 保证。

    

---



## 四、公开数据、RAG 与训练就绪流水线



### 4\.1 数据来源优先级



1. 自己运行微服务并注入故障产生的真实 telemetry。

2. 有许可证、可固定 commit 的官方仓库和文档。

3. ITBench\-Lite、RCAEval、OpenRCA 等公开基准。

4. 自己编写的 runbook、故障模板和变更记录。

5. 公开事故复盘仅作为补充知识，不作为核心 ground truth。

    

不以无边界网页爬虫开局。知识获取采用 allowlist registry，每个来源记录：



- URL或仓库。

- commit、版本或抓取时间。

- 许可证和允许用途。

- 内容哈希。

- 原始文件位置。

- 更新频率。

- 是否允许重新分发。

    

对于没有明确再分发许可的网页，只保存 URL、必要元数据和原创摘要；不把全文提交到公开仓库。



### 4\.2 自建核心场景集



以 OpenTelemetry Demo 为主环境，首版构建不少于 8 类故障：



- CPU/内存资源耗尽。

- Pod crash 或 readiness/liveness 异常。

- 服务配置错误。

- 下游依赖超时。

- 网络延迟、丢包或连接失败。

- 数据库/消息队列依赖异常。

- 错误版本部署或端口配置错误。

- 单实例、容量和扩缩容问题。

    

每类至少包含：



- 多个服务落点或难度。

- 3 个随机种子/负载条件。

- 明确 ground truth。

- 起止时间、前置状态和恢复条件。

- 正确诊断所需证据。

- 合法动作、非法动作和可接受替代动作。

- 是否应修复、回滚或升级人工。

    

核心数据集目标：



- 72 个 live scenario variants。

- 24 个安全/提示注入/越权案例。

- 18 个模型、工具和依赖失败案例。

- 18 个 RAG 版本、引用和权限案例。

- 18 个噪声、冲突证据和 OOD 案例。

- 总计不少于 150 个自有可控评测案例；外部 benchmark 不计入这 150 个。

    

### 4\.3 RAG 实现



采集内容：



- OpenTelemetry Demo 代码、配置和部署 manifest。

- Kubernetes、OpenTelemetry、Prometheus、Grafana、Chaos Mesh 官方文档。

- 项目 runbook、服务目录、SLO 和故障处置规范。

- Git 变更、部署历史和历史事故报告。

    

索引管线：



```Plain Text
acquire
→ license_validate
→ parse
→ normalize
→ redact
→ structure-aware chunk
→ deduplicate
→ enrich metadata
→ embed
→ sparse index
→ Qdrant upsert
→ retrieval regression test
```



检索策略：



- 结构化 metadata 先过滤环境、服务、版本、权限和有效时间。

- dense\+sparse 检索后使用 RRF 融合。

- cross\-encoder 对候选重排。

- 返回父文档上下文和精确引用。

- 模型结论必须引用 `EvidenceRef` 或知识文档 ID。

- 对 dense\-only、sparse\-only、hybrid、hybrid\+reranker 做消融实验。

    

长期知识与事件记忆严格分离。事故经验只有在人工确认、质量校验、冲突检查和过期策略通过后才能写入 episodic memory。



### 4\.4 数据与算法优化 pipeline



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



- 指标、日志统计、trace features：Parquet。

- Agent 轨迹和标签：JSONL。

- 场景、ground truth、动作约束：YAML。

- 大型原始对象：MinIO\+DVC。

- Schema、manifest 和流水线：Git。

    

数据切分不能随机按行切分，必须按 fault family、环境、服务、场景模板分组，避免同源泄漏。外部 benchmark 永远作为锁定测试集；ground truth 不能挂载到 Agent 可见的容器或检索库。



生成训练数据时只保存工具调用、结果、结构化决策摘要和人工标签，不收集私有思维链。



只有同时满足以下条件才进入微调实验：



- 已有不少于 500 条经审计的高价值成功/失败轨迹或偏好对。

- 失败集中在模型可学习且能稳定标注的类别。

- prompt、工具、检索和确定性流程优化已进入平台期。

- 标注一致性达到预设门槛。

- 有独立验证集且训练收益能够覆盖维护成本。

    

ITBench Trajectories 等非商业许可数据单独存放，不与计划公开或商业可用的数据混合。



---



## 五、LangSmith Trace、评测与实验设计



### 5\.1 Trace 规范



所有 LangGraph 根运行、节点、模型、工具、检索和 evaluator 都接入 LangSmith。每条根 trace 至少携带：



- `git_sha`

- `graph_version`

- `prompt_version`

- `tool_schema_version`

- `dataset_version`

- `rag_index_version`

- `model_provider/model_name`

- `scenario_id/fault_id`

- `incident_id/task_id`

- token、费用、延迟、重试次数

- LangSmith run ID 与 OpenTelemetry trace ID 的互链字段

    

LangSmith 用于交互式调试、数据集、实验对比和在线抽样；本地 PostgreSQL、MinIO 和 TrajectoryIR 是长期可迁移的事实源。由于 LangSmith Developer 计划的基础 trace 保留期有限，应把失败、人工复核和高价值运行提升到 LangSmith dataset，并同步保存本地轨迹。[官方价格与保留策略](https://www.langchain.com/pricing)



### 5\.2 固定对照组



必须实现四种可切换实验配置：



- A：确定性诊断工作流，不使用自主循环。

- B：通用 ReAct 单 Agent。

- C：最终的证据驱动、有界 LangGraph Agent。

- D：加入独立 verifier 或 specialist 的版本。

    

D 只有在重复实验中对任务成功率、证据质量或成本有明确收益时才进入最终架构，否则保留 C，避免为了多 Agent 而多 Agent。



### 5\.3 LangSmith 数据集



建立相互隔离的数据集：



- `core-live-diagnosis-remediation`

- `rag-citation-regression`

- `tool-reliability-recovery`

- `security-policy-adversarial`

- `itbench-lite-external`

- `rcaeval-openrca-external`

    

每次 prompt、模型、工具 schema、图结构、检索策略或知识版本变更，都运行对应 offline eval。演示和真实测试流量使用 online evaluator 抽样；失败 trace 经复核后加入 regression dataset。



### 5\.4 Evaluator 分层



优先使用确定性 evaluator：



- 根因实体和机制匹配、Top\-k 命中。

- 必需证据覆盖。

- 工具选择、schema、参数和调用顺序。

- 权限、审批、动作哈希和策略符合性。

- 动作执行、后置条件、回滚和最终服务健康。

- 引用存在、引用支持性、版本和 ACL。

- 死循环、重复查询、预算和无进展检测。

- 延迟、token、成本和工具错误率。

    

LLM evaluator 只评估难以规则化的部分：



- 诊断解释是否与证据一致。

- 是否主动寻找反证。

- 事故报告是否完整、清晰、不过度推断。

- 两个轨迹之间的相对质量。

    

Judge 尽量使用不同模型供应商或模型家族；隐藏被评系统名称；随机抽取 10%–20% 结果双人复核，报告 judge 与人工一致性。LangSmith 的 trajectory evaluators 用来评完整工具路径，而非只看最终回答。[Evaluator 类型说明](https://docs.langchain.com/langsmith/evaluators)



### 5\.5 规模与验收门槛



至少运行 1,000 条完整轨迹，覆盖：



- 模型与参数变化。

- 4 个对照组。

- 多随机种子和多次重复。

- 正常、困难、噪声、工具故障和安全场景。

    

初始发布门槛：



- 常规核心场景端到端成功率 ≥80%。

- 困难场景成功率 ≥60%。

- 根因 Top\-3 与证据质量显著优于 ReAct baseline。

- 工具 schema 合法率 ≥99%。

- 可重试工具最终成功率 ≥95%。

- RAG Recall@10 ≥90%。

- 引用正确率 ≥95%。

- 无证据支持的重要结论 ≤3%。

- 死循环率 \<1%。

- 未授权写操作必须为 0。

- 任何 R2 动作绕过审批必须为 0。

- action 成功但健康未恢复时，必须进入回滚或升级人工，不得错误结案。

    

成功率门槛可在 baseline 后向上校准，但安全零容忍指标不得降低。结果报告必须包含置信区间、重复次数、模型版本、成本和失败分布。



---



## 六、安全、可靠性与部署



### 6\.1 权限模型



- `R0_READ`：只读，可自动执行。

- `R1_SAFE_REVERSIBLE`：仅允许明确白名单、可逆且可验证的动作。

- `R2_APPROVAL_REQUIRED`：必须 LangGraph interrupt 等待人工批准。

- `R3_FORBIDDEN`：删除数据、任意命令、修改安全边界等永远拒绝。

    

审批 token 绑定动作哈希、操作者、有效期和单次消费。任何动作参数变化都会使旧审批失效。



使用 OPA 做最终确定性裁决；LLM 只能提出风险判断，不能覆盖策略。



### 6\.2 服务端部署



服务器采用 K3s，建议命名空间：



- `faultwitness-system`：Agent、API、数据服务和前端。

- `faultwitness-target`：OpenTelemetry Demo。

- `faultwitness-chaos`：Chaos Mesh。

- `faultwitness-bench`：外部 benchmark 和批量实验。

    

要求：



- namespace network policy、resource quota 和独立 ServiceAccount。

- PostgreSQL、MinIO、Qdrant 使用持久卷并定期快照。

- Grafana、LangSmith key、审批接口只通过 LAN/VPN/SSH 隧道访问。

- PC 通过 Remote SSH 开发；本地只运行单元测试和轻量组件。

- 首次执行计划通过 `nvidia-smi` 确认 GPU 型号。GPU 仅用于本地 embedding、reranker 或小模型实验，P0 不依赖它。

- 公共 GitHub Actions 只运行单测、契约测试、静态检查和无特权集成测试；PR 不得触发服务器上的特权 runner。

- 完整故障注入和修复评测仅在受控服务器手动触发。

    

### 6\.3 可靠性验证



必须覆盖：



- 模型 429、5xx、超时、无效结构化输出。

- 工具超时、部分结果、重复返回和 schema 变化。

- worker 在 checkpoint 前后被杀死。

- 消息重复投递。

- PostgreSQL、Redis 或对象存储短时不可用。

- 审批超时、拒绝和动作内容变化。

- 动作已执行但 API 响应丢失。

- 修复动作成功返回但服务健康未恢复。

- 检索内容包含 prompt injection 或恶意操作建议。

- SSE 断线、重连和事件重复。

- 1、10、25、50 个并发 incident 下的队列、P95、数据库连接、provider throttling、CPU、内存和费用。

    

---



## 七、12–16 周实施顺序



### 第 1 周：工程与服务器基线



- 建立 monorepo、Python/前端开发规范、CI、配置和秘密管理。

- 在服务器安装 K3s、Helm、存储、观测组件。

- 部署固定版本的 OpenTelemetry Demo。

- 建立 PostgreSQL、Redis、MinIO、Qdrant、OPA。

- 完成 LangSmith 项目、环境隔离和最小 trace 验证。

    

退出条件：从 PC 提交代码后，可在服务器部署；Grafana 能看到目标系统 telemetry；LangSmith 能看到一条包含工具 span 的测试 trace。



### 第 2–3 周：故障实验室与 ground truth



- 实现首批 8 类故障模板、负载脚本、恢复脚本和健康 oracle。

- 生成 scenario manifest、ground truth、证据要求和动作约束。

- 建立故障前后 telemetry 快照和内容哈希。

- 禁止 Agent 访问 ground truth 和 Chaos Mesh。

    

退出条件：至少 24 个场景变体可以重复注入、自动判定和自动清理。



### 第 4 周：确定性 baseline



- 完成告警接入、查询工具、简单 RCA 规则和确定性处置流程。

- 建立核心 schema、工具契约、artifact store 和基础评测。

- 得到首份成功率、延迟和成本基线。

    

退出条件：无需 LLM 也能完成一部分固定场景，形成后续对照组 A。



### 第 5–6 周：LangGraph 单 Agent



- 实现 typed state、checkpoint、stream、bounded loop、恢复和取消。

- 实现证据采集、假设生成、反证验证和事故报告。

- 接入 LangSmith 全链路 trace。

- 实现 ReAct baseline B 和最终候选 C。

    

退出条件：Agent 中断后可恢复；每个重要结论可追溯到 EvidenceRef；无证据时能正确升级而非猜测。



### 第 7–8 周：知识库与数据流水线



- 实现来源 registry、许可证校验、解析、去重、脱敏和版本化。

- 完成 Qdrant hybrid retrieval、reranker 和引用。

- 建立 DVC pipeline 与 TrajectoryIR 导出。

- 导入 ITBench\-Lite 和选定外部测试数据，但保持 locked test。

    

退出条件：检索回归集通过；任何数据可追溯到来源、版本、许可证和哈希。



### 第 9–10 周：受控修复与安全



- 实现 OPA 策略、风险分级、LangGraph interrupt 和审批 UI。

- 完成 action executor、dry\-run、幂等、后置验证和回滚。

- 建立提示注入、越权、恶意 runbook 和秘密泄漏测试。

    

退出条件：完整成功闭环和失败回滚闭环可重复演示；未授权写操作为 0。



### 第 11–12 周：LangSmith 评测体系



- 建立所有 LangSmith datasets 和确定性/trajectory evaluators。

- 对 4 个配置运行重复实验。

- 建立在线抽样、人工反馈、badcase 分类和 dataset promotion。

- 完成模型 bakeoff：同一 30\-case 子集比较至少 3 个候选模型通道，按成功率、schema 合法率、延迟和成本选择角色模型。

    

退出条件：任何 prompt、模型、工具和 RAG 改动都能通过统一实验命令复测并生成对比报告。



### 第 13–14 周：外部基准与架构消融



- 接入 AIOpsLab 代表性在线任务。

- 运行 ITBench\-Lite、RCAEval RE2/RE3 和 OpenRCA 选定任务。

- 比较单 Agent、独立 verifier、并行 specialist。

- 验证第二环境 Online Boutique；若工期紧，只做 diagnosis\-only 泛化，不扩大修复范围。

    

退出条件：能够清晰回答哪些设计真正贡献了效果、哪些多 Agent 设计无收益，以及系统在未见服务上的退化程度。



### 第 15–16 周：性能、交付与面试材料



- 完成 1/10/25/50 并发测试和故障恢复测试。

- 固化 150\+ core cases、1,000\+ trajectories 和实验报告。

- 准备架构文档、威胁模型、数据卡、模型卡、评测卡、复现实验命令。

- 准备 10 分钟演示、30 分钟技术深挖和典型 badcase 复盘。

- 输出 one\-command 入口：环境启动、故障注入、单场景运行、核心评测和报告生成。

    

最终退出条件：新环境按文档可复现；面试中所有核心设计都能用代码、trace、数据和对照实验回答，而不是依靠口头设想。



---



## 八、最终交付物与决策门



必须交付：



- 完整源码和基础设施配置。

- 可重复故障实验环境。

- Agent UI、API、LangGraph runtime 和工具服务。

- LangSmith datasets、experiment 链接和评测报告。

- 150\+ 自有场景、1,000\+ 轨迹及其版本信息。

- 数据源与许可证清单。

- 威胁模型、安全策略和审计示例。

- 架构消融、RAG 消融和模型 bakeoff 报告。

- 至少 10 个深度 badcase 复盘。

- 训练就绪数据导出，但不以模型训练结果作为验收条件。

    

是否加入正式多 Agent，由消融实验决定：



- 如果 verifier/specialist 在重复实验中带来显著成功率或安全收益，且成本和延迟可接受，则保留。

- 如果收益只来自更多 token、更多调用或 judge 偏好，则删除多 Agent 层。

- supervisor/swarm 不因“面试看起来高级”而进入核心架构。

    

## 九、默认假设



- 服务器为 Ubuntu、32 核、126GB 内存、1 GPU、48TB 磁盘，可供项目长期独占或稳定使用，并具备 sudo 权限。

- PC 仅承担编码、代码审查和轻量单测，不要求本地 Kubernetes。

- 默认每周投入约 20–30 小时；若显著少于此范围，应优先保留 LangGraph、LangSmith、核心故障闭环和评测，缩减第二环境与外部 benchmark 数量。

- 默认可使用至少两个模型 API 通道；具体模型不预先绑定，通过第 11–12 周 bakeoff 确定。

- 默认公开核心代码、数据构建脚本和可再分发的合成数据；受许可证限制的数据仅提供下载和转换脚本。

- 默认部署在受控实验服务器，不直接取得真实生产集群权限。

- 默认首版采用单节点 K3s；只有资源隔离或并发测试证明确有需要，才扩展为多节点。

