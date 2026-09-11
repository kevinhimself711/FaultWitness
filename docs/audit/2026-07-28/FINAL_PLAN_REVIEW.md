---
document_id: FW-AUDIT-2026-07-28-FINALPLAN-REVIEW
audit_date: 2026-07-28
authoritative: false
question: 现有 FINAL_PLAN.md 是否足以支撑达到岗位要求的深度
---

# FINAL_PLAN.md 审查

## 结论

**它比多数个人项目的规划文档好,主要缺陷不是"不够严格",而是"没有取舍"。**

`docs/blueprint/FINAL_PLAN.md`（371 行）已经做到了三件难做对的事：
§6 为 G00–G10 每个 Gate 冻结了带真实数字的退出标准；§3 的安全不变量九条是可执行的约束
而非口号；§4 `:152` 主动声明了"三个模型族共享一个 live upstream,
因此不得表述为三家独立 Provider"——这种自我约束在个人项目规划里很少见。

问题在另一侧：**它把 57 条需求当作等权处理,没有任何一处写明"这条不做,理由是什么"。**
结果是交付清单持续膨胀,而立项报告 §1.3 自己就写了"合理方案不是堆满所有能力"。

按 [REQUIREMENT_COVERAGE.md](REQUIREMENT_COVERAGE.md) 的分级,
现有计划里有 **12 条应降级、7 条应舍弃或绕过**,一条都没有被标记。

## 缺陷清单

### 缺陷 1：没有取舍层,导致范围只增不减

`FINAL_PLAN.md` 全文没有"不做"这一类陈述,除了 §3 提到的
"多地域、超大规模集群、完整企业 IAM"三项非目标。这三项都是显然不可能做的,
真正需要判断的边界项一个都没有表态。

最典型的是**多模态**（`:256` 摄取"架构图和 Dashboard"、`:263-265` 的 G04 退出）。
`REQ-MM-001` 本身已是 P2,其 statement 写的是
"Add multimodal document processing **only for demonstrable** chart or
architecture-diagram value"——立项报告 §1.3 更明确："多模态只有在业务数据确实需要
图片、表格或视频时才进入 P1,不为关键词覆盖强行加入。"

而 FaultWitness 的证据是指标、日志、Trace、配置、变更记录,**全部结构化文本**。
计划却把它列为 G04 交付。这是最清晰的一处过度设计。

**修改建议**：在 §6 每个 Gate 增加"本 Gate 不做"小节;
在 §1 或 §3 增加一节"已评估并主动排除的能力",逐条写明理由。
主动排除的记录本身是面试资产——它展示判断力,而勉强实现只展示执行力。

### 缺陷 2：G04 与 G08 的规模不可执行

**G04**（`:252-265`）一个 Gate 内塞进 RAG 全链路 + 五类 Memory + 3-5 个 Skill +
动态 Tool/Skill Retrieval + 多模态摄取。按 [gates/G04.md](gates/G04.md) 的拆解,
即使砍掉多模态与完整 Skill 生态,仍需 27-36 天,是全项目最长的 Gate。

**G08**（`:316-326`）列了 5 组对照,其中最后一组
"RAG、Memory、Reranker、Cache、Batch 和 Routing"本身是 6 个子对照。
合计 13+ 次预注册实验,每次要求"至少三次并报告 95% CI"（`:365`）。
原样执行估计需 35-45 天。

**修改建议**：
- G04 拆为阶段 A（RAG）与阶段 B（Memory + Skills）两次 Gate 评估。
  理由见 [gates/G02.md](gates/G02.md) 第二节——G02 的 12 次 attempt 全部死于管道,
  单次评估表面积越大,非语义失败概率越高。
- G08 明确"引用 G04 已完成的消融数据,不重跑"。这要求 G04 的消融从一开始
  就按 G08 的预注册规范做,是一个**必须写进 G04 计划**的跨 Gate 决定。
  仅此一项可把 G08 从 35-45 天压到 18-23 天。
- Batch 与 Routing 对照舍弃,理由是结构性的：单上游架构下不可测量。
  这一点与 §4 `:152` 的自我约束是一致的——既然承认只有一个 live upstream,
  就不应该在 §6 要求做跨 provider 的 routing 对照。**这是计划内部的一处不自洽。**

### 缺陷 3：G03 的比较基准是错的

`:248` 冻结"Validation E2E 比最佳基线提高至少 5pp"。

`best_baseline` 目前是 deterministic 的 **0.500**,而这个 0.500 是规则表缺陷造成的巧合：
`deterministic_baseline` 按 key 存在性匹配,而探针无条件输出 `working_set`,
导致 16/32 被误判为 emailMemoryLeak。完整推导见
[EVAL_HARNESS_REVIEW.md](EVAL_HARNESS_REVIEW.md) 第一节。

**这不是计划的错**,但它使计划里唯一的量化门槛失去意义——5pp 可能过松也可能不可达。

