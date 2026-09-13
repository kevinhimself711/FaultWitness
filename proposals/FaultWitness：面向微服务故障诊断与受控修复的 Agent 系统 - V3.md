# FaultWitness：面向微服务故障诊断与受控修复的 Agent 系统 \- V3

# FaultWitness 最终项目规划：Documentation\-first、Gate\-driven



## 1\. 总体决策



### 项目定义



在 `D:\项目\Agent项目筹备\FaultWitness` 新建独立 Git monorepo，当前目录继续作为不公开的调研资料库。



FaultWitness 定义为：



> 面向微服务事故调查、受控修复与持续优化的多租户 Agent Runtime。
> 
> 



项目不是任意领域的通用 Agent 平台，也不是仅处理发布错误的回滚 Agent：



- 主要深度主线：发布、配置、路由、版本变更的因果归因与安全回滚。

- 必须覆盖的泛化故障：资源/容量、依赖/网络/数据面、Pod/运行时/重试。

- 主 SUT：固定 commit 的 OpenTelemetry Demo。

- 第二 SUT：Online Boutique，仅做诊断泛化，不复制完整修复面。

- 外部锁定基准：ITBench\-Lite；其他 benchmark 不进入主完成条件。

- 支持四种类型化写动作：Deployment rollback、Config restore、Rollout restart、Scale workload。

- 不建设插件市场、跨地域高可用、任意云厂商接入、真实生产运维或公网执行入口。

    

### 三个强制工程平面



1. Agent Application

LangGraph 状态机、证据推理、RAG、Memory、Skills、工具调用、审批、修复验证和 Incident Console。



2. Agent Runtime/Infra

多租户身份与隔离、任务调度、租约/心跳、checkpoint、暂停/恢复/取消、沙箱、策略执行、水平扩展和 AgentOps。



3. Data/Eval/Training

Scenario DSL、TrajectoryIR、数据版本、LangSmith Eval、badcase、SFT/DPO/GRPO 数据与训练管线。



三者代码和部署解耦，但共同构成项目完成条件。训练代码放在后期实现，但 `TrajectoryIR`、数据版本、模型/Prompt/Tool 版本和 Ground Truth 从第一个运行开始记录。



### 已锁定约束



- 不设总期限，严格按 Gate 推进。

- 专业服务器、K3s、4090、充足 CPU/内存和国内主流模型 API 可用。

- LangSmith 是 Agent Trace、Dataset、Experiment 和 Eval 的强依赖。

- 本地 PostgreSQL、MinIO、DVC 继续保存运行状态、训练导出和重要证据副本。

- SFT、DPO、GRPO 三条训练路径都必须在 4090 上做极小规模真实 smoke run，但不承诺正式训练收益。

- 开发期仓库私有；安全纵切和来源审计通过后公开代码与脱敏证据。

- 服务只通过 LAN/VPN/SSH Tunnel 访问，公开内容采用录屏和可复现实验。

- 根 `AGENTS.md` 全英文；其他文档中文正文、英文代码/API/Schema 标识符。

    

---



## 2\. 第 0 工程平面：文档、证据与提交治理



### 初始仓库资产



```Plain Text
FaultWitness/
├─ AGENTS.md
├─ README.md
├─ PROJECT_STATE.yaml
├─ CHANGELOG.md
├─ Makefile
├─ docs/
│  ├─ blueprint/FINAL_PLAN.md
│  ├─ requirements/
│  │  ├─ REQUIREMENTS.yaml
│  │  └─ EVIDENCE_MATRIX.md
│  ├─ roadmap/
│  │  ├─ PHASES.md
│  │  └─ iterations/I-xxxx.md
│  ├─ gates/Gxx/{PLAN.md, REPORT.md}
│  ├─ evals/EVAL-xxxx/{PLAN.md, REPORT.md, manifest.json}
│  ├─ claims/CLAIMS.yaml
│  ├─ adr/ADR-xxxx.md
│  ├─ badcases/BC-xxxx.md
│  ├─ security/THREAT_MODEL.md
│  ├─ data/DATA_CARD.md
│  ├─ models/MODEL_CARD.md
│  ├─ operations/{RUNBOOK.md, INCIDENT_JOURNAL.md}
│  ├─ engineering/AI_DEVELOPMENT_LOG.md
│  └─ provenance/{UPSTREAM.md, ORIGINALITY.md, THIRD_PARTY.md}
├─ apps/
├─ packages/
├─ evals/
├─ training/
├─ infra/
└─ scripts/
```



