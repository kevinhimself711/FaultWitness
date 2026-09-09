---
document_id: FW-AUDIT-2026-07-28-INDEX
audit_date: 2026-07-28
authoritative: false
scope: review_and_forward_design_only
---

# FaultWitness 逐 Gate 审查（2026-07-28）

## 这个文件夹是什么

一次审查与前向设计的完整结论，21 份文件、约 4,100 行。它做了两件事：

- **回顾审查** G00–G02（已关闭）：设计是否合理、执行是否到位、关闭证据是否成立、不足如何补救。
- **前向设计** G03–G10（未开始，此前只有全局文档里的高抽象边界）：细化到 iteration 粒度，
  每个 iteration 配 eval 与通过标准。

**不改动仓库代码。** 全部文件 `authoritative: false`，不修改 `PROJECT_STATE.yaml`，
不使任何 G00–G02 证据失效，也不构成 Gate Plan 修订——修订需要单独的批准动作。
`docs/gates/G02/REPORT.md` 里的 0.500 / 0.000 作为诚实的历史记录原样保留。

基准是仓库根目录的 `大厂Agent项目立项要求与决策报告.md`（v1.0, 2026-07-17）与
`docs/requirements/REQUIREMENTS.yaml` 的 57 条需求（41 条 P0/mandatory）。

## 文件夹结构

```text
docs/audit/2026-07-28/
├── README.md                     ← 你在这里：索引、判据、结论摘要、待办
│
├── REQUIREMENT_COVERAGE.md       全局判据层：57 条需求的 T1–T4 分级
│                                 （核心 / 支撑 / 可降级 / 建议舍弃）+ Gate 分布
├── FINAL_PLAN_REVIEW.md          现有 FINAL_PLAN 的九处不足 + 明确不应改动的部分
├── FINAL_PLAN_PROPOSED.md        达标版 FINAL_PLAN 全文草案（待批准）
│
├── GOVERNANCE_REVIEW.md          专题：治理系统——G02 治理成本量化、简化成效、残留项
├── EVAL_HARNESS_REVIEW.md        专题：eval / trace / memory harness 与指标可信度推导
├── MODEL_LAYER_REVIEW.md         专题：模型层与推理层（第二轮增补）
├── CROSS_GATE_INTERFACES.md      专题：5 条跨 Gate 接口的字段级规格（第二轮增补）
├── BADCASE_TAXONOMY.md           专题：badcase 分类口径修正（第二轮增补）
├── INTERVIEW_DEFENSE_COVERAGE.md 专题：§19 交付物 + §20 追问 88 题的落点核查
│                                 （第二轮增补；采纳 4 条、驳回 5 条）
│
└── gates/
    ├── G00.md  G01.md  G02.md    回顾审查（已关闭的三个 Gate）
    └── G03.md … G10.md           前向设计（iteration 划分 + 通过标准 + 联动 + 明确不做）
```

