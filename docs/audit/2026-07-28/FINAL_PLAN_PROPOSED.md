---
document_id: FW-AUDIT-2026-07-28-FINALPLAN-PROPOSED
audit_date: 2026-07-28
authoritative: false
status: draft_for_approval
supersedes: none
---

# FINAL_PLAN 建议版（草案）

这是一份**待批准草案**,不替代 `docs/blueprint/FINAL_PLAN.md`。它保留原计划全部冻结的退出数值,
增加原计划缺少的三层：**取舍层**、**叙事分工层**、**Gate 联动层**。

缺陷依据见 [FINAL_PLAN_REVIEW.md](FINAL_PLAN_REVIEW.md);分级依据见
[REQUIREMENT_COVERAGE.md](REQUIREMENT_COVERAGE.md)。

## 1. 项目定义

FaultWitness 是面向微服务研发与 SRE 的 Agent 平台：收到告警或自然语言问题后,
从指标、日志、Trace、代码、配置、变更记录与 Runbook 收集证据,生成可追溯根因假设;
在风险策略与人工审批约束下执行可逆修复;随后验证恢复效果,必要时回滚并沉淀事件记忆。

目标等级为 **L3 面试级生产型原型**,不是商业生产系统。
具备生产系统的关键约束、证据与测试,但把多地域、超大规模集群、完整企业 IAM
明确列为非目标。

## 2. 叙事分工（原计划缺失）

立项报告 §1.3：这些 JD 至少分四类岗位,"一个个人项目不可能在每个方向都达到同样深度。
合理方案不是堆满所有能力,而是建设一套共同的生产型 Agent 核心;
主攻应用开发作为默认求职叙事;按目标岗位二选一增加算法优化扩展或 Infra 扩展。"

| 叙事 | 定位 | 供货 Gate | T1 核心需求数 | 目标深度 |
|---|---|---|---:|---|
| **应用开发** | **默认主叙事** | G03、G04 阶段 A、G05 | 16 | 最深,可承受任意深挖 |
| AI 算法 | 二选一扩展 | G07、G09 | 3 | 中等,以评测与归因为主 |
| Agent Infra | 二选一扩展 | G01、G06 | 2 | 中等,已按权重瘦身 |

这个分工不是主观选择,是数据结果：21 条 T1 核心需求里 16 条落在应用叙事的三个 Gate 上。

**每个 Gate 必须知道自己为哪套叙事供货**,以此决定投入水位。

## 3. 主动排除的能力（原计划缺失）

以下能力经评估后**不做**。排除记录本身是面试资产——它展示判断力,而勉强实现只展示执行力。

| 能力 | 原状 | 排除理由 |
|---|---|---|
| **多模态文档处理** | `REQ-MM-001` P2,原为 G04 交付 | 本项目证据全部是结构化文本（指标/日志/Trace/配置/变更）。JD 覆盖 77% 但面经仅 25%。立项报告 §1.3 明令"不为关键词覆盖强行加入"。该需求 statement 本身写的是 "only for demonstrable value" |
| **Batch 对照** | 原为 G08 交付 | 收益取决于上游是否支持 continuous batching,而单一 live upstream 不暴露该能力（§7 已声明）。测不出真实效果,只能得到无法讲述的"无显著差异" |
| **按 provider 容灾路由** | 原为 G08 交付 | 单 live upstream,不得表述为跨供应商容灾。**注意：按任务路由不在排除范围,见下** |
| **本地推理 / Continuous Batching / Prefix-KV Cache** | 报告 `:839` | 该处原文是"根据数据决定是否引入",是条件句不是要求。单机 K3s + 单张 4090 已被 G09 训练 smoke 占用,无硬件余量 |
| **完整 prompt 管理系统** | — | 版本化只需 digest + 版本号进 Trace,不建 prompt 注册表、A/B 分流或模板编辑界面 |
| **完整配额系统与调度器** | 原为 G06 交付 | 无真实租户,配额的计费与公平性价值不成立。1-4 Worker 用队列 + lease 即可 |
| **沙箱管理层** | 原为 G06 交付 | 镜像生命周期、池化、预热不影响"隔离是否成立"这一主张。沙箱本体保留 |
| **完整 Skill 生态** | 原为 G04 交付 3-5 个 Skill + 动态加载 | 降为 2-3 个 Skill + trigger 精确率。`tools_mcp_skills` 主题的高分主要由 tools 与 MCP 贡献 |
| **SDK/MCP 双向等价实现** | `REQ-TOOL-005` P1 | 降为 MCP 只读子集 + 一致性契约测试。足以回答鉴权与暴露问题 |
| **交互式 Dashboard** | `REQ-OBS-003` P1 | 降为静态报告页。observability 面经覆盖 24%,看板是最贵的表达形式 |
| **25/50 并发测量** | `REQ-PERF-002` P0 | 单机 K3s 上不可信,报了是负资产。降为 1/10 两档 |
| **容量曲线扫描** | `REQ-RAG-007` P1 | 降为单点容量报告 |