大型数据、原始 Trace 和模型权重进入 MinIO/DVC；Git 只保存 Schema、DVC hash、配置、指标、报告和证据链接。



### 根 `AGENTS.md` 必须固化的规则



- 项目使命、产品边界、非目标和三平面完成定义。

- 修改前必须读取 `PROJECT_STATE.yaml`、当前 Gate 和当前 Iteration。

- 没有 `I-xxxx.md` 不得开始行为变更。

- 不得在同一次实现变更中降低 Gate 阈值或修改 locked test。

- 不得为了让当前实现通过而改 Ground Truth。

- Prompt、Model、Tool、Skill、Policy、Dataset 和 Schema 全部版本化。

- 任何功能主张必须映射到 `CLAIMS.yaml` 中的代码、测试和 Eval 证据。

- 禁止提交密钥、原始 JD/面经、私有 Trace、模型隐藏思维链或未脱敏数据。

- Agent 不得获得管理员 kubeconfig、任意 shell、Chaos 权限或生产式数据库写权限。

- 行为变更必须同时更新受影响文档、测试和版本清单。

- 未通过 Gate 时保留失败报告，不得覆盖或删除 badcase。

- 规定本地、公共 CI、服务器特权测试分别允许执行的命令。

- 规定代码、注释、API、Schema 使用英文；项目文档正文使用中文。

    

在 `evals/locked`、`infra` 和 `training` 下增加局部 `AGENTS.md`，分别禁止测试集泄漏、未授权特权操作和训练数据污染。



### 需求和证据分层



`REQUIREMENTS.yaml` 为每项要求分配稳定 ID：



- Tier A：原始 JD 与原始面试问题。

- Tier B：立项报告中的综合结论。

- Tier C：面经合集中的辅导答案，仅作问题提示，不作为指标或事实依据。

    

每条强制要求必须包含：



```YAML
id:
role_tracks:
source_tier:
source_refs:
requirement:
planned_gate:
implementation_status:
evidence_ids:
```



原始 JD/面经不进入公开仓库。仓库只保存转述后的矩阵；本地 `.gitignore` 文件 `evidence.local.yaml` 保存源 ID 到本机路径的映射。



### Iteration、Commit、Eval、Gate 生命周期



1. 开始一轮实现前创建 `I-xxxx.md`，锁定假设、改动范围、受影响 Requirement、测试集、预期指标、回滚方式和 Gate 影响。

2. 使用短分支开发；行为变更与必要文档进入同一 commit。

3. Commit 使用 Conventional Commits，并带 Trailer：

    

```Plain Text
Iteration: I-0012
Requirements: REQ-AGENT-004, REQ-EVAL-007
Eval: EVAL-0041
```



4. 每个 commit 运行 `make verify-fast`；行为变化运行 `make eval-changed`。

5. CI 根据 commit SHA 生成不可变 Eval manifest，不自动回写仓库。

6. 原始结果进入 LangSmith、MinIO/DVC 和 CI Artifact。

7. Iteration 通过后，专门的关闭 commit 更新 Iteration、Eval 报告、Claims、Changelog 和 `PROJECT_STATE.yaml`。

8. 阶段 Gate 通过后，使用仅含资产更新的 Gate 关闭 commit，并打 `gate/Gxx-vN` 标签。

9. Gate 失败时保留 `REPORT.md`、失败指标和 badcase，状态不得前移。

    

`manifest.json` 至少记录：



- evaluated commit SHA；

- Dataset/DVC hash；

- Provider、Model、Prompt、Tool、Skill、Policy、Schema 版本；

- 环境、硬件、随机种子和命令；

- LangSmith Experiment URL；

- MinIO/DVC Artifact；

- 指标、置信区间、失败分布和状态。

    

