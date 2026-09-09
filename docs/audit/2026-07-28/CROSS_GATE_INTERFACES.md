---
document_id: FW-AUDIT-2026-07-28-INTERFACES
audit_date: 2026-07-28
authoritative: false
question: FINAL_PLAN_PROPOSED §8 说"必须提前预留接口"，但没有一处给出字段级规格
---

# 跨 Gate 接口规格

## 为什么补这一份

[FINAL_PLAN_PROPOSED.md](FINAL_PLAN_PROPOSED.md) §8 列了 12 条跨 Gate 联动，
每条都写了"提前预留什么"，但全部是自然语言描述。例如第一行：

> `REQ-OBS-001` | G01→G03→G04 | **EvidenceRef 必须在 G03 就支持
> source/version/section/chunk 四级定位**，即使 G03 只用 observation 一级。

这句话无法验证。"四级定位"是哪四个字段名？类型是什么？可选还是必填？
没有规格，G03 的实施者只能自行猜测，而 G04 发现不匹配时已经晚了——
这恰好是该条联动想要避免的返工。

**一句"必须预留"不构成接口约束。** 本文件把 §8 的 12 条联动中
**会导致结构性返工的 5 条**转成字段级规格，其余 7 条是行为约定而非数据结构，
不需要提前定义字段。

## 现状核对：契约层比预期完整

先纠正第一轮的一个印象。[REQUIREMENT_COVERAGE.md](REQUIREMENT_COVERAGE.md) 第五节
说"`SkillManifest` 与 `ActionTransaction` 只是契约模型，无实现"，
这一句是对的，但它容易被读成"契约也不完整"。核对 `src/faultwitness/contracts/models.py` 后：

| 类型 | 行 | 状态 |
|---|---|---|
| `EvidenceRef` | 323-327 | 存在，含 `source_ref` / `observed_at` / `artifact_digest` |
| `SourceVersionRef` | 231-233 | 存在，**只有 `source_id` + `source_version` 两级** |
| `Hypothesis` | 330-334 | 存在，含 `supporting_evidence` **与 `contradicting_evidence`** |
| `ProbePlan` | 337-341 | 存在，含 `expected_information_gain` |
| `ActionProposal` | 379-386 | 存在，含 `action_digest` + `resource_version` |
| `ActionTransaction` | 399-404 | 存在，含 `idempotency_key`（`repr=False`）|
| `BudgetCounters` | 218-222 | 存在，含 `steps/model_calls/tokens/cost_usd` |
| `ProgressDigest` | 225-228 | 存在，含 `evidence_count` / `supported_claim_count` |
| `ToolResult` | 357-369 | 存在，带 status/error_code 一致性校验 |
| `Lease` | 302-306 | 存在，含 `fencing_token` |

**这是一个比第一轮描述更好的起点。** 三处设计已经预判了后续 Gate 的需要：

- `Hypothesis.contradicting_evidence` —— 对抗证据不是后加的，G04 的冲突检测有位置可挂。
- `ActionProposal.action_digest` + `resource_version` —— G05 的 Digest 幂等与
  "资源版本变化使审批失效"两条安全不变量的字段已就位。
- `Lease.fencing_token` —— G06 的 lease 语义用的是 fencing token 而非单纯过期时间，
  这是正确的做法（单纯过期时间无法防止旧 Worker 的延迟写入）。

所以以下 5 条规格是**增补**，不是重建。

## 规格 1：EvidenceRef 四级定位（G03 必须，G04 依赖）

**缺口**：`SourceVersionRef` 只有两级。G04 的 citation precision 要求
"source / version / section / chunk 四级定位"（`REQ-RAG-004`）。
若 G03 只按现状使用，G04 需要修改 `EvidenceRef` 这一核心结构，
而它届时已被 G03 的全部 Evidence 与 Trace 引用。

**规格**：新增一个可选的定位段，`SourceVersionRef` 本身不动（避免破坏现有引用）。

```text
class SourceLocator(ContractModel):        # 新增
    section_path: tuple[NonEmptyText, ...] = ()   # 层级路径，如 ("ch3","3.2")
    chunk_id: NonEmptyText | None = None
    chunk_index: int | None = Field(default=None, ge=0)
    char_span: tuple[int, int] | None = None      # 半开区间 [start, end)

class EvidenceRef(ContractModel):          # 增补一个字段
    evidence_id: EvidenceRefId
    source_ref: SourceVersionRef
    locator: SourceLocator | None = None   # <- 新增；G03 留空，G04 填充
    observed_at: UtcDateTime
    artifact_digest: Sha256
```