**规则**：以上每一条都必须在对应 Gate 报告中留下"已评估并排除"的记录及理由,
不得静默省略。涉及 P0 需求或冻结数值的降级须走 `docs/blueprint/AMENDMENTS/` 修正案。

## 3.1 建议新增一条需求（第二轮）

第一轮只对既有 57 条做取舍,未新增。第二轮发现一处**已实现但无人承接的模块**,
且它落在 JD 覆盖率第三高的主题（`model_inference` JD 95% / 面经 81%）上,
而 57 条需求里没有一条以模型调用层为主体。

> **REQ-MODEL-001（建议,P0 支撑档）：模型调用层可证明。**
>
> Statement：模型网关对全部关键输出执行 Schema 校验,解析失败进入有界修复或显式降级;
> Prompt、模型、参数与 Schema 版本写入每次 Trace;按任务类型路由模型;
> 缓存仅用于纯函数步骤且 Key 含权限范围。
>
> Verification：报告结构化输出合法率（绝对值与样本数）、修复成功率、各失败码分布;
> 提供一个畸形输出负例测试与一个跨租户缓存命中拒绝的负例测试;
> 任一 Trace 可取出其 prompt 与 schema 版本。
>
> Gates：G03（合法率与版本化）、G08（任务路由与缓存对照）。

**为什么是支撑档而不是核心**：它不构成 §0.1 任何一条一票否决项,
也不是 L3 十条门槛的唯一落点。但它是该主题唯一落点,且**实现成本极低**——
`models/gateway.py:106-117` 已有真实的 Draft 2020-12 校验与有界修复
（修复次数被类型钉死为至多 1 次,这是好设计:它使"修复"不可能退化成隐式重试循环）,
缺的只是版本字段、指标聚合与两个负例测试。

完整分析见 [MODEL_LAYER_REVIEW.md](MODEL_LAYER_REVIEW.md)。

## 4. 安全不变量（原文保留,不改）

- Agent 只能产生 ToolCall 和 ActionProposal,不能直接执行 shell 或 Kubernetes 写操作。
- Action Executor 是唯一写入口。
- R2 动作必须绑定不可变审批摘要。
- 参数、环境或资源版本变化会使审批失效。
- COMMITTED 必须有后置条件成功证据。
- UNCERTAIN 不得盲目重试。
- 不宣称分布式 exactly-once。
- Ground Truth 和 locked test 永不暴露给 Agent。
- 不保存模型私有思维链。

## 5. 技术方向（原文保留,一处强化）

Python 3.12、FastAPI、Pydantic、LangGraph;React、TypeScript、Vite;
PostgreSQL、Redis、Qdrant、MinIO、DVC;Keycloak/OIDC、OPA/Rego;
K3s、Helm、NetworkPolicy、ResourceQuota;
OpenTelemetry、Prometheus、Loki、Tempo、Grafana;LangSmith;SOPS + Age;
TRL、PEFT、bitsandbytes、Accelerate。

ModelGateway 通过 Bailian live channel 调用 Qwen、DeepSeek、GLM 三个模型族。
**三个模型族共享一个当前 live upstream,因此不得表述为三家独立 Provider
或跨供应商容灾。** 这条声明必须在 G08 的模型对照报告中重复,不只写在计划里。

默认 Agent 架构为单 Orchestrator 加确定性并行 Evidence Collectors。
**Multi-Agent 只有消融证明收益后才能成为默认路径。**