### 自动门禁



实现以下命令：



- `make verify-fast`：格式、静态检查、单测、契约测试、文档 Schema、链接、密钥扫描。

- `make eval-changed`：按变更矩阵运行受影响的快速回归集。

- `make eval-gate G=Gxx`：运行指定 Gate 的冻结测试。

- `make close-iteration I=... RUN=...`：验证证据后生成关闭资产。

- `make close-gate G=... RUN=...`：验证 Gate 条件并更新项目状态。

    

CI 必须检查“代码路径—必需资产”映射：



- API/Schema 变化：契约、接口文档和兼容测试。

- Graph/Prompt/Model 变化：版本清单和目标 badcase Eval。

- Tool/Skill 变化：权限、风险、Schema 和回归集。

- Dataset/Ground Truth 变化：Data Card、DVC hash 和泄漏检查。

- Policy/Sandbox/Infra 变化：Threat Model、Runbook 和安全测试。

- 修复 bug：新增对应 badcase 和永久回归用例。

    

---



## 3\. 架构与公共契约



### 技术栈



- Python 3\.12、FastAPI、Pydantic、LangGraph。

- React、TypeScript、Vite。

- PostgreSQL：Incident、租户、审批、审计、checkpoint、task lease、outbox。

- Redis：缓存、限流、短租约和非权威事件广播。

- Qdrant：Dense＋Sparse＋RRF＋Cross\-encoder，ACL 前置过滤。

- MinIO＋DVC：Telemetry、Dataset、Eval Artifact 和训练资产。

- Keycloak/OIDC：用户、租户和角色认证。

- OPA/Rego：动作和资源策略。

- K3s、Helm、NetworkPolicy、ResourceQuota。

- OpenTelemetry、Prometheus、Loki、Tempo、Grafana。

- LangSmith：强制 Trace、Dataset、Experiment 和 Evaluator 平台。

- SOPS＋Age：密钥与配置。

- TRL、PEFT、bitsandbytes、Accelerate：训练 smoke pipeline。

    

### 服务边界



- Control API：认证、Incident API、审批、反馈和 SSE。

- Scheduler：PostgreSQL 队列、优先级、deadline、lease、heartbeat、backpressure。

- Agent Worker：LangGraph 执行、checkpoint 和恢复。

- Tool Gateway：工具注册、参数校验、ACL、结果外置和 MCP Adapter。

- Action Executor：唯一写入口，执行 OPA、审批、幂等和补偿。

- Knowledge/Memory Service：知识、Episode、偏好和 Context Packing。

- Eval/Data Worker：轨迹导出、评测、badcase 和训练数据构建。

- Incident Console：证据、假设、状态、审批、回放和 Eval 对比。

    

### 核心类型



必须首先以 Pydantic＋JSON Schema 固化：



- `TenantContext`

- `IncidentSpec`

- `ChangeEvent`

- `AgentState`

- `EvidenceRef`

- `Hypothesis`

- `ProbePlan`

- `ToolDefinition`、`ToolCall`、`ToolResult`

- `SkillManifest`

- `ActionProposal`

- `ApprovalGrant`

- `ActionTransaction`

- `TrajectoryIR`

- `EvalResult`

    

所有 Schema 使用 SemVer，并把 Schema hash 写入 LangSmith Trace。



### 固定 API



- `POST /v1/incidents`

- `GET /v1/incidents/{incident_id}`

- `GET /v1/incidents/{incident_id}/events`

- `POST /v1/incidents/{incident_id}/approvals`

- `POST /v1/incidents/{incident_id}/cancel`

- `POST /v1/incidents/{incident_id}/feedback`

- `GET /v1/tools`

- `GET /v1/skills`

    

`tenant_id` 只从 OIDC/JWT 得到，不接受客户端在请求体中指定。SSE 使用递增 `event_id` 和 `Last-Event-ID` 断线续传。



### Agent 和安全边界



- 默认架构：单 Orchestrator＋确定性并行 Evidence Collectors。

- Multi\-Agent 仅作为 Planner/Investigator/Verifier 消融方案。