**修改建议**：在 G03 交付前增加一条前置条件"baseline 重测",
并注明 5pp 是相对于**重测后**的基准。数值 5pp 不变,只固定其参照物。

**后续（2026-07-28）**：重测已执行,签名表缺陷确已修复,但结果是三条 baseline
全部 1.000、CI 宽度为 0,`1.05` 不可达。因此前置条件需再强化一层——不只是"重测",
而是"重测后三条 baseline 必须可区分"。当前 1.000 的成因是组存在性签名泄漏标签
（不读任何数值即可 Top-3 = 32/32）,见
[EVAL_HARNESS_REVIEW.md](EVAL_HARNESS_REVIEW.md) 第 0 节。

**结局（2026-09-05）**：本缺陷提出的修改建议已完全落实,且参照物已由实测固定。
metric v3 去泄漏后跑完两轮：r8 返回 `ready` 但被判定为假通过（评分标准未向 live 臂披露、
对照臂按构造豁免）,披露后的 r9（288/288,2.90 CNY）给出
`naive_react` **0.9167**、`naive_react_single` 0.8854、`no_rag` 0.8750、
`deterministic` 0.8125,CI 宽度 0.18–0.19,三条彼此可区分的要求**已满足**。

因此本节担心的"5pp 可能过松也可能不可达"现在有了确定答案：**5pp 那一条可达**
（`best + 0.05` = 0.9667,剩 0.033 空间）。真正不可达的是本节没有点出的另一条——
全局 quality floor `max(0.70, best + 0.10)` 要求 `core_e2e >= 1.0167`,单位区间上无解。
换言之参照物固定之后,`+0.05` 与 `+0.10` 两条门槛的可行性**分道扬镳**了,
而计划 `:248` 只冻结了前者。这一点应在 G03 Master Plan 里明确处置,
但不得以下调 `+0.10`、封顶目标或剔除 `naive_react` 的方式处置。

> 本条已由 [ADR-0018](../../adr/ADR-0018.md) 处置：margin 的数值因锚点失效回到待定，目标形式不变。
详见 [gates/G03.md](gates/G03.md) 的 r8、r9 两节。

### 缺陷 4：三套面试叙事没有深度差异

`:352` 要求"应用、Infra、算法三套面试叙事",但全文未说明三者深度应有差异。

立项报告 §1.3 写得很明确："一个个人项目不可能在每个方向都达到同样深度。
合理方案不是堆满所有能力,而是：建设一套共同的生产型 Agent 核心;
**主攻应用开发作为默认求职叙事**;按目标岗位二选一增加算法优化扩展或 Infra 扩展。"

按 [REQUIREMENT_COVERAGE.md](REQUIREMENT_COVERAGE.md) 的 Gate × 分级分布,
T1 核心需求恰好集中在应用叙事的供货 Gate（G03 六条、G04 五条、G05 五条),
而 Infra 叙事的 G06 只有 1 条 T1。**数据已经支持"应用为主"这个定位,
但计划没有把它写出来**,导致 G06 被赋予了与其权重不符的交付清单。

**修改建议**：在 §6 之前增加一节"叙事分工",声明每个 Gate 为哪套叙事供货,
以及三套叙事的目标深度不同。

### 缺陷 5：G06 交付清单与其需求权重不符

`:282-297` 要求 Keycloak 四角色 + PostgreSQL RLS + Qdrant ACL + MinIO 隔离 +
quota + task queue + lease + heartbeat + deadline + backpressure + 1-4 Worker + gVisor/Kata。

而 `REQ-INFRA-001` 是 **P2、非 mandatory**,`infra_runtime` 主题
JD 45% / 面经 **11%**。G06 只承接 1 条 T1 核心需求。

**修改建议**：保留 tenant 隔离、lease/recovery、沙箱;
砍掉配额系统、调度器、沙箱管理层。详见 [gates/G06.md](gates/G06.md)。
节省的 10-14 天转移到 G03 与 G04 阶段 A。

沙箱不能砍——它是 Agent Infra 岗 JD 的明确要求,
且"用 gVisor 遇到兼容问题换 Kata"是具体可讲述的工程经历。

### 缺陷 6：`REQ-PERF-002` 的四档并发是负资产

`REQ-PERF-002` 要求 1/10/25/50 四档并发。单机 K3s 上 50 并发的数字不可信——
面试官会问"你的硬件能撑 50 并发吗",答案是不能,那这个数字就成了负资产。

**修改建议**：降为 1/10 两档,显式记录 25/50 未测量及原因。
但 `REQ-PERF-002` 是 P0 mandatory 且 `PHASES.md:24` 规定性能标准不得放宽,
**因此这个降级必须走修正案,不能默默少测**。

### 缺陷 7：`REQ-DEV-004` 被低估

`ai_coding` 是**唯一**面经覆盖率（39%）高于 JD（27%）的主题,
`REQ-DEV-004` 却是 P1。