## 6. 治理（替换原 §5）

治理规则以 `docs/governance/GOVERNANCE_V2.md` 为准。G00–G02 的 I/C/A 迭代与 Eval
生命周期属**只读遗留 epoch**（`docs/governance/LEGACY_GOVERNANCE_EPOCH.md`）,
不适用于 G03 及以后。

保留的资产规则：

- 行为变化与必要文档进入同一 commit。
- Gate 失败与负实验永久保留。
- 原始 JD、面经、密钥、私有 Trace 与受限数据不得提交。
- Tier-C 辅导答案不能成为强制需求或指标的唯一来源。
- 每项公开主张最终必须关联代码、测试、Trace、数据与可复现实验。

移除的机制（已由 v2 替换,量化见 [GOVERNANCE_REVIEW.md](GOVERNANCE_REVIEW.md)）：
候选 SHA 全局绑定、Eval manifest 自动生成、Iteration/Gate 双资产关闭 commit、
strict up-to-date 分支保护。失效范围现由 `semantic_cache_key` 与具名 runtime checkpoint 决定。

**反死锁规则**：连续两个只改治理、没有新 runtime observation 的动作即判定为编排死锁,
必须删除或绕过非语义阻塞项。

权威命令：`uv run python -m faultwitness_dev <command>`。Makefile 只作 Linux 薄封装。

## 7. Gate 路线

退出数值全部沿用原计划,**未降低任何一条**。新增每个 Gate 的"不做"边界与联动说明。

### G00–G02（已关闭,回顾结论）

见 [gates/G00.md](gates/G00.md)、[gates/G01.md](gates/G01.md)、[gates/G02.md](gates/G02.md)。

待偿还项及状态（2026-07-28 更新）：`audit.py` 接回 CI 前门 —— **已完成**;
DEBT-G01-004 由 G03 接走 —— 未做;G02 的 baseline 重测 —— **已执行但参照物无效**,
被"消除组存在性泄漏使三条 baseline 分化"取代为 **G03 唯一硬阻塞**。

### G03：只读 Agent 纵切

交付：Typed State、checkpoint、interrupt、SSE/outbox;
Evidence、Hypothesis、ProbePlan、ChangeEvent;
指标、日志、链路、Kubernetes 与变更工具;Incident Console 最小闭环。

退出（不变）：Validation E2E 比最佳基线提高至少 **5pp**;
关键结论 **100%** 回溯到 EvidenceRef;Worker 和 SSE 恢复不丢失或重复状态。

**前置**：第 1 条的 `best_baseline` 必须来自一批**可区分**的 baseline。
v1 的 0.500 是规则表缺陷造成的巧合（已修）;metric v2 复测后三条 baseline 同分 1.000、
CI 宽度为 0,`1.000 + 5pp = 1.05` 不可达。原因是组存在性签名可在不读任何数值的情况下
拿到 Top-3 = 32/32（[EVAL_HARNESS_REVIEW.md](EVAL_HARNESS_REVIEW.md) 第 0 节）。
**数值 5pp 不变,先修泄漏再固定参照物**;截断 1.05、排除基线或降低 5pp 都是未授权弱化。

> **前置已完成（2026-09-05）。** metric v3 去泄漏并披露证据契约后实测（r9,288/288）：
> `naive_react` **0.9167**、`naive_react_single` 0.8854、`no_rag` 0.8750、
> `deterministic` 0.8125,CI 宽度 0.18–0.19,"一批可区分的 baseline"这一前置**已满足**,
> `best_baseline` 参照物由此固定为 0.9167。5pp 那条门槛可达（0.9667,剩 0.033）。
>
> 但同一参照物使全局 quality floor `max(0.70, best+0.10)` 要求 `core_e2e >= 1.0167`,
> **单位区间上无解**。也就是说 `+0.05` 与 `+0.10` 的可行性已分道扬镳,
> 而本节冻结的只是前者。禁止事项不变且现在更具体：不得下调 `+0.10`、不得剔除
> `naive_react`、不得封顶目标。出路只能是改任务形态,详见
> [gates/G03.md](gates/G03.md) 的 r9 一节。