**为什么可选**：G03 的证据是 observation ID，没有 section/chunk 概念。
强制必填会迫使 G03 填入无意义的占位值。`None` 明确表示"该证据不是文档片段"。

**G03 的义务**（不是 G04 的）：
1. `locator` 字段存在于契约与生成的 JSON Schema 中。
2. 至少一个契约测试断言 `locator=None` 的 `EvidenceRef` 可序列化并往返。
3. Trace 的 evidence span 属性保留 `locator` 的位置，即使值为空。

**验证方式**：G04 开工时不得修改 `EvidenceRef` 的现有字段。若需要修改，即为 G03 未履行本规格。

## 规格 2：Typed terminal reason（G03 建立，G07 扩展）

**缺口**：`BudgetCounters` 记录了四个计数器，但没有任何字段表达
"因为哪个守卫而终止"。[gates/G03.md](gates/G03.md) 的 I-G03-03 要求八个守卫
各自独立可触发并"保留 typed terminal reason"——该类型不存在。

同时 [gates/G07.md](gates/G07.md) 的 badcase 分类需要以它为基础
（§8 第五行：`REQ-AGT-002` G03→G07）。

**规格**：

```text
class TerminalReason(StrEnum):             # 新增，G03 定义
    COMPLETED = "completed"
    MAX_STEPS = "max_steps"
    MAX_WALL_TIME = "max_wall_time"
    MAX_MODEL_CALLS = "max_model_calls"
    MAX_TOKENS = "max_tokens"
    MAX_COST = "max_cost"
    MAX_RETRIES = "max_retries"
    REPETITION_DETECTED = "repetition_detected"
    EVIDENCE_EXHAUSTED = "evidence_exhausted"
```

九个成员 = 一个正常完成 + 八个守卫。**枚举必须与守卫一一对应且可穷举**，
这样"八个守卫各有一个 chaos case 单独触发"才是机器可检的：
测试断言全部八个非 `COMPLETED` 成员都至少被触发一次。

**扩展规则**：G07 的 badcase 分类**不得**向本枚举追加成员。
badcase 分类是另一个维度（失败的**原因**），terminal reason 是**终止方式**。
两者交叉成表，不是同一个枚举。这一条约束防止 G07 把 13 类 badcase
塞进 terminal reason 从而破坏 G03 的八守卫一一对应关系。

## 规格 3：Dead-loop 信号（G03 建立，让空转 floor 生效）

**缺口**：`dead_no_progress_loop` 是 7 条 quality floor 之一（`<0.01`），
但 [EVAL_HARNESS_REVIEW.md](EVAL_HARNESS_REVIEW.md) 已证实它从未被计算。
`ProgressDigest` 有 `evidence_count` 与 `supported_claim_count`，
但没有任何字段能判定"这一步是否产生了进展"。

**规格**：

```text
class ProgressDigest(ContractModel):       # 增补两个字段
    evidence_count: int = Field(ge=0)
    supported_claim_count: int = Field(ge=0)
    no_progress_streak: int = Field(default=0, ge=0)   # <- 新增
    digest: Sha256
```

`digest` 已经是内容哈希，因此"无进展"可定义为：**本步结束时 `digest` 与上一步相同**。
`no_progress_streak` 是该条件连续成立的次数，达到阈值即触发
`REPETITION_DETECTED`（规格 2）。

**为什么这样定义**：它不需要新的判定逻辑，复用已有的 `digest`。
`dead_no_progress_loop` 指标 = 触发 `REPETITION_DETECTED` 的 trial 占比。
这使该 floor 第一次可计算，且定义可在报告里一句话说清。

## 规格 4：Checkpoint 的已提交/已计划区分（G03 建立，G05 依赖）

**缺口**：§8 第二行要求"checkpoint 需区分'已提交'与'已计划'，G05 才能扩到外部副作用"。
`ActionTransaction` 有 `state` 与 `state_version`，但 G03 是只读 Gate，
其 checkpoint 不经过 `ActionTransaction`。

若 G03 的 checkpoint 只记录"到第几步"，G05 恢复时无法判断
最后一个动作是**已经发出**还是**只是计划发出**——这正是重复外部副作用的来源，
而"重复外部副作用为 0"是 G05 的冻结零容忍标准。

