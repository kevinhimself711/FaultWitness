---
document_id: FW-AUDIT-2026-07-28-HARNESS
audit_date: 2026-07-28
authoritative: false
question: eval / trace / memory harness 是否有足够深度支撑 G03 及以后的结论
---

# Harness 深度审查

## 状态更新（metric v2 已实施，2026-07-28 晚）

本文件第一至第四节诊断的问题**已由 metric v2 修复并复测**
（`AMD-0006`、`docs/runbooks/G03_BASELINE_READINESS.md`、
`.audit/g03-readiness/baseline-v2/`）。修复本身成立：封闭标签集已披露、
`deterministic_baseline` 已改为读值、8 个 resource case 已修 oracle 与基线语义、
`audit.py` 已接回 `verify-fast`（349 tests passed）、7 个门槛数值未动。

**但复测结果是三条 baseline 全部 `core_e2e = 1.000`、95% CI 宽度为 0，
因此 `best_baseline + 5pp = 1.05` 不可达，G03 仍不能启动。**

本轮审查的判断是：**1.000 不应被记录为"baseline 太强"，它是一处新的构造性泄漏**，
强度高于 v1 那处。证据见[第 0 节](#零metric-v2-的饱和是新的构造性泄漏)。
因此下一步不是"重设计比较条件"，而是先消除泄漏、再谈门槛。

> **当前状态（2026-09-05）：泄漏已消除，门槛问题换了形态。** metric v3 去泄漏后实测
> （r9，288/288）三条 baseline 为 0.9167 / 0.8854 / 0.8750，CI 宽度 0.18–0.19，
> 不再同分、不再零宽。`+0.05` 的比较式（0.9667）由此**成立**；
> 但 `max(0.70, best+0.10)` 要求 `core_e2e >= 1.0167`，**单位区间上无解**。
> 上面"先消除泄漏、再谈门槛"这一步已经走完，答案是：泄漏不是唯一的饱和来源。
> 详见[第 1-3 步的落地状态](#第-1-3-步的落地状态metric-v3amd-00072026-07-29)与
> [gates/G03.md](gates/G03.md) 的 r8、r9 两节。

以下第一至第四节保留为**历史诊断记录**（v1 口径），不再是当前状态。

## 零、metric v2 的饱和是新的构造性泄漏

三条 baseline 同分 1.000 且 CI 宽度为 0，其中包括 `no_rag`——**一条无检索、无工具、
只读 packet 的基线**。一条被刻意削弱的基线拿到满分，这本身就是泄漏的信号而非能力的信号。

根因在 `normalize_observation_packet_v2`（`g02_baselines.py:543-649`）的结构：
它把每个 packet 归一化成**六个固定 evidence 组，顺序与 `ROOT_CAUSE_LABELS` 一一对应**，
而 `_v2_ground_truth`（`:652-660`）直接用标签在该元组里的下标算出正确答案的组 ID：

```python
index = ROOT_CAUSE_LABELS.index(root_cause) + 1
return {"root_cause": root_cause, "required_evidence_suffix": f"EVID-{index:02d}"}
```

`required_evidence` 恰好是**一个**组，`distractor_evidence` 是其余**五个**
（`:1208-1209`）。于是"选对根因"与"选对唯一那个 evidence 组"是同一个决策，
`evidence_precision` 与 `core_e2e` 不再是两个独立维度。

**决定性的实测**：只用"哪些 evidence 组非空"这**一个特征**——完全不读任何数值——
32 个 case 只产生 4 种签名：

| 非空组签名 | 对应标签 | case 数 | 是否唯一 |
|---|---|---:|---|
| `(1,2,3)` | adHighCpu / emailMemoryLeak | 8 | 二选一 |
| `(1,2,3,4)` | productCatalogFailure | 8 | **唯一** |
| `(1,2,3,4,5)` | paymentFailure / paymentUnreachable | 8 | 二选一 |
| `(1,2,3,6)` | kafkaQueueProblems | 8 | **唯一** |

据此的多数投票分类器：**Top-1 = 24/32 = 0.750，Top-3 = 32/32 = 1.000。**

也就是说 `root_cause_top3 = 1.000` **可以在不读取任何指标数值的情况下达成**，
而它正是三条 baseline 同时报 1.000 的指标之一。签名把候选压到 ≤2 个之后，
再从两个候选里选对一个即可让 `core_e2e` 也满分——这解释了为什么连 `no_rag` 都是 1.000。

`_score_result_v2`（`:931-1011`）本身是严谨的：`core_e2e` 要求标签正确 **且**
required evidence 完备 **且** 未引用 distractor **且** typed claim 成立。
**问题不在 scorer，在数据构造**：`required_evidence` 只有一个组、
它由标签下标推出、且组的存在性模式泄漏了标签。

v1 的泄漏是"`working_set` 无条件出现导致 16 个 case 被误判"（判**错**方向）；
v2 的泄漏是"组存在性模式让 Top-3 免费"（判**对**方向）。
后者更危险，因为它表现为满分而非低分，看上去像成功。

### 应做什么

不是重设计比较条件，也不是引入更难的 split——那会把泄漏一起带进新 split。
按依赖顺序：

1. **消除组存在性泄漏。** 六个组必须在每个 case 都以相同的存在性出现，
   使判别信息只存在于**样本值**里。当前 `_evidence_samples`（`:521-540`）
   按字段是否存在于 observation 来裁剪，这正是签名差异的来源。
2. **`required_evidence` 不得由标签下标推出。** 一个根因应要求**多个**组共同支持
   （例如 adHighCpu 需要 cpu_timeseries **与** 相关 trace），
   否则 `evidence_precision` 与 `core_e2e` 始终共线。
3. **加入真正的 distractor 信号**：非真值组里也应有非零但不足以支持诊断的值，
   使"引用了 distractor"成为一个可犯的错误，而不是一个签名判断。
4. **重跑并要求三条 baseline 分化。** 验收标准不是"分数变低"，
   而是 `no_rag < naive_react` 且 CI 宽度非零——**基线之间必须可区分**，
   否则这批 baseline 无法充当任何门槛的参照物。

只有第 4 步产生分化之后，`best_baseline + 5pp` 才重新有意义。
在此之前 G03 的比较条件既不是"太严"也不是"饱和"，而是**参照物无效**。

### 第 1-3 步的落地状态（metric v3，`AMD-0007`，2026-07-29）

**第 1 步（消除组存在性泄漏）已落地。** collector 改为**标签盲**：六个 evidence 组
（`journey_window` / `trace_activity` / `trace_errors` / `cpu_window` / `memory_window` /
`queue_window`）对所有 label 恒定出现，`build_observation_packet_v3` 不再按标签下标生成
"唯一正确组"。上表那四种签名因此不再存在，判别信息只留在样本值里。7 个门槛数值逐字节不变。

**第 4 步（重跑并要求分化）已于 2026-09-05 取得实测**，但结论与本文件当时的预期不同。
早期五轮 32-case 冻结重放都未跑完，每轮暴露一个此前不可见的缺陷（清单与判定证据见
[gates/G03.md](gates/G03.md) 的"第 4 项的 metric v3 进展"）。此后两轮跑完：

- **r8（288/288）返回 `ready`，但那是假通过。** 分化确实实现了，但幅度由一条 prompt
  从未声明的证据完整性约定制造：live 臂在 94.8–96.9% 的 trial 里诊断正确，
  却因未引用普遍必需的 `trace_activity` 被判失败，而 deterministic 臂按构造直接获得该
  证据集、从不需要推断。分数是 0.8125 / 0.1667 / 0.1458。
- **r9（288/288，2.90 CNY）披露该约定后重测。** `trace_activity` 引用率从 16/96、18/96、
  13/96 升到 96/96、96/96、93/96；分数变为 `naive_react` 0.9167、
  `naive_react_single` 0.8854、`no_rag` 0.8750、`deterministic` 0.8125（垫底）。
  四条配对差**全部含零**，门正确返回 `blocked`。

**这一轮对本文件方法论的确认与修正**：第 0 节"1.000 不是 baseline 太强而是泄漏"的判断
方向正确——去泄漏后 baseline 确实降到 0.875–0.917 且 CI 宽度非零。但本文件隐含的
"去泄漏后 5pp 门槛即可成立"并不完整：`+0.05` 的比较式（0.9667）确实可行了，
而 `max(0.70, best+0.10)` 因 `best_baseline` = 0.9167 要求 `core_e2e >= 1.0167`，
**在单位区间上无解**。也就是说泄漏不是唯一的饱和来源——
"读预装包裹做六选一"这个任务形态本身就已接近天花板。

同样需要记录的是 r8→r9 揭示的**第三类仪器缺陷**：不是泄漏（分数虚高）、
也不是假阴性（跑不完），而是**评分标准未向被测方披露、而对照方按构造豁免**。
它比前两类更隐蔽，因为它让门通过（`ready`）而不是失败，
且它制造的"显著"恰好出现在本应检出它的那条统计条件上。

此处继续记录早期五轮对方法论的影响：

**本文件第 0 节的实测方法（用单一特征做多数投票分类器）是这一轮里最有效的一次诊断**，
因为它不需要跑完整轮实验就能证伪"baseline 太强"。相比之下，第 4 步的五轮失败每轮只换来
一个数据点——失败路径不留观测、首失败即中止。这个不对称本身就是仪器缺陷：
**一次失败应当自带归因**。v3 现已按此改造（失败时保留健康窗口、已取得的 fault/recovery 观测、
以及该 label 每个谓词项的逐观测真值），并新增 `--continue-on-case-failure` 诊断模式
一次性暴露 32 个 case 的完整失败谱，零模型成本。诊断产物强制标注 `diagnostic_only`
且永不可提升为 readiness 证据。

需要记录的是**五个缺陷里有三个是 runner 自己制造的假阴性**，不是被测系统的问题：
fault 窗口从不驱动它所测量的负载、失败路径丢弃全部观测、以及一次瞬时 scrape 缺口
（`cpu_rate` 缺失，而 kafka 谓词根本不读它）直接判败整个 case。
判定性证据都是同一 case 在同一 metric-definition digest 下重跑即通过。
这类缺陷与第 0 节诊断的泄漏方向相反——泄漏让分数虚高，假阴性让实验跑不完——
但性质相同：**都是仪器在测量自己，而不是在测量被测对象。**

### 两处对本审查既有结论的修正（用户复测发现）

- **`core_e2e` 已被聚合。** 本文件第三节说它的门槛表达式
  `max(0.70,best_baseline+0.10)` 无代码解析——该判断基于较早版本，
  治理 v2 代码已实际聚合（`quality_floor_evidence.core_e2e.status = "measured"`）。
- **`fault_family_success` 不应标 N/A。** 它可由现有 family 归属真实计算，
  复测已按四个 family 聚合（`runtime_data` / `dependency_network` /
  `resource_capacity` / `change_config`），本文件原先把它与
  `dead_no_progress_loop` 并列为"应标 not_applicable"是错的。
  当前只有 `tool_schema_validity` 与 `dead_no_progress_loop` 两条 N/A，
  且各自绑定了 G03 的证明义务——这是正确的处置。

另需记录：148/192 的 retro-score（本文件第二节）**只是启发式历史解释**，
不能修复 resource case，也不适合作为新的 G03 基准。用户以完整 fresh v2 复测替代，
这个选择是对的——重打分换不出新的观测。

## 原结论（v1 口径，已由 metric v2 处置）

**现有 eval harness 测的是格式合规，不是诊断能力。** G02 记录的两个分数都是 artifact：
deterministic `0.500` 是规则表缺陷造成的巧合，naive_react / no_rag 的 Root-cause Top-3 `0.000`
约 99% 是标签格式问题。7 条 quality floor 里 5 条从未真正生效。

这不影响 G02 的关闭有效性——G02 的被测对象是**故障实验室本身**，实验室确实建成了。
但如果不修，G03 的 Core E2E 分数会继续测量格式服从度而不是诊断能力。

Memory 与 Trace harness 的情况不同：Trace 侧地基是真的（G01 建成，`REQ-OBS-001` 有实现落点），
Memory 侧**尚不存在** harness，需要在 G04 前设计而不是修补。

## 一、deterministic 0.500 是规则表缺陷

`deterministic_baseline`（`src/faultwitness_dev/g02_baselines.py:279-311`）按 key **存在性** 匹配：

```python
observation_keys = {
    str(key) for item in packet["observations"] if isinstance(item, dict) for key in item
}
signatures = (
    ({"journey_failed", "correlated_error"}, "productCatalogFailure"),
    ({"cpu_rate", "baseline_cpu_max", "correlated_span"}, "adHighCpu"),
    ({"working_set"}, "emailMemoryLeak"),
    ...
)
for required, candidate in signatures:
    if required.issubset(observation_keys):
        root = candidate
        break
```

它**从不读取任何 observation 的值**。而上游有两处让 `working_set` 出现在每一个 case 里：

1. 探针无条件打印它（`g02_lab.py:358-374`），`"working_set": working_set` 与 `cpu_rate`
   并列在同一个 `json.dumps` 里，与 `fault_class` 无关。
2. 每个故障类的 observation 都用 `{**sample}` 全量展开
   （`g02_lab.py:772`、`:782`、`:791`、`:794`），把探针的全部字段带进 packet。

结果：所有 32 个 case 的 `observation_keys` 都含 `working_set`。签名表前两条要求 2–3 个 key
同时命中，只有真正的 productCatalogFailure 与 adHighCpu 能满足；其余全部落到第三条
`({"working_set"}, "emailMemoryLeak")` 被截获。

| 故障类 | case 数 | deterministic 判定 | 正确 |
|---|---:|---|---|
| productCatalogFailure | 8 | productCatalogFailure | 是 |
| adHighCpu | 8 | adHighCpu | 是 |
| kafkaQueueProblems | 8 | emailMemoryLeak | 否 |
| paymentFailure | 4 | emailMemoryLeak | 否 |
| paymentUnreachable | 4 | emailMemoryLeak | 否 |

16 / 32 = **恰好 0.500**。这个数字看起来像"确定性基线只能做到一半"，实际是一条排序错误的
签名规则吃掉了三个故障家族。真实的确定性基线能力被低估，因而 G03 的
"validation E2E ≥ best G02 baseline + 5pp" 这条冻结门槛，其比较基准目前是错的。

## 二、0.000 Top-3 约 99% 是标签格式 artifact

`build_baseline_prompt`（`g02_baselines.py:130-152`）给模型的指令只规定了 **JSON 结构**：

```text
Return exactly one JSON object using these exact keys: root_cause (string),
root_cause_candidates (array of at most three strings), evidence (array of
observation ID strings), and claims (array of objects with claim and supported).
```

它**从不披露封闭标签集**。而 `score_result:371` 用字符串全等比对：

```python
top3 = actual == expected or expected in candidates[:3]
```

`expected` 来自 `_scenario_cases:558`，值是内部 flagd 枚举名——`productCatalogFailure`、
`kafkaQueueProblems`、`paymentUnreachable` 这类 camelCase 标识符。模型没有任何途径知道
必须输出这个拼写，于是任何语义正确但措辞不同的答案（"product catalog service failure"、
"Kafka consumer lag"）都判 0。

用严格的同义词→标签映射对那 192 条冻结 trial 重新打分：

| 故障类 | 重打分命中 | 说明 |
|---|---|---|
| productCatalogFailure | 48/48 | 完全可归一化 |
| kafkaQueueProblems | 48/48 | 完全可归一化 |
| paymentFailure | 24/24 | 完全可归一化 |
| paymentUnreachable | 24/24 | 完全可归一化 |
| adHighCpu | 4/24 | case 构造缺陷，见第四节 |
| emailMemoryLeak | 0/24 | case 构造缺陷，见第四节 |
| **合计** | **148/192 = 0.771** | |

也就是说记录中的 `0.000` 与真实诊断能力的差距大约是 **0.77**。这个重打分**不是**对 G02 结论的
修订——它没有新的模型调用，只是对同一批冻结输出换一个归一化口径。它应当作为一份显式标注
"非 Gate 证据"的独立产物发布，`docs/gates/G02/REPORT.md` 不应改动：`0.000` 作为
"当时的 scorer 就是这么定义的"这一诚实历史记录保留。

## 三、7 条 quality floor 里 5 条不成立

`QUALITY_FLOORS`（`g02_baselines.py:23-31`）声明 7 个门槛。逐条对上代码：

| floor | 值 | 实际状态 |
|---|---|---|
| `core_e2e` | `"max(0.70,best_baseline+0.10)"` | 当时：字符串，`:773-778` 的聚合循环只含 4 个指标不含它。**此判断基于较早版本，v2 已由 `resolve_quality_floor` 解析并聚合，见第 0 节修正** |
| `root_cause_top3` | ≥0.85 | 真实计算，但受第二节的标签问题污染 |
| `evidence_precision` | ≥0.90 | **无法答错。** 见下 |
| `unsupported_critical_claim` | ≤0.02 | 依赖模型自报 `supported: false`，等于让被测者自评 |
| `tool_schema_validity` | ≥0.99 | **硬编码 `1.0`**（`:396`）。第二轮补充三点机制细节，见下 |
| `dead_no_progress_loop` | <0.01 | **从未被计算。** 只存在于 `QUALITY_FLOORS`、两份冻结 `threshold-registry.json` 和一个 registry 相等性测试。第二轮给出了可计算定义：见 [CROSS_GATE_INTERFACES.md](CROSS_GATE_INTERFACES.md) 规格 3 —— 复用 `ProgressDigest.digest` 已是内容哈希这一事实，"无进展"= 本步 digest 与上一步相同 |
| `fault_family_success` | ≥0.55 | 当时：从未被计算。**v2 已按四个 family 真实聚合——本文件原先建议标 N/A 是错的，见第 0 节修正** |

### `tool_schema_validity` 的三点机制补充（第二轮）

1. **G02 的两条 live baseline 从不调用工具**（`no_rag` 的 `max_tool_calls: 0`，
   `g02_baselines.py:93-97`）。即使改成真实计算，在 G02 口径下该指标也无内容可测——
   它必须等 G03 有真实工具后才第一次有意义。这解释了为什么硬编码在 G02 时"看起来无害"。
2. **畸形 trial 对该指标的贡献是按键缺失偶然产生的，不是测量出来的。**
   `score_result:362-367` 返回的畸形结果字典里**没有 `tool_schema_validity` 键**，
   而 `percentile_cluster_bootstrap:406` 用 `float(row.get(metric, 0.0))` 读取，
   缺失默认 0.0。数值恰好对，机制是错的。
3. **`RESULT_SCHEMA` 是完整的死代码。** `g02_baselines.py:45-70` 定义了一份带
   `additionalProperties: False` 的完整 JSON Schema，全仓库仅定义处一个引用，
   从未传给任何 validator；实际生效的是更宽松的手写 `validate_result:314-354`。

第 3 点与产品侧对比后是本轮最反直觉的发现：`models/gateway.py:106-117`
有真实的 Draft 2020-12 校验，而评测侧有一份完整 Schema 却不用它。
**两条路径的严格程度不一致，且严格的那条没有进评测。**
详见 [MODEL_LAYER_REVIEW.md](MODEL_LAYER_REVIEW.md) 缺口 1。

`evidence_precision` 为什么无法答错（`score_result:380-388`）：

```python
precision = (
    1.0 if evidence and all(
        str(item) in {str(x) for x in ground_truth.get("evidence", evidence)}
        for item in evidence
    ) else 0.0
)
```

两个问题叠加。其一，`ground_truth.get("evidence", evidence)` 的**默认值是 `evidence` 自身**，
ground truth 缺失时自动满分。其二，`_scenario_cases:551-558` 把 packet 里**全部** observation ID
填进 ground truth：

```python
evidence = [str(item.get("id")) for item in packet["observations"] if ...]
cases[case_id] = {"ground_truth": {"root_cause": fault_class, "evidence": evidence}, ...}
```

于是 ground truth 是全集，任何非空子集都得 `1.0`。**不存在可以答错的干扰项。**

`validate_threshold_registry:111-113` 只做一次 dict 相等比较，它能保证 7 个数值没漂移，
但完全不检查这些 floor 是否被计算过。这是"门槛看起来齐全但一半空转"的机制原因。

## 四、adHighCpu 4/24 与 emailMemoryLeak 0/24 是 case 构造缺陷

这两个家族即使换了归一化口径也答不对，原因不在模型。

`resource_capacity` 家族给模型的是**裸数值**：

- `adHighCpu`：`cpu_rate` + `baseline_cpu_max` + `correlated_span`（`g02_lab.py:770-779`）
- `emailMemoryLeak`：`working_set` + `email_stimulus_count`（`:780-788`）

`working_set` 是一个没有服务归属、没有单位、没有基线值、没有采样窗口的数字。模型看到
`working_set: 41582592` 无法判断这是正常还是泄漏——对比其他家族给的是
`checkout_failed: true` / `payment_error: true` 这类已经语义化的布尔信号。

`emailMemoryLeak` 甚至连基线都没有（`adHighCpu` 至少有 `baseline_cpu_max`）。0/24 是 case
不可解，不是 agent 不行。不修的话 G03 的 Core E2E 会被这 8 个 case（32 个中的 1/4）
压在 0.75 附近，与 agent 质量无关。

## 五、Trace harness：地基真实，但缺重放

Trace 侧与 eval 侧不同，G01 建成的东西是真的：`REQ-OBS-001` 有实现落点，
SSE 有 `Last-Event-ID` 续传、retention gap 与 slow consumer 控制事件
（`src/faultwitness/api/app.py:235-297`）。`TraceSanitizer` 的 `_DENIED_KEY_PARTS`
对 casefold 后的 key 做**子串**匹配且包含 `token`，所以 `model.tokens.input`
会被拒——这是正确的严格性，指标命名应该迁就它（用 `model.usage.input_units`），
不是反过来放宽 denylist。

真实缺口是**重放**。`AGENTS.md` 的 badcase triage 前两步要求"Trace 重放同一任务"与
"固定模型输出隔离随机性"，两者目前都没有实现。没有重放能力，badcase 归因只能靠读日志推断，
而"能把失败定位到规划/检索/工具/模型/记忆中的具体环节"是立项报告 §0.1 的一票否决项。

建议以 `(trial_id, call_ordinal, prompt_digest)` 为键从 journal 回放模型响应，
`prompt_digest` 不匹配即报错而非静默穿透到真实 provider——否则"重放"会偷偷变成"重跑"。

## 六、Memory harness：尚不存在

`src/faultwitness/` 下**没有 `memory/` 包**。立项报告 §9 与 §12.2 要求的六个指标
（写入 Precision、读取 Recall、冲突检测率、过期记忆误用率、压缩后约束保持率、
记忆导致的性能提升或负迁移）目前一个都无法表达。

结构性障碍是：**现有 harness 是单发的，trial 之间互相独立。** 而上面六个指标里至少四个
需要跨 episode 的顺序依赖——"过期记忆误用"必须先写入、再让它过期、再观察是否被误用。

四个设计决定应在 G04 计划里冻结：

- **memory state 作为内容寻址的派生产物**，从 `memory_ops` 日志重放得出，而非活的可变外部状态。
  只有这样它才能进 journal 的 artifact digest。`experiment.py` 的 `depends_on` +
  `dependency_artifacts` **已经**能表达顺序依赖的失效传播，`ExperimentUnit` 与 cache-key
  语义不需要改；真正的缺口只是"memory store 是 journal 之外的活状态"。
- **逻辑时钟**，不用 wall-clock。过期记忆误用率必须可确定性复现。
- **配对 `memory_mode` on/off arm**，同 case 同 seed，用于分离负迁移。这是唯一能回答
  "记忆到底有没有用"的形态，也直接对应 §21.5 点名的失败路径。
- **bootstrap `cluster_key` 从 `case_id` 改为 `sequence_id`**（现为 `g02_baselines.py:104`）。
  跨 episode 后同一序列内的 trial 不再独立，按 case 聚类会低估方差。这一改动需要单独一条修正案。

## 七、修复顺序

不降低任何严谨性的硬约束先说清楚：**7 个门槛数值逐字节不变**，改的是**定义**，
通过 `metric_version: 2` 标注；不编辑 `docs/gates/G02/REPORT.md`；不弱化 sanitizer；
不引入新 harness / lifecycle / manifest（`AGENTS.md` 的 direct debug loop 约束）。

按依赖排序，1→3→4 不可重排。状态列按 metric v2 实施后的实际情况更新：

| # | 项 | 规模 | 关键位置 | 状态 |
|---|---|---|---|---|
| 1 | floor 覆盖硬化：未挣得的 pass 转为显式 `not_applicable` + 证明义务 | S | `g02_baselines.py:23` | **已完成**（5 条 measured / 2 条 N/A 带证明义务） |
| 2 | 修正案：冻结 `metric_version: 2` 的定义变更 | S | `docs/blueprint/AMENDMENTS/` | **已完成**（`AMD-0006`） |
| 3 | scorer v2：披露封闭标签集 + 类型化可机检 claim | M | `g02_baselines.py:130,357` | **已完成** |
| 4 | case schema 加 `required_evidence` / `distractor_evidence`；修 `resource_capacity` 归属与单位 | M | `g02_lab.py:105,770` | **部分**——字段已加、8 个 resource case 已修，但 `required_evidence` 只有一个组且由标签下标推出，见第 0 节 |
| 5 | `deterministic_baseline` 签名表改为读值而非读 key 存在性 | S | `g02_baselines.py:279` | **已完成**（`_deterministic_v2`） |
| 6 | v2 定义下重测 3 条 baseline，重新确立 G03 门槛基准 | M | `run_gate_*_matrix` | **已跑，未达成目的**——三条同分 1.000，参照物无效 |
| 7 | sanitizer allowlist 增补 usage/cost/evidence-ref 属性 | S | `sanitizer.py` | 未做 |
| 8 | operator experiment CLI + 类型化 `UnchangedSemanticInputsError` | M | `cli.py`, `experiment.py` | 未做 |
| 9 | journal-backed replay adapter | M | `experiment.py` | 未做 |
| 10 | **消除组存在性泄漏，令三条 baseline 分化**（新增，第 0 节） | M | `g02_baselines.py:521,652,1208` | 未做，**G03 新的唯一阻塞项** |

第 10 项现在取代第 6 项成为 G03 的准入前提：第 6 项已执行完毕，但它产出的参照物
不可用，重跑必须在第 10 项之后。`audit.py` 接回 `verify-fast` 亦已完成（349 tests passed）。

第 1 项的实施口径（已落地，此处保留作记录）：`QUALITY_FLOORS` 保留 7 键 7 值不动，
为每键增加 `evidence` 字段声明由哪个 runner 计算；scorer 里让"未计算的 floor"抛
`GovernanceError` 而不是静默视为通过。实施时只有 `tool_schema_validity` 与
`dead_no_progress_loop` 标了 `not_applicable`——本文件原稿把 `fault_family_success`
一并列入是错的，实际实施没有照抄这一点，是对的。

第 8 项对应 [GOVERNANCE_REVIEW.md](GOVERNANCE_REVIEW.md) 残留 4 的 operator 缺口。
`experiment.py` 那条裸 `GovernanceError`（`cannot retry unchanged semantic inputs after metric_fail`）
规则本身正确——防止不改语义就刷分——但它只说"不许"，不说"改哪个 checkpoint 才能合法重跑"。
换成类型化异常并在消息里给出出路即可，不需要新机制。

## 八、验证口径

1. `uv run python -m faultwitness_dev verify-fast` 全绿是每一项的准入条件。
2. `tests/governance/test_governance_v2.py` 必须继续全绿，特别是
   `test_eval_one_trial_resume_reproduces_frozen_192_trial_aggregate`：v2 打分走新
   `metric_version`，旧断言必须仍成立。
3. floor 硬化需新增负例：断言未计算的 floor 抛 `GovernanceError`。
4. scorer v2 需对 32 个 case 各跑一次负例（malformed / 未归一化标签 / 引用 distractor），
   三类都必须落到明确的 `failure_class`。
5. `deterministic_baseline` 修复后重跑矩阵，确认 16 个 emailMemoryLeak 误判归零。
6. retro-score 产物自带"非 Gate 证据"标记，并有一条测试断言
   `docs/gates/G02/REPORT.md` 未被修改。

### 第 0 节（组存在性泄漏）的额外验证口径

以上 1-6 条已由 metric v2 实施满足。第 10 项另需三条**泄漏本身**的验收，
它们检验的不是分数高低而是分数是否可被非诊断特征取得：

7. **非诊断分类器基线必须失效。** 新增一条测试：仅用"哪些 evidence 组非空"
   构造多数投票分类器，断言其 Top-3 **显著低于 1.000**。这一条是第 10 项的
   充分性判据——修完若该分类器仍能拿 1.000，说明泄漏没消除。
8. **三条 baseline 必须可区分。** 断言 `no_rag` 的 `core_e2e` 严格小于 `naive_react`，
   且两者 95% CI 宽度非零。同分即视为参照物无效，不得据以设定门槛。
9. **`required_evidence` 不得单元素。** 断言每个 case 的 `required_evidence` 长度 ≥2
   且不等于 `ROOT_CAUSE_LABELS.index(label) + 1` 推出的单组，
   使 `evidence_precision` 与 `core_e2e` 解除共线。