**新增交付（第二轮）**：
- [CROSS_GATE_INTERFACES.md](CROSS_GATE_INTERFACES.md) 的五条契约层字段规格,
  与 I-01 同批落地。
- `tool_schema_validity` 真实计算,接入 gateway 的
  `INVALID_STRUCTURED_OUTPUT` 与 `INVALID_TOOL_ARGUMENTS` 两个失败码;
  `RESULT_SCHEMA`（`g02_baselines.py:45-70`,当前为死代码）生效或删除。
- Prompt、模型、参数与 Schema 版本写入每次 Trace（报告 §6.5 `:459`）。
  与成本归因共享同一 span 属性写入点。

**不做**：任何写操作、RAG、Memory、多 Agent、多租户、交互式 Dashboard。

九个 iteration 约 25-30 天（含 I-09 的五份选型 ADR）,详见 [gates/G03.md](gates/G03.md)。

### G04：RAG 与 Memory（拆两阶段评估）

**阶段 A — RAG**（14-19 天）：摄取与格式路由;chunk 策略三方对照;
dense/sparse/fusion/rerank 四段可归因;五级引用;增量与回滚;ACL 前置过滤。

**阶段 B — Memory 与 Skills**（13-17 天）：三类记忆分库;memory harness;
写入门控;冲突与过期;2-3 个 Skill;动态工具检索对照;MCP 只读子集;压缩消融。

退出（不变）：Recall@10 ≥ **85%**,Citation precision ≥ **90%**;
无收益机制不得进入默认架构;Memory 和动态 Skill 通过独立消融与安全回归。

**新增约束**：本 Gate 的四个消融（chunk、检索分段、动态工具、压缩）
**必须按 G08 的预注册规范执行**,以便 G08 直接引用而不重跑。

**不做**：多模态、完整 Skill 生态、动态加载子系统、SDK/MCP 双向等价、容量曲线。

详见 [gates/G04.md](gates/G04.md)。

### G05：受控修复与动作事务

交付：四种类型化写动作;OPA、Action Digest、审批、幂等、后置验证、补偿、审计。

退出（不变）：未授权写、审批绕过、Digest 篡改接受、重复外部副作用均为 **0**;
后置验证成功率 ≥ **95%**;失败进入补偿或人工升级 **100%**。

通过来源、License 与 Secret 审计后,仓库可首次公开;运行环境继续私有。
**前置：`audit.py` 必须已有 CI 前门 —— 已满足（2026-07-28 接回 `verify-fast`）。**

**不做**：完整策略引擎生态、企业 IAM、不可逆动作。

九个 iteration 约 24-30 天,详见 [gates/G05.md](gates/G05.md)。

### G06：多租户 Runtime 与隔离（已瘦身）

交付：Keycloak 四角色;PostgreSQL RLS、Qdrant ACL、MinIO 隔离;
lease、heartbeat、deadline;熔断与队列上限;1-4 Worker;gVisor,不兼容时 Kata。

退出（不变）：跨租户泄漏、任务丢失、重复动作副作用为 **0**;
Worker 在 lease 到期后 **30 秒**内恢复;1→4 Worker 的 **Mock** 吞吐提高至少 **2.5 倍**;
Sandbox escape、Secret 读取、未授权网络为 **0**。

**不做**：配额系统、调度器、沙箱管理层、25/50 并发测量。

七个 iteration 约 17-21 天（原设计约 28-35 天）,详见 [gates/G06.md](gates/G06.md)。
节省的时间转移到 G03 与 G04 阶段 A。

### G07：完整评测、数据飞轮与泛化

交付：160 个均衡 case;≥24 个误导性最近变更场景;≥1,000 条 TrajectoryIR;
**13 类** badcase 与 ≥10 份深度报告;Online Boutique 20 个 diagnosis-only case;
ITBench-Lite locked eval。

退出（不变）：达到 G02 冻结质量下限;Judge-human agreement ≥ **0.80**;
数据、Ground Truth 与失败标签全部可追溯。

**新增约束**：
- **split 重设计**。现 `SPLIT_COUNTS` 按模板切分,同一模板会跨 dev/locked 出现,
  按构造存在泄漏。立项报告 §8.6 要求按事故模板**和时间**切分。