- 模型只能提出 ToolCall 和 ActionProposal，不能直接执行 shell 或 Kubernetes API。

- Action 状态固定为：

    

```Plain Text
prepared → approval_pending → approved → executing → verifying
→ committed
or compensating → rolled_back
or uncertain/manual
```



- 所有写操作绑定不可变 Action Digest、目标资源版本、前后置条件、审批人、有效期和单次消费 token。

- 至少一次任务投递＋动作幂等，不宣称分布式 exactly\-once。

- 诊断脚本只进入临时 Kubernetes Sandbox Job。

- Sandbox 必须使用 gVisor；若服务器探测不兼容，则转 Kata Containers。两者均不可用时 Infra Gate 失败，不得把普通容器包装成强沙箱。

- Sandbox 禁用 ServiceAccount token、hostPath、特权模式和默认网络；只读根文件系统、非 root、drop capabilities，并限制 CPU、内存、PID 和时长。

    

### ModelGateway



实现智谱 GLM、DeepSeek、阿里云百炼 Qwen Adapter，统一：



- Tool Calling；

- Structured Output；

- Streaming；

- timeout/retry/fallback；

- Token、费用和限流；

- Prompt 与模型版本；

- LangSmith Trace。

    

角色模型通过同一冻结子集 bakeoff 决定。先过滤安全和 Schema 不合格模型，再选择质量最高者；质量差距不超过 2 个百分点时选择成本更低者，成本差距不超过 10% 时选择延迟更低者。



---



## 4\. 实施阶段与详细 Gate



所有 Gate 的安全、权限、租户隔离和 locked\-test 泄漏指标均不可豁免。实验结果为负不代表 Gate 失败；只要实验预注册、执行完整、结论与数据一致，可以保留简单方案。



### G00：蓝图与治理基线



实现：



- 初始化独立 Git monorepo、Apache\-2\.0 License、分支保护和 CI。

- 创建全部文档骨架、AGENTS、状态 Schema、Requirement/Evidence/Claims Registry。

- 固化变更—资产同步矩阵和 Gate 运行器。

    

Eval：



- 空仓库 bootstrap；

- 文档 Schema、链接、密钥与许可证扫描；

- 用测试 fixture 验证 CI 能拒绝缺少计划、测试或文档的行为变更。

    

通过标准：



- 100% 强制 Requirement 有 source、role track、planned Gate。

- 所有阶段已有冻结 Gate 模板。

- `PROJECT_STATE.yaml` 可由机器校验。

- CI 能正确拒绝至少四类资产漂移。

- 原始 JD、面经和密钥均不在 Git 历史中。

    

### G01：平台、契约与 Trace 地基



实现：



- 部署 K3s、PostgreSQL、Redis、Qdrant、MinIO、Keycloak、OPA、观测组件。

- 固化核心 Schema、租户字段、ModelGateway 和 LangSmith Instrumentation。

- 探测并记录服务器、4090、gVisor/Kata 能力。

    

Eval：



- 三个模型 Provider 分别完成 Structured Output、Tool Calling、Streaming、timeout/fallback smoke。

- 全链路 Trace、脱敏和 Artifact 外置测试。

- 从干净环境按 Runbook 重建。

    

通过标准：



- 100% 根运行、模型、工具和检索 Span 包含 code SHA、tenant、incident 和全部版本。

- 三个 Provider smoke 全部通过。

- Trace 和日志密钥泄漏为 0。

- 数据库、向量库、对象存储均执行租户范围测试。

- 训练相关 `TrajectoryIR`、SFT、Preference、GRPO record Schema 已冻结。

    

### G02：故障实验室与基线



实现：



- 固定 OpenTelemetry Demo commit。

- 建立四类故障 Scenario DSL。

- 完成首批 32 个可执行种子场景，每类 8 个。

- 预注册最终 160 个核心 case：80 dev、40 validation、40 locked test，每类故障按 20/10/10 均衡。

- locked test 和 Ground Truth 使用独立 MinIO bucket、身份和命名空间。

- 实现确定性 Workflow、Naive ReAct 和无 RAG 基线。

    

Eval：



- 每个种子故障执行注入、观测和恢复三次。

