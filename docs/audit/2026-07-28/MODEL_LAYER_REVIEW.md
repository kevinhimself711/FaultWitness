---
document_id: FW-AUDIT-2026-07-28-MODELLAYER
audit_date: 2026-07-28
authoritative: false
question: model_inference 是 JD 第三高主题，为什么 57 条需求里没有一条承接它
---

# 模型层与推理层审查

## 为什么补这一份

第一轮审查漏了一个主题。按 [REQUIREMENT_COVERAGE.md](REQUIREMENT_COVERAGE.md) 的覆盖率表：

| 主题 | JD 覆盖 | 面经覆盖 | 排名 |
|---|---:|---:|---|
| agent_architecture | 100% | 95% | 1 |
| project_depth | 100% | 90% | 2 |
| **model_inference** | **95%** | **81%** | **3** |

`model_inference` 是两侧覆盖率第三高的主题，且面经 81% 高于 `tools_mcp_skills`(65%)、
`rag_retrieval`(69%)、`memory_context`(64%) 全部。但在第一轮的 T1–T4 分级里，
**它没有任何一条需求落点**——57 条需求中没有一条以模型调用层为主体。

第一轮把它一句带过（"高频，但多为原理问答而非要求实现"）。这个判断只有一半对：
原理问答确实占多数，但立项报告 §6.5 有六条**明确的实现要求**，
§12 有两条**明确的指标要求**。它们目前没有任何需求承接。

## 一、纠正一个事实：Model Gateway 已经存在且质量不低

第一轮的实现状态核对（[REQUIREMENT_COVERAGE.md](REQUIREMENT_COVERAGE.md) 第五节）
列出了缺失的包，但没有核对 `src/faultwitness/models/`。核对后的结论是**它已实现，
且实现了报告 §6.5 的多数条目**：

| §6.5 要求 | 状态 | 证据 |
|---|---|---|
| 统一封装 Provider、模型版本、超时、重试、并发、Token、费用、Trace | 已实现 | `models/catalog.py`、`models/types.py:62-107` |
| 关键输出使用 JSON Schema/Pydantic 校验 | **已实现** | `models/gateway.py:106-117` Draft 2020-12 真实校验 |
| 解析失败进入修复或降级，不直接继续执行 | **已实现（有界）** | `gateway.py:187-197` 一次修复后抛出 |
| 按任务路由模型 | **未实现** | `RoutePolicy.routes` 只有 `ModelFamily` 维度 |
| 主模型、备用模型、不可用降级 | 部分 | 候选 profile 列表存在，但单上游下实际长度为 1 |
| Prompt、模型、参数、Schema 版本化并写入每次 Trace | **未实现** | `prompt_version` / `prompt_digest` 在 `src/faultwitness/` 零命中 |
| 缓存 Key 含模型版本、Prompt 版本、输入哈希、权限范围 | **未实现** | `models/` 下 `cache` 零命中 |

`gateway.py:106-117` 的实现值得肯定，它是全项目最贴近生产写法的一段：

```python
Draft202012Validator.check_schema(schema)
value = json.loads(result.content)
if not isinstance(value, dict):
    raise ValidationError("structured output root must be an object")
Draft202012Validator(schema).validate(value)
```

修复次数被类型本身钉死为至多 1 次（`models/catalog.py:33` `Field(default=1, ge=0, le=1)`，
`types.py:77` `repair_count` 同界）。**这是一个好设计**——它使"修复"不可能退化成隐式重试循环，
而"无界修复"正是 §0.1"没有卡循环控制"在模型层的表现形式。

所以这一节的结论不是"缺失能力"，而是：**已有一个不错的实现，但它既没有需求承接，
也没有进入任何评测，因此在面试中无法被证明。**

## 二、三个真实缺口

### 缺口 1：结构化输出合法率从未被测量

报告 §12 `:904` 把"结构化输出合法率"列为质量指标，`:951` 给出阈值
"工具参数 Schema 合法率 ≥ 99%"。这正是 `QUALITY_FLOORS` 里 `tool_schema_validity ≥ 0.99`
的来源。但该指标在 `score_result` 里硬编码：

`g02_baselines.py:396` — `"tool_schema_validity": 1.0`