四层的读法：**判据层**定标准，**专题层**给证据，**gates/** 落到可执行的 iteration，
**FINAL_PLAN_PROPOSED** 把前三层收敛成一份可批准的计划。

## 阅读顺序

### 如果你要实施 G03（最常见）

1. [CROSS_GATE_INTERFACES.md](CROSS_GATE_INTERFACES.md) —— **只读一份就读这个。**
   它是唯一"不做就必然返工"的文件，五条契约层字段规格必须与 G03 的 I-01 同批落地。
   其余文件都是取舍论证，这一份是硬约束。
2. [gates/G03.md](gates/G03.md) —— 八个 iteration、通过标准、三条前置阻塞。
3. [EVAL_HARNESS_REVIEW.md](EVAL_HARNESS_REVIEW.md) 第一、三节 ——
   G03 的 5pp 门槛为什么现在没有意义，以及五条空转 floor 怎么硬化。

### 如果你要判断范围与取舍

1. [REQUIREMENT_COVERAGE.md](REQUIREMENT_COVERAGE.md) —— 全局判据与 T1–T4 分级。
   **先读这一份**，后面所有 Gate 文件的投入水位都由它决定。
2. [FINAL_PLAN_PROPOSED.md](FINAL_PLAN_PROPOSED.md) §2 叙事分工、§3 主动排除的能力、
   §3.1 建议新增的需求。
3. [MODEL_LAYER_REVIEW.md](MODEL_LAYER_REVIEW.md) —— 唯一一处"应该加"而非"应该减"的结论。

### 如果你要审阅本轮审查本身

1. [FINAL_PLAN_REVIEW.md](FINAL_PLAN_REVIEW.md) —— 九处不足，以及明确**不应**改动的部分。
2. [GOVERNANCE_REVIEW.md](GOVERNANCE_REVIEW.md) —— 治理简化的量化成效与唯一真实回退。
3. gates/G00–G02 —— 三份回顾审查，判断已关闭的 Gate 证明了什么、没证明什么。

### 按 Gate 查

[gates/](gates/) 下每份文件自带结构：本 Gate 定位 → 冻结的退出标准 →
iteration 划分（各含 eval 与通过标准）→ 与其他 Gate 的联动 → 规模 → **明确不做**。
最后一节尤其值得读——它记录了主动排除的理由，这类记录本身是面试资产。

## 判据

不按"57 条覆盖率"打分。三条判据：

1. 这条要求能否在面试中撑起一次**深度追问**（不是名词确认,而是"你怎么测的、样本多少、反例是什么"）。
2. 它是否落在 **Agent 开发 / AI Infra / LLM 训练** 三个目标岗位族的核心素养上。
3. 它放在 FaultWitness 这个具体场景里是否**适配**,还是会大幅增加复杂度而不增加可讲述的深度。

立项报告 §1.3 自己就写明了"合理方案不是堆满所有能力",
并给了取舍原则"多模态只有在业务数据确实需要图片、表格或视频时才进入 P1,
不为关键词覆盖强行加入"。本轮据此把 57 条分为四档,并显式点出应舍弃与降级的项。

分级的依据是 `SOURCE_CATALOG.yaml` 的 `themes` 字段（22 份 JD × 83 份有效面经的逐份主题编码），
**不是 `REQUIREMENTS.yaml` 的 `source_ids`** ——后者是模板化填充（57 条各恰好 5 个来源，
只用到 107 个来源中的 27 个，去重后仅 26 种组合），无法用于排序重要性。

## 结论摘要

| 主题 | 结论 |
|---|---|
| 治理系统 | 简化真实有效,热路径 0 强制治理产物;安全回退已修（`audit.py` 接回 `verify-fast`）,剩 1 处 operator 缺口 |
| Eval harness | v1 测的是格式合规;v2 引入组存在性泄漏（三条同分 1.000）;**v3 已去泄漏**（Top-1 `8/32`）,并于 2026-09-05 修正了未披露的证据契约。现存问题不再是仪器而是任务饱和——见下方第 1 项 |
| G00 | 关闭有效,但证明的是文档自洽;`audit.py` 的 CI 前门缺口已偿还 |
| G01 | 三个已完成 Gate 中工程含量最高;DEBT-G01-004 至今无归属,建议 G03 接走 |
| G02 | 关闭有效,被测对象是实验室而实验室确实建成;REPORT 未改;**5pp 比较基准已于 r9 成立**（`best_baseline` = `naive_react` 0.9167,比较式 0.9667 可行）,但同一数字使 `+0.10` 全局下限不可行 |
| G03 | **T1 核心密度最高的未开始 Gate（6 条),现仅 30 行 placeholder——当前最大设计缺口** |
| G04 | 全项目最宽,应拆两阶段评估,多模态应舍弃 |
| G05 | 一票否决项最密集;安全治理做到可演示即可,不必企业 IAM 深度 |
| G06 | T1 最少却交付最重,应瘦身 10-14 天 |
| G07 | split 按模板切分存在构造性泄漏,须重设计 |
| G08 | T3 密度最高,引用 G04 消融可压缩 18-23 天 |
| G09 | 归因报告应升为首要交付,smoke 管线次要 |
| G10 | 三套叙事深度不应相同;AI Coding 度量被低估应上调 |
| FINAL_PLAN | 冻结数值质量高,缺的是取舍层、叙事分工层、Gate 联动层 |
| 模型层（第二轮） | **JD 第三高主题却零需求落点**;gateway 已实现且质量不低,但未进评测因此无法证明 |
| 跨 Gate 接口（第二轮） | §8 的"必须预留接口"缺字段级规格,无法验证;5 条转为可验收规格 |
| Badcase 分类（第二轮） | `FINAL_PLAN.md:306` 的"七类"**全仓库从未枚举**;应采用报告 §13.1 的 13 类 |
| §19/§20 落点（第二轮） | 88 题里 79 题有落点;**最大缺口是 ADR 决策层**——§19.1 十二条缺八条,现有 15 份 ADR 类型全部错位 |

规模结论：建议版工程日合计约 **172-215 天**，较原设计减少约 **34-44 天**，
且**未降低任何一条冻结退出数值**。减少来自舍弃不适配能力、降级低收益范围、
以及 G08 引用 G04 消融而不重跑；第二轮的 §19/§20 补齐项使总量回升 7-9 天，
全部是文档与既有实验的 arm 扩展，不新增子系统。

**规模表只用于排序与依赖分析，不是工期承诺。** 每个 Gate 的规模按设计完整性决定，
时间不作为约束条件。

## 两轮的分工

**第一轮做减法**：按 JD 相关性分级，识别应舍弃与应降级的项。

**第二轮做加法**：针对"设计层面还缺什么"重新查证，新增三份专题文件并修正四处既有结论。

| 修正 | 原结论 | 修正后 | 依据 |
|---|---|---|---|
| G08 按任务路由 | 与 Batch 一并舍弃 | **保留** | 舍弃理由只对"按 provider 容灾"成立,报告 `:457` 要求的是按**任务**路由,单上游内三个模型族的能力与价格差异完全可测 |
| G07 badcase 类目 | 七类 | **13 类**,`other` ≤5% | "七类"从未枚举;13 类里 4 类各对应一个专门建成的机制 |
| G03 I-01 规模 | S（2-3d） | M（3-4d） | 五条跨 Gate 接口规格在此一次性落地 |
| G08 规模 | 16-20d | 17-22d → 18-23d | 按任务路由 +1-2d;模型族切换演练 +0.5d |

第二轮新增的实现落点（均为既有结论的遗漏，非范围扩张）：
结构化输出合法率真实计算、`RESULT_SCHEMA` 死代码处置、Prompt/Schema 版本进 Trace、
缓存 Key 含权限范围、幻觉五层聚合小节。

**§20 追问清单的筛选。** 逐题核查报告 §20 的 88 题后，9 题无落点，
按判据只采纳 4 条、驳回 5 条——**不无脑照收**。采纳的是八份选型 ADR（成本只是把
已做过的判断写下来）、项目级 Problem Brief（P0 mandatory 的 verification 无产物）、
长上下文 arm（Memory 整块的立论前提）、Reward Hacking 排除记录（补判断而非补实验）。
驳回的五条写入各 Gate 的"明确不做"，理由同样留档。
完整筛选过程见 [INTERVIEW_DEFENSE_COVERAGE.md](INTERVIEW_DEFENSE_COVERAGE.md)。

第二轮也纠正了第一轮的两处偏悲观描述：`models/` 包**已存在**且
`gateway.py:106-117` 有真实的 JSON Schema Draft 2020-12 校验与有界修复；
契约层比"只是契约模型"更完整（`Hypothesis.contradicting_evidence`、
`ActionProposal.action_digest`、`Lease.fencing_token` 三处都预判了后续 Gate 的需要）。

## 术语

- **回顾审查**（G00–G02）：master plan 设计是否合理、iteration 划分是否得当、
  eval 标准松紧、关闭证据是否成立、执行是否到位、不足如何补救。
- **前向设计**（G03–G10）：把 `FINAL_PLAN.md` §6 已冻结的交付与退出标准细化到 iteration 粒度,
  并为每个 iteration 配 eval 与通过标准。**冻结的退出标准只能提高,不得降低。**
- **T1–T4**：需求分级。T1 核心（必须做到可深挖）、T2 支撑（能演示、不深挖）、
  T3 可降级（缩到最小可证形态）、T4 建议舍弃或绕过。
- **零容忍**：该项的通过标准是 0 或 100%，且必须有一个负例测试证明它会失败。
  没有负例的零容忍项不算验证。

## 五项立即待办

按阻塞性排序。第一项是硬阻塞,后两项是"晚做则返工"。
第 2、3 项与原第 1 项已于 2026-07-28 晚随 metric v2（`AMD-0006`）落地,
状态更新在下面：

1. **消除组存在性泄漏,使三条 baseline 分化** —— G03 的 5pp 门槛唯一硬阻塞。
   原待办"baseline 重测"已执行完毕（`deterministic_baseline` 改为读值、
   scorer 披露封闭标签集、8 个 resource case 修 oracle 与基线语义、192/192 live trial）,
   但复测结果是三条 baseline 全部 `core_e2e = 1.000`、CI 宽度为 0,
   `best_baseline + 5pp = 1.05` 不可达。原因不是基线强,而是
   `normalize_observation_packet_v2` 的六个 evidence 组存在性模式泄漏了标签:
   只用"哪些组非空"这一个特征、不读任何数值,Top-3 = 32/32 = 1.000。
   因此必须先去泄漏、令 `no_rag < naive_react` 且 CI 宽度非零,再重跑并固定参照物。
   截断 1.05、排除某条 baseline 或降低 5pp 都属于未授权的门槛弱化。
   见 [EVAL_HARNESS_REVIEW.md](EVAL_HARNESS_REVIEW.md) 第 0 节。

   > **本项的泄漏部分已于 2026-09-05 关闭，但阻塞并未解除，换了形态。**
   > metric v3 去泄漏成功：探针 Top-1 降到 `8/32`、Top-3 `20/32`，三条 baseline 已分化。
   > r8（288/288）一度返回 `ready`，但那是**假通过**——分数由一条 prompt 从未声明的
   > 证据完整性约定压低 live 臂而来。披露该约定后重测（r9，288/288，2.90 CNY）：
   > `naive_react` 0.9167、`naive_react_single` 0.8854、`no_rag` 0.8750、
   > `deterministic` 0.8125，四条配对差**全部含零**，门正确返回 `blocked`。
   >
   > 新的硬阻塞是**任务饱和**：`best_baseline` = 0.9167 使全局下限
   > `max(0.70, best+0.10)` 要求 `core_e2e >= 1.0167`，**单位区间上无解**；
   > `+0.05` 的比较式（0.9667）仍可行，剩 0.033 空间。
   > 一个只读预装包裹、从不接触真实系统的 baseline 做到 0.9167，
   > 所以这不是调参能解决的问题。禁止封顶目标、剔除 `naive_react` 或下调 `+0.10`；
   > 出路只能是改任务（文本盲化包裹、agent 自行采集证据、开放标签集、重设 distractor），
   > 属于后续修正案范围。详见 [gates/G03.md](gates/G03.md) 的 r8、r9 两节。
2. ~~**`audit.py` 接回 CI 前门**~~ —— **已完成**,已接回 `verify-fast`（349 tests passed）。
   G05 的仓库公开决定不再依赖此项。
3. ~~**floor 覆盖硬化**~~ —— **已完成**,7 个门槛数值未动,
   5 条 measured、2 条显式 N/A 并绑定 G03 证明义务
   （`tool_schema_validity` → `g03.tool_contract_matrix`,
   `dead_no_progress_loop` → `g03.termination_guard_matrix`）。
4. **五条跨 Gate 接口规格进契约层** —— 见
   [CROSS_GATE_INTERFACES.md](CROSS_GATE_INTERFACES.md)。它们不阻塞 G03 开工,
   但**必须与 G03 的 I-01 同时完成**：全部是 `contracts/models.py` 的字段,
   集中改一次只需重新编译契约一次;等到 G04/G05/G06 发现不匹配时,
   这些字段已被 G03 的全部 Evidence、Trace 与 checkpoint 引用。

5. **八份选型 ADR 各自在决策发生的 Gate 里写** —— 不阻塞任何 Gate 开工，
   但**不能事后补**：ADR 的价值在于记录当时被否决的备选，
   等 G10 再回头补写就只是追认，而追认答不了"你当时考虑过什么"。
   五份在 G03 I-09、两份在 G04（I-06b 与 I-10）、G10 I-01 只做验收。
   见 [INTERVIEW_DEFENSE_COVERAGE.md](INTERVIEW_DEFENSE_COVERAGE.md) 采纳 1。

定义变更按 `AGENTS.md` 需走修正案路径：已落地部分由 `AMD-0006`（`metric_version: 2`）冻结，
第 1 项若引入 `metric_version: 3` 需另发一条。两种情况下
**7 个门槛数值都逐字节不变，改的是定义而非放宽**。