- 三个基线使用相同模型预算、工具范围和随机种子。

- 锁定最终质量指标与阈值。

    

通过标准：



- 32/32 故障连续三次可重现并可恢复。

- Agent 和普通开发凭证无法读取 locked Ground Truth。

- 基线报告包含 95% bootstrap CI、成本、Token、延迟和失败分布。

- 最终发布下限被冻结，之后只能提高：

    

    - Core E2E Success ≥ `max(70%, best baseline + 10pp)`；

    - Root\-cause Top\-3 ≥ 85%；

    - Evidence precision ≥ 90%；

    - Unsupported critical claim ≤ 2%；

    - Tool schema validity ≥ 99%；

    - Dead/no\-progress loop \< 1%；

    - 任一故障族成功率不得低于 55%。

        

### G03：只读 Agent 纵切



实现：



- LangGraph Typed State、Reducers、checkpoint、interrupt 和预算。

- Incident API、Scheduler/Worker 最小版本、SSE/Outbox。

- Evidence、Hypothesis、ProbePlan 和 ChangeEvent。

- 首批 Prometheus、Loki、Tempo、Kubernetes、Git/Deployment 工具。

- Incident Console 最小闭环。

    

Eval：



- 四类故障的 read\-only 诊断。

- 模型 429/5xx、错误 JSON、工具 timeout、Worker kill、SSE 重连。

- ChangeEvent 与症状时间/拓扑/版本不一致的反事实场景。

    

通过标准：



- Validation E2E 比最佳基线至少提高 5pp。

- 100% 关键结论能回溯到 EvidenceRef。

- Worker 恢复后不丢失已提交状态。

- SSE 重连不丢事件且不重复改变状态。

- 无预算越界、无限循环或未经工具验证的“已执行”陈述。

    

### G04：RAG、Memory、Skills 与多模态



实现：



- PDF/Markdown/HTML/表格/架构图和 Dashboard 截图摄取。

- Dense、Sparse、Hybrid、RRF、Reranker 和精确引用。

- Working State、Knowledge、Episode、Team Preference、Conversation Summary 五类数据生命周期。

- 3–5 个领域 Skill，包含 trigger、anti\-trigger、tools、risk、examples 和独立 Eval。

- 静态工具与动态 Tool/Skill Retrieval 两条路径。

    

Eval：



- Dense/Sparse/Hybrid/Reranker 消融。

- OCR\-only 与 VLM extraction 比较。

- Memory on/off、过期记忆、冲突记忆和恶意知识注入。

- Static all\-tools 与动态检索比较。

    

通过标准：



- Retrieval Recall@10 ≥ 85%，Citation precision ≥ 90%。

- Hybrid/Reranker 没有收益时必须回退更简单方案并保留负结果。

- 动态 Tool/Skill 进入默认路径的条件：Context Token 至少下降 20%，E2E 非劣界不低于 \-2pp。

- Episode Memory 进入默认路径的条件：重复事故成功率提高至少 5pp，且过期记忆不产生关键危险动作。

- 多模态结构字段 F1 ≥ 90%；否则只保留结构化/人工确认 fallback。

    

### G05：受控修复与动作事务



实现：



- Deployment rollback、Config restore、Rollout restart、Scale workload。

- OPA 风险分级、Action Digest、人工审批、资源版本检查。

- 后置验证、补偿、uncertain/manual 和审计。

- Lab 环境允许严格白名单的 R1 自动动作；R2 始终人工审批。

    

Eval：



- 审批绕过、审批过期、参数篡改、重放、重复消息和并发审批。

- Action 执行前后 Worker kill。

- 动作成功但服务健康未恢复。

- 补偿失败和结果不可确认。

    

通过标准：



- 未授权写、审批绕过、Digest 篡改接受、越权资源操作均为 0。

- 重复任务导致重复外部副作用为 0。

- 支持动作后置验证成功率 ≥ 95%。

- 验证失败进入补偿或人工升级的比例为 100%。

- 每种写动作至少 10 个独立 case，并执行 3 次。

- Gate 通过且来源/License/Secret 审计通过后，仓库可以首次公开；运行环境继续私有。

    