- 7 条 quality floor 必须**全部真正可计算**。G02 时 5 条空转,
  其中 4 条在 G03 各 iteration 中逐步偿还,`core_e2e` 的门槛表达式在本 Gate 偿还。
- journal-backed replay adapter,键为 `(trial_id, call_ordinal, prompt_digest)`。

**不做**：交互式 Dashboard、超过 160 的 case 规模、更多外部 benchmark。

九个 iteration 约 29-35 天,详见 [gates/G07.md](gates/G07.md)。

### G08：模型、架构与性能消融（已瘦身）

比较：三条 baseline vs 最终 Agent;单 Agent vs 多 Agent（**仅并行取证与独立验证两种形态**);
独立 Verifier;三个模型族;Cache 与上下文缩减。

**引用不重跑**：RAG、Memory、Reranker、动态 Tool、chunk 策略、压缩六个消融
直接引用 G04 数据。

退出（不变）：Multi-Agent 进入默认架构必须质量提高 ≥ **5pp**、95% CI 不跨 0,
且成本与延迟增加 ≤ **30%**;或危险建议下降 ≥ **50%** 且质量不退化。

**预先声明**：这条门槛很可能达不到——单机、160 case、三次重复的统计功效有限。
`PHASES.md:23` 允许负向结果通过 Gate。**一个诚实的负结果完全满足立项报告 §0.1
"使用多 Agent 但说不清为什么单 Agent 不够"这一条**,它证明的是"我做了对照,
数据不支持,所以没用多 Agent"。

**新增保留项：按任务路由模型。** 报告 §6.5 `:457` 要求"确定性分类优先规则/小模型,
复杂规划和验证才用强模型"。这一项**不受单上游限制**——同一 Bailian upstream 下
三个模型族的能力与价格本身不同,该对照产出一个成本数字而不是"无显著差异"。
现状 `RoutePolicy.routes` 只有 `ModelFamily` 维度（`models/catalog.py:31`）,无任务维度。
缓存 Key 须含**权限范围**以防跨租户命中,这是真实安全边界而非性能优化。
详见 [MODEL_LAYER_REVIEW.md](MODEL_LAYER_REVIEW.md)。

**不做**：Batch 对照、按 provider 容灾路由、本地推理、
完整 Planner/Investigator/Verifier 编排、重跑 G04 消融、超过三次的重复。

七个 iteration 约 18-23 天（原设计约 35-45 天）,详见 [gates/G08.md](gates/G08.md)。

### G09：训练就绪与真实 Smoke（交付重排序）

**首要交付**：一份"为什么现在不该真正训练"的归因报告——
按 G07 的 badcase 13 类分布,判定哪些失败是模型能力问题、哪些应通过工程修复,
并给出"在什么条件下应开始真正训练"的触发条件。

**次要交付**：SFT（State + Tools → Structured Next Action）、
DPO（偏好对来自 G07 badcase 归因）、GRPO（**规则化 Reward**,不用 LLM 打分）。

退出（不变）：SFT、DPO 各 ≥ **20 个 optimizer step**;GRPO ≥ **10 个 optimizer update**;
三条路径均完成 checkpoint 保存、恢复、加载与推理;
**不使用 validation、locked test 或外部 benchmark**;
**不把 smoke loss/reward 包装为质量提升**。

排序理由：`REQ-ALG-001` statement 本身写的是 "only after badcase attribution";
§21.8 把"过早做训练"列为具名失败路径。归因报告比 loss 曲线更有说服力。

**硬依赖**：G07 的 1,000+ 轨迹与 split isolation。

五个 iteration 约 12-16 天,详见 [gates/G09.md](gates/G09.md)。

### G10：发布、Dogfooding 与面试资产

交付：私网运行 4-6 周;≥3 名使用者与 ≥20 次事故调查或回放;
Runbook、Threat Model、Data/Model/Eval Card;
成功、补偿、误导性变更、Worker 恢复、租户隔离五类演示;
应用、Infra、算法三套面试叙事（**深度按第 2 节分工,不等深**）;
AI Coding 度量三个数字（**从 P1 上调**)。

最终退出（不变）：G00–G09 全部通过,无 P0/P1 缺陷;新环境仅按文档即可部署;
Claims **100%** 关联代码、测试、Trace、数据与实验;
三条训练管线有真实 **4090 smoke** 证据。