**规格**：G03 的 checkpoint 记录中，每个待执行意图必须处于两段式状态之一：

```text
class IntentPhase(StrEnum):                # 新增
    PLANNED = "planned"      # 已写入 checkpoint，尚未离开进程
    DISPATCHED = "dispatched"  # 已交给执行者，结果未知
    SETTLED = "settled"      # 结果已知并已写入 checkpoint
```

**恢复语义**（G03 建立，G05 直接沿用）：

| 恢复时状态 | G03（只读）动作 | G05（有副作用）动作 |
|---|---|---|
| `PLANNED` | 直接重新执行 | 直接重新执行（安全） |
| `DISPATCHED` | 重新执行（只读幂等） | **不得重试**，进入 UNCERTAIN 对账 |
| `SETTLED` | 跳过 | 跳过 |

**这张表是 G03 与 G05 之间最关键的接口**。G03 因为只读，三种状态都可以重试，
所以很容易写出一个不区分状态的 checkpoint 而测试全绿。
但 G05 的 `DISPATCHED` 行为完全不同——若 G03 没有留下这个状态，
G05 必须重构 checkpoint 结构。

**G03 的义务**：即使三种状态在只读语义下行为相同，也必须**分别记录**，
并有一个测试断言 `DISPATCHED` 状态可从 checkpoint 中读出。

## 规格 5：工具 catalog 的 MCP 投射位（G03 建立，G04 投射）

**缺口**：§8 第四行要求"工具 catalog 结构支持 MCP 只读子集投射"。
`ToolDefinition`（`models.py:344-348`）有 `input_schema_ref` / `output_schema_ref` / `risk`，
但没有任何字段标记"该工具是否可经 MCP 暴露"。

**规格**：

```text
class ToolDefinition(ContractModel):       # 增补两个字段
    tool_id: ToolId
    input_schema_ref: NonEmptyText
    output_schema_ref: NonEmptyText
    risk: RiskLevel
    mcp_exposed: bool = False              # <- 新增，默认不暴露
    side_effect_free: bool                 # <- 新增，必填
```

**两个字段而非一个**，因为它们是不同的判断：
`side_effect_free` 是工具的**事实属性**；`mcp_exposed` 是一个**策略决定**。
默认 `False` 是 fail-closed——新增工具默认不对外暴露。

**不变量**（G03 就应有测试）：`mcp_exposed=True` 蕴含 `side_effect_free=True`
且 `risk == R0`。这条不变量使"MCP 只暴露只读子集"成为契约层的强制约束，
而不是 G04 实施时的口头约定。

## 不需要提前定义字段的 7 条联动

§8 的其余 7 条是**行为约定**，不涉及跨 Gate 共享的数据结构，因此不需要本文件的规格：

| 联动 | 为什么不需要字段规格 |
|---|---|
| `REQ-REL-001` G03→G05 | typed error 分类是错误码命名空间（`ERR-*`，`ToolResult:361` 已有 pattern），G05 追加成员不破坏 G03 |
| `REQ-PERF-003` G03→G08 | 成本归因粒度是 span 属性的写入频率，不是结构 |
| `REQ-AGT-005` G03→G08 | "Verifier 不继承 Planner 结论"是调用图约束，G08 才有第二个 Agent |
| 四个消融 G04→G08 | 预注册规范是文档格式约定，见 [gates/G04.md](gates/G04.md) |
| `REQ-SEC-002` G04→G05→G07 | 注入防御是策略与测试套件，不是共享结构 |
| 四个机制 G05→G06 | 权限/幂等/审计/补偿在 G05 建成，G06 是重新验证而非扩展结构 |
| `REQ-SEC-003` G01→G06→G10 | sanitizer 的 denylist 是配置，扩展出口面不改结构 |

## 如何使用本文件

这五条规格应在 **G03 的 I-G03-01（Typed State 与 reducer）** 一次性落地，
因为它们全部是契约层字段，集中修改一次比分散到各 iteration 更省事，
且 `contracts/generated/contracts-v1.1.0.json` 只需重新编译一次。

**验收方式**：G04、G05、G06 开工时，若需要修改本文件规定的任何字段的
名称、类型或可选性，即视为 G03 未履行接口义务，应记入该 Gate 的 carry-in 债务。

这个验收方式本身是一条可讲述的工程实践：**接口契约在上游 Gate 冻结，
下游 Gate 的修改需求即是上游的缺陷**。它比"我们做了跨模块设计"具体得多。