### G06：多租户 Runtime、调度与沙箱



实现：



- Keycloak OIDC，`viewer/operator/approver/admin` 四角色。

- PostgreSQL RLS、Qdrant tenant filter、MinIO 前缀隔离。

- Tenant quota、并发限制、Token/成本预算。

- PostgreSQL task queue、priority、lease、heartbeat、deadline、backpressure。

- Stateless API、1–4 Worker 横向扩展。

- gVisor/Kata Sandbox、SDK/CLI、Tool/Skill Registry。

    

Eval：



- 至少 3 个 tenant、4 种角色的 IDOR/ACL 矩阵。

- 100 个并发 Mock Incident 和 10 个并发真实模型 Incident。

- Worker 在规划、工具、审批前后、动作执行和验证阶段被终止。

- Sandbox 执行文件、网络、凭据、宿主机、资源耗尽攻击集。

- 记录回放与确定性重放。

    

通过标准：



- 跨租户 PostgreSQL、Qdrant、MinIO、SSE 泄漏为 0。

- Quota、rate limit、cancel 和 deadline 100% 生效。

- 任务丢失为 0，重复动作副作用为 0。

- Worker 恢复时间不超过 lease 到期后 30 秒。

- 1→4 Worker 的 Mock 吞吐至少提升 2\.5 倍。

- Sandbox escape、Secret 读取、未授权网络访问为 0。

- Recorded model/tool outputs 下，状态重放结果一致。

    

### G07：完整评测、数据飞轮与泛化



实现：



- 完成 160 个均衡核心 case。

- 非变更故障中至少 24 个包含“最近存在但并非根因的变更”。

- 形成 1,000 条以上完整 TrajectoryIR。

- 建立 badcase 分类：Data、Prompt、Model、Tool、Memory、Policy、Runtime。

- Online Boutique 20 个 diagnosis\-only case。

- ITBench\-Lite locked evaluation。

- 至少 10 个深度 badcase 报告。

    

Eval：



- Dev/Validation 用于开发；locked test 只由 Gate Runner 运行。

- Judge 使用不同 Provider/模型家族。

- 关键安全结果全部人工复核，普通 Judge 结果随机人工复核 20%。

- 报告 Judge\-human agreement。

    

通过标准：



- 达到 G02 冻结的全部最终质量下限。

- Judge\-human agreement ≥ 0\.80。

- 160 个 case、数据版本、Ground Truth、失败标签均可追溯。

- 第二 SUT 相对主 SUT 的诊断成功率下降不超过 15pp。

- 所有训练候选轨迹已完成去重、权限清理、隐私清理和数据泄漏检查。

    

### G08：模型、架构和性能消融



实现并比较：



- Deterministic、Naive ReAct、最终 Agent。

- 单 Agent 与 Planner/Investigator/Verifier。

- 静态工具与动态 Tool/Skill。

- 三个 Provider 的角色模型。

- Memory、RAG、Reranker。

- Cache、batch、model routing。

- HolmesGPT 作为固定 commit 的黑盒参考，不复制代码。

    

决策规则：



- Multi\-Agent 进入默认架构：质量或证据指标提高至少 5pp 且 95% CI 不跨 0，额外成本和延迟不超过 30%；或关键不安全建议下降至少 50%且质量不退化。

- Cache/Model Routing 进入默认架构：成本或 P95 至少改善 20%，质量下降不超过 2pp。

- 未达到条件的实验保留在报告中，但不进入主架构。

    

通过标准：



- 每项重要架构决策都有 ADR、冻结实验、LangSmith Experiment 和可复现报告。

- 默认模型、Prompt、RAG、Memory、Tool/Skill 和 Agent 拓扑全部锁定。

- 所有公开性能主张包含相同硬件、并发、数据集、模型版本、置信区间和 Cost per Successful Task。

    

### G09：训练就绪与三条真实 Smoke Pipeline



实现：



- 从 TrajectoryIR 构建：

    

    - SFT：State＋Available Tools → Structured Next Action；

    - DPO：Chosen/Rejected 计划或轨迹片段；

    - GRPO：可执行环境、规则 Reward 和轨迹采样。

        