**诚实降级条款**：若找不到 3 名使用者,如实降为 dogfooding 自用 + 完整回放记录并说明,
不虚构使用者（§4.4："没有这些资源时,不应虚构客户、人工团队和线上准确率"）。

**locked 回归门**：这是 v2 之后唯一应重新引入阻塞的 CI 检查,
但必须**按语义变更范围触发,不按 commit 触发**,以避免重现 G02 的自失效循环。

九个 iteration,工程部分 20-24 天,总日历 6-8 周（私网运行并行）,
详见 [gates/G10.md](gates/G10.md)。

## 8. Gate 联动（原计划缺失）

33 条需求跨 ≥2 个 Gate（30 条跨 2 个,3 条跨 3 个）。以下是**必须提前预留接口**的联动,
漏掉会导致返工：

| 联动 | 链 | 提前预留什么 |
|---|---|---|
| `REQ-OBS-001` | G01→G03→G04 | **EvidenceRef 必须在 G03 就支持 source/version/section/chunk 四级定位**,即使 G03 只用 observation 一级。否则 G04 的 citation precision 需返工改 G03 核心结构 |

**本节的字段级规格见 [CROSS_GATE_INTERFACES.md](CROSS_GATE_INTERFACES.md)。**
上表是自然语言描述,无法验证——"四级定位"是哪四个字段名、什么类型、可选还是必填,
一句"必须预留"不构成接口约束。该文件把其中**会导致结构性返工的 5 条**转成字段级规格
并给出验收方式（下游 Gate 若需修改这些字段,即为 G03 未履行接口义务）,
其余 7 条是行为约定而非数据结构,不需要提前定义字段。
| `REQ-AGT-003` | G03→G05→G06 | checkpoint 需区分"已提交"与"已计划",G05 才能扩到外部副作用 |
| `REQ-REL-001` | G03→G05 | typed error 分类体系在 G03 建立,G05 复用不新建 |
| `REQ-TOOL-005` | G03→G04 | 工具 catalog 结构支持 MCP 只读子集投射 |
| `REQ-AGT-002` | G03→G07 | typed terminal reason 枚举可扩展,成为 badcase 分类基础 |
| `REQ-PERF-003` | G03→G08 | 成本归因粒度到单次模型调用 |
| `REQ-AGT-005` | G03→G08 | Verifier 不继承 Planner 结论的接口位 |
| 四个消融 | G04→G08 | **G04 的消融按 G08 预注册规范做,G08 引用不重跑** |
| `REQ-SEC-002` | G04→G05→G07 | 注入防御基线在 G04 建立,攻击成功率在 G07 进入指标 |
| 四个机制 | G05→G06 | 权限、幂等、审计、补偿全部需在多 Worker 下重验。**G05→G06 是最强耦合,G06 不应大幅推迟** |
| `REQ-EVAL-006` | G07→G09 | **G09 硬依赖 G07 的轨迹与 split isolation** |
| `REQ-SEC-003` | G01→G06→G10 | sanitizer 建于 G01,扩全出口面于 G06,最终审计于 G10 |

第一行与第八行是本次审查发现的两处最高价值联动：
前者防止 G04 返工改 G03 核心结构,后者把 G08 从 35-45 天压到 18-23 天。

## 8.1 面试交付物与追问防守（第二轮增补）

原计划 `:352` 只要求"应用、Infra、算法三套面试叙事",
没有把报告 §19（十五项面试交付物）与 §19.1（ADR 最低清单十二条）写成可验收项。
逐题核查 §20 的 88 题后（[INTERVIEW_DEFENSE_COVERAGE.md](INTERVIEW_DEFENSE_COVERAGE.md)）：
**79 题有落点，9 题无落点**，其中 4 条经判据筛选后采纳、5 条驳回。

四节完全覆盖：§20.3 多 Agent、§20.4 Tools/MCP/Skills、§20.7 评测与 Badcase、§20.9 安全。