**修改建议**：提到 P0 支撑档。三个数字（accepted diff 比例、首过验证率、返工率)
全部可由 git 历史自动生成,成本 1-2 天,而"你这个项目多少是 AI 写的"是面经常见问题。

### 缺陷 8：G09 的主要产物写错了

`:328-342` 把 G09 定义为三条训练 smoke。冻结标准（20/20/10 step、
checkpoint 全链路、不用 validation/locked、不包装为质量提升）设计质量很高。

但**最有面试价值的产物没有被列为交付**：一份说明"为什么现在不该真正训练"的归因报告。

`REQ-ALG-001` 的 statement 本身就写了
"only after badcase attribution"。§21.8 把"过早做训练"列为具名失败路径。
所以"我做了归因,发现 80% 的失败是检索和工具问题,训练解决不了"
比"我跑了 20 步 SFT"有价值得多。

**修改建议**：把归因报告列为 G09 的首要交付,smoke 管线列为次要。

### 缺陷 9：治理段落已过期

`§5`（`:156-184`）仍描述 Iteration Plan、Eval Manifest、candidate SHA 等资产规则,
`:173` 写"CI 根据候选 SHA 生成不可变 Eval manifest"。

这些机制已被 governance v2 移除或替换：`semantic_cache_key` 取代了全局 candidate SHA,
4 个 lifecycle 模板已删除,`.github/rulesets/main.json` 已删除,
CI 从 3 个必需检查降为 1 个 advisory job。量化见
[GOVERNANCE_REVIEW.md](GOVERNANCE_REVIEW.md) 第二节。

**修改建议**：§5 改为引用 `docs/governance/GOVERNANCE_V2.md`,
并注明 G00–G02 的 I/C/A 生命周期属只读遗留 epoch。

## 不应改动的部分

以下部分质量高,审查建议**保持原样**：

- **§3 安全不变量九条**（`:128-138`）。每一条都可执行,尤其
  "Action Executor 是唯一写入口"、"UNCERTAIN 不得盲目重试"、
  "Ground Truth 和 locked test 永不暴露给 Agent"、"不宣称分布式 exactly-once"。
  最后一条尤其可贵——多数项目会声称 exactly-once。
- **§4 `:152` 的单上游声明**。这是全文最诚实的一句,应保留并在 G08 报告中重复。
- **§4 `:154`**："Multi-Agent 只有消融证明收益后才能成为默认路径。"
  这正是 §21.7 反模式的正面对策。
- **§6 的全部退出数值**。它们是本项目严谨性的来源,
  本审查的所有降级建议都不修改这些数值,只修改**范围**与**参照物**。
- **§7 全局评测原则七条**（`:361-371`）。尤其"同一模型不得同时生成测试、答案并作为唯一 Judge"
  与"Baseline 后阈值只能提高"。
- **`:371`**："项目以全部 Gate 和架构一致性检查通过为完成标准,
  不以日期、代码量、框架数量或单次演示成功作为完成标准。"

## 修改路径

本审查不修改 `FINAL_PLAN.md`。建议的改动分两类：

**不涉及冻结数值的**（可直接进入 Gate 设计,无需修正案）：
- 增加"本 Gate 不做"小节与"已评估并主动排除的能力"一节
- 增加"叙事分工"一节
- G04 拆两阶段评估
- G08 引用 G04 消融数据
- G09 归因报告升为首要交付
- §5 治理段落改为引用 GOVERNANCE_V2
- `REQ-DEV-004` 提档
- 舍弃 `REQ-MM-001`（其 statement 的 "only for demonstrable value" 已允许）

**涉及冻结数值或 P0 范围的**（必须走 `docs/blueprint/AMENDMENTS/` 修正案）：
- `REQ-PERF-002` 从 4 档降到 2 档
- `REQ-INFRA-001` 降为最小骨架（G06 交付清单缩减）
- `REQ-REL-003` 背压降为熔断 + 队列上限
- `REQ-RAG-007` 容量曲线降为单点
- G03 的 5pp 参照物改为重测后基准，且要求那批 baseline 彼此可区分
- Memory harness 的 `cluster_key` 从 `case_id` 改为 `sequence_id`
- eval scorer 的 `metric_version: 2` 定义变更（**7 个门槛数值逐字节不变**）
  —— **已由 `AMD-0006` 冻结**
- 去除组存在性泄漏所需的 case 构造变更（若引入 `metric_version: 3`，需另发一条修正案，
  同样不得动 7 个数值）

第二类的每一条都必须显式说明"降低了什么、为什么、替代证据是什么",
因为 `PHASES.md:24` 规定安全、隔离、Ground Truth、locked-test、质量与性能标准
不得因实施简化而放宽。**这些降级是范围调整,不是标准放宽**,但必须留下判断记录。

完整的建议版计划见 [FINAL_PLAN_PROPOSED.md](FINAL_PLAN_PROPOSED.md)。