第一轮已在 [EVAL_HARNESS_REVIEW.md](EVAL_HARNESS_REVIEW.md) 第三节记录了硬编码这一事实。
本轮补充三点更精确的机制：

1. **G02 的两条 live baseline 从不调用工具**（`no_rag` 的 `max_tool_calls: 0`，
   `g02_baselines.py:93-97`）。所以即使改成真实计算，在 G02 的口径下这个指标也无内容可测。
   它必须在 G03 有真实工具后才第一次有意义。
2. **畸形 trial 对该指标的贡献是"按键缺失偶然产生"的，不是测量出来的。**
   `score_result:362-367` 返回的畸形结果字典里**没有 `tool_schema_validity` 键**，
   而 `percentile_cluster_bootstrap:406` 用 `float(row.get(metric, 0.0))` 读取，
   缺失默认 0.0。数值恰好是对的，但机制是错的——依赖键缺失而非显式计分。
3. **`RESULT_SCHEMA` 是完整的死代码。** `g02_baselines.py:45-70` 定义了一份带
   `additionalProperties: False` 的完整 JSON Schema，全仓库仅定义处一个引用，
   从未传给任何 validator。实际生效的是手写检查 `validate_result:314-354`。

**这是本轮最反直觉的发现**：产品侧 `gateway.py` 有真实的 Draft 2020-12 校验，
而评测侧 `g02_baselines.py` 有一份完整 Schema 却不用它，改用手写字段检查。
两条路径的严格程度不一致，且严格的那条没有进评测。

### 缺口 2：Prompt 与 Schema 版本未进 Trace

报告 `:459`："Prompt、模型、参数和 Schema 都必须版本化，并写入每次 Trace。"

`prompt_version`、`prompt_digest`、`params_version` 在 `src/faultwitness/` 全部零命中。
`schema_version` 的命中全部来自 `contracts/compiler.py`，是契约编译产物，与模型调用无关。

这一条的价值不在"版本化"本身，而在它是**评测可复现性的前置条件**：
如果 Trace 里没有 prompt 版本，那么"这次分数变化是因为改了 prompt 还是改了模型"
无法回答。它直接支撑 `REQ-EVAL-003`（可复现，T1 核心）与 §0.1
"拿不出测试集、计算公式、样本数和实验报告"。

也是 [EVAL_HARNESS_REVIEW.md](EVAL_HARNESS_REVIEW.md) 里 replay adapter 的
`prompt_digest` 键的来源——**该键当前没有任何生产侧字段可对应**。

### 缺口 3：按任务路由与缓存 Key 均未实现

报告 `:457`："根据任务路由模型：确定性分类优先规则/小模型，复杂规划和验证才用强模型。"
`:460`："缓存只用于可安全复用的纯函数步骤；缓存 Key 包括模型版本、Prompt 版本、
输入哈希和权限范围。"

`RoutePolicy.routes` 的类型是 `dict[ModelFamily, tuple[str, ...]]`（`catalog.py:31`），
只有模型族维度，没有任务维度。`models/` 目录下 `cache` 零命中。

按分级判断，这两条的处理**不同**：

- **按任务路由：应实现，成本低价值高。** 它是 `REQ-PERF-004`（缓存与上下文缩减，
  第一轮已定为 T3 降级）的天然搭档，且"什么时候不该用强模型"是一个具体的成本判断，
  比"我做了模型路由"可讲述性强得多。
- **四元缓存 Key：应实现但只做纯函数步骤。** 关键是 Key 里的**权限范围**这一维——
  它防止跨租户缓存命中，是一个真实的安全边界，直接关联 G06 的跨租户泄漏零容忍。
  缓存本身收益有限，但"缓存 Key 里为什么必须有 tenant"是一个好问题。

### 附带发现：部署态下 gateway 的失败事件无处可去

`gateway.py:230-237` 通过 observer 记录 `model_attempt_failed` 与 `failure_code`，
这是 `invalid_structured_output` 唯一的可观测出口。但 `NullObserver` 是默认
（`gateway.py:38-40`），且 `create_app` 构造 gateway 时不传 observer（`models/server.py:75`）。
HTTP 边界（`server.py:125-130`）只返回 `{"code", "retryable"}`，不发射任何指标。