**跨节的单一最大缺口是 ADR 决策层。** 报告 §19 要求 ≥8 份关键 ADR，
仓库有 15 份且数量达标，但**类型全部错位**——全是架构不变量（ADR-0001/0002/0005/0006）、
基础设施选型（ADR-0003/0004/0007/0008）、治理机制（ADR-0009/0014/0015）
与 G02 实验协议（ADR-0010…0013），
没有一份是 §19.1 要求的"为什么这样选"的路线决策。十二条里**八条缺失**。

采纳的四条与落点：

| 采纳项 | 落点 | 为什么采纳 |
|---|---|---|
| 八份选型 ADR | G03 I-09（五份）、G04 I-06b / I-10（各一份）、G10 I-01 验收 | 决策**已经做过**，`LangGraph` 在仓库出现 13 处但无一处是选型论证；成本只是写下来 |
| 项目级 Problem Brief | G10 I-01 | `REQ-BUS-001` 是 **P0 mandatory**，verification 要求版本化 Problem Brief，而项目级文档不存在 |
| 长上下文 arm | G04 I-14 扩为三 arm | 补的是 Memory 整块的**立论前提**——现有 no-compression baseline 答不了"为什么不把窗口开大" |
| Reward Hacking 排除记录 | G09 I-05 归因报告内 | 规则 Reward 最易被 hack，10 个 update 测不出来；缺的是**判断记录**而非能力 |

驳回的五条（写入对应 Gate 的"明确不做"，不静默省略）：
embedding 选型实验（embedding 是控制变量，加对照会稀释真正想测的因子）、
百万级容量迁移（与已排除的 25/50 并发同构）、BM25 vs 稀疏向量（检索专精题，不落在目标岗位族）、
并发索引一致性（知识库写入方是单一 dogfooding 用户，并发不是真实场景）、
自身发布灰度（纯 CD 工程，单节点 K3s 上无意义）。

**验收方式**：G10 I-01 的通过标准增加"§19.1 十二条各有一份 accepted ADR"，
且每份 ADR 必须含**被否决的备选方案**及否决理由——
只写"我们选了 X"的 ADR 不计入，它没有回答追问。

## 9. 全局评测原则（原文保留,不改）

- 确定性 evaluator 优先。
- 同一模型不得同时生成测试、答案并作为唯一 Judge。
  **本项目具体约束**：三个模型族共享同一上游,Judge 与被测须用不同模型族,
  且报告须说明共享上游这一事实。
- 随机实验至少三次并报告 95% CI。
- 安全、审批、隔离和测试泄漏为零容忍。
- Baseline 后阈值只能提高。
- 失败 Gate、负实验和 rejected architecture 均保留。
- 所有性能结果报告硬件、并发、数据集、模型、成本和失败分布。

项目以全部 Gate 与架构一致性检查通过为完成标准,
不以日期、代码量、框架数量或单次演示成功作为完成标准。

## 10. 规模汇总

| Gate | 本草案 | 原计划估算 | 差 |
|---|---:|---:|---:|
| G03 | 25-30d | 无 iteration 粒度 | — |
| G04 | 27-36d | 含多模态与完整 Skill,约 40-50d | −13 至 −14d |
| G05 | 24-30d | 相当 | 0 |
| G06 | 17-21d | 约 28-35d | −11 至 −14d |
| G07 | 29-35d | 相当 | +1d |
| G08 | 18-23d | 约 35-45d | −17 至 −22d |
| G09 | 12-16d | 相当 | +1d |
| G10 | 20-24d 工程 + 6-8 周日历 | 相当 | +2d |

工程日合计约 **172-215 天**,较原设计减少约 **34-44 天**,
而**没有降低任何一条冻结退出数值**。减少全部来自：
舍弃不适配能力、降级低收益范围、G08 引用 G04 消融而不重跑。

第二轮加法分两批。设计层：G03 +1d（五条接口规格）、G08 +1-2d（按任务路由）。
§20 追问清单层（见 [INTERVIEW_DEFENSE_COVERAGE.md](INTERVIEW_DEFENSE_COVERAGE.md)）：
G03 +2d（五份选型 ADR）、G04 +2d（两份 ADR）+0-1d（长上下文 arm）、
G07 +0.5d、G08 +0.5d、G09 +0.5d、G10 +2d。
**时间不是本项目的约束条件**——规模按设计完整性决定,
上表的作用是排序与依赖分析,不是工期承诺。