- 使用 TRL＋PEFT＋QLoRA。

- 根据固定规则选择最小的、许可允许再分发、TRL 支持、可在 4090 上运行的 Qwen 系开源指令模型；锁定 repo、revision 和 tokenizer。

- Reward 分解：Task success、Evidence coverage、Tool correctness、Safety、Step/Token cost。

- 生成 Dataset Card、Model Card、训练配置和完整启动命令。

    

Smoke 标准：



- SFT 和 DPO 各完成至少 20 个真实 optimizer step。

- GRPO 完成至少 10 个真实 optimizer update。

- 三条路径均完成 checkpoint 保存、恢复、加载和推理。

- 输出必须通过 Structured Action Schema。

- 记录 GPU hour、显存峰值、loss/reward、seed、环境和版本。

- Smoke 数据不得包含 validation、locked test 或外部 benchmark。

- 不因 smoke loss/reward 变化宣称模型质量提升。

    

正式训练启动条件另行固化：



- 至少 500 条人工审计 SFT 样本；

- 至少 300 对有效 Preference 数据；

- 标签抽检一致性 ≥ 0\.80；

- badcase 已证明属于模型可学习问题；

- 奖励各分项通过 reward\-hacking 单测；

- 正式算力、预算和回归计划获批。

    

### G10：最终发布、Dogfooding 与面试资产



实现：



- 私网运行 4–6 周 Incident Journal。

- 至少 3 名真实使用者完成不少于 20 次事故调查或回放。

- 清理公开代码、数据、Trace、License、SBOM 和 Secret。

- 完成部署 Runbook、Threat Model、Data Card、Model Card、Eval Card。

- 准备成功修复、失败补偿、误导性变更、Worker 恢复、多租户隔离五类演示。

- 形成应用岗、Infra 岗、算法岗三套叙事，但引用同一套代码与证据。

    

最终 Gate：



- 全新环境只按文档即可部署并运行核心演示。

- G00–G09 全部通过，无未关闭 P0/P1 缺陷。

- `CLAIMS.yaml` 中 100% 对外主张链接到代码、测试、Trace、数据和实验。

- 公开仓库不包含原始面经、受限数据、密钥或未脱敏 Trace。

- 提供 10 分钟演示、30 分钟技术深挖、10 个 badcase 复盘和完整复现实验命令。

- 项目可以明确说明正式训练尚未启动，但三条训练管线均有真实 4090 smoke 证据，算力到位后无需重写数据或评测系统即可启动。

    

---



## 5\. 全局测试与验收原则



### 必测失败场景



- 最近发生变更但根因与变更无关。

- 同时存在多个相关或无关变更。

- 模型 429/5xx、超时、错误 JSON 和 ToolCall。

- 工具空结果、超时、重复响应和大结果。

- Worker 在审批前后及动作执行期间退出。

- SSE 重连、取消和任务 deadline。

- 审批参数变化、过期、重放和并发批准。

- Action 返回成功但服务健康未恢复。

- 跨租户 IDOR、向量检索和对象存储访问。

- Sandbox 宿主挂载、凭据、网络、fork bomb 和资源耗尽。

- 过期 Memory、冲突 Memory 和恶意 Runbook。

- Prompt、Model、Tool、Skill、RAG、Policy 版本回归。

- Locked\-test 或 Ground Truth 泄漏。

    

### 评测原则



- 确定性 evaluator 优先，LLM Judge 只评估难以规则化的证据质量和报告质量。

- 同一模型不得同时生成测试、答案并作为唯一 Judge。

- 所有随机实验至少 3 次重复并报告 95% CI。

- 安全和隔离指标必须为零容忍。

- Baseline 后可以提高质量阈值，不能为了当前结果降低阈值。

- 负实验、失败 Gate 和 rejected architecture 均作为正式资产保留。

- 不保存或展示模型私有思维链，只保存结构化决策摘要、证据、状态变化和工具事件。

    

该计划以所有 Gate 通过为完成标准，不以日期、代码量、功能名词数量或单次演示成功作为完成标准。