所以在部署态下，**结构化输出失败率即使发生也不可见**。这不是评测缺陷，是可观测缺陷，
落在 `REQ-OBS-001`（T1 核心）范围内。

## 三、建议新增一条需求

第一轮的分级是对既有 57 条做取舍，没有新增。本轮建议**新增一条**，
因为它对应的是一个已实现但无人承接的模块，且落在 JD 第三高主题上。

> **REQ-MODEL-001（建议，P0 支撑档）：模型调用层可证明。**
>
> Statement：模型网关对全部关键输出执行 Schema 校验，解析失败进入有界修复或显式降级；
> Prompt、模型、参数与 Schema 版本写入每次 Trace；按任务类型路由模型；
> 缓存仅用于纯函数步骤且 Key 含权限范围。
>
> Verification：报告结构化输出合法率（绝对值与样本数）、修复成功率、
> 各失败码分布；提供一个畸形输出负例测试与一个跨租户缓存命中拒绝的负例测试；
> 任一 Trace 可取出其 prompt 与 schema 版本。
>
> Gates：G03（合法率与版本化）、G08（任务路由与缓存对照）。

**为什么是 P0 支撑档而不是 T1 核心**：它不构成 §0.1 的任何一条一票否决项，
也不是 L3 十条门槛的唯一落点。但它是 JD 95%/面经 81% 主题的唯一落点，
且**实现成本极低**——gateway 主体已存在，缺的是版本字段、指标聚合与两个负例测试。

## 四、对既有 Gate 设计的增补

不改动任何冻结退出数值。以下是需要写进对应 Gate 的增补项：

### G03 增补

在 [gates/G03.md](gates/G03.md) 的 I-G03-02（六个只读工具与契约）中：

- `tool_schema_validity` 改为真实计算时，**必须同时接入 `gateway.py` 的
  `INVALID_STRUCTURED_OUTPUT` 与 `INVALID_TOOL_ARGUMENTS` 两个失败码**，
  而不是只统计 `validate_result` 的结果。两者衡量的是不同层：
  前者是模型是否产出合法 JSON，后者是工具参数是否符合子 schema。
- **让 `RESULT_SCHEMA` 生效或删除它。** 保留一份从未使用的完整 Schema
  是一个真实的可维护性缺陷，且它比手写 `validate_result` 更严格
  （带 `additionalProperties: False`）。倾向于让它生效。

在 I-G03-06（预算与成本）中增补：

- Prompt 与 Schema 版本写入 Trace。这一项与成本归因共享同一个 span 属性写入点，
  合并做的边际成本接近零。
- 属性命名仍须迁就 `_DENIED_KEY_PARTS` 的子串匹配，与成本字段同一约束。

### G08 增补

在 [gates/G08.md](gates/G08.md) 中，第一轮已排除"Batch 与 Model Routing 对照"，
理由是单上游下测不出效果。**这个判断需要修正一半**：

- **Batch 对照仍应排除**——它确实依赖多上游或本地推理。
- **按任务路由应保留**，因为它不依赖多上游。同一个 Bailian upstream 下，
  Qwen / DeepSeek / GLM 三个模型族的**能力与价格不同**，
  "确定性分类用小模型、复杂规划用强模型"这个对照在单上游内完全可测，
  且它产出的是一个成本数字，不是"无显著差异"。

这是第一轮的一处判断偏差：我把"单上游"等同于"无法做模型层对照"，
但三个模型族的差异本身就是可测的对照维度，报告 §6.5 要求的也是按**任务**路由，
不是按 provider 容灾。

## 五、明确不做

- **本地推理、Continuous Batching、Prefix/KV Cache。** 报告 `:839` 写的是
  "根据数据决定是否引入"——这是一个条件句，不是要求。单机 K3s + 单张 4090
  已被 G09 的训练 smoke 占用，本地推理服务没有硬件余量。
  应在 FINAL_PLAN 的"主动排除"表里记录该判断及依据。
- **多 provider 容灾。** §7 已声明单 live upstream，不得表述为跨供应商容灾。
- **完整 prompt 管理系统。** 版本化只需 digest + 版本号进 Trace，
  不建 prompt 注册表、A/B 分流或模板编辑界面。
