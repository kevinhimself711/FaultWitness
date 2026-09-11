# 加宽观测面：实测结果（r4，零模型，diagnostic_only）

源运行 `g03-wide-r4`，32/32 case 全 `pass`，`dataset_digest 728a8ae405ee`，
三份产物均 `model_calls: 0`、`diagnostic_only: true`、重跑逐字节可复现（忽略 `generated_at`）。
观测面 6 → 9，新增 `cart` / `frontend` / `recommendation`。

**落在四组合的哪一格：`E 有 + D1 高`。** 但比预登记设想的更极端——D1 不是"仍然高"，
而是**从 0.9062 涨到 1.0000**。加宽让任务变得更容易，方向与预期相反。

## 判据 E：级联存在（`cascade_present`）

`candidate_cases_answerable: 16/16`，`candidate_cases_with_no_upstream_traces: []`
——**没有落进 `cascade_unobservable`**，这个零是测到的，不是没测到的。

| 族 | n | 观测到级联 | 传播模式数 | 模式 |
| --- | --- | --- | --- | --- |
| `paymentFailure` | 4 | 4 | 1 | `frontend` ×4 |
| `paymentUnreachable` | 4 | 4 | 1 | `frontend` ×4 |
| `productCatalogFailure` | 8 | 7 | 1 | `frontend` ×7，1 例无 |

**预期 E 被部分否证。** 预登记猜 `frontend`/`recommendation` 在 product-catalog 故障时报错、
`cart` 在 payment 故障时报错。实测**只有 `frontend` 承载传播**：

- `recommendation`：16 个候选 case 全部 `observed_under_fault: false`，fault 期零 trace。
  它根本没有流量，**不是"有流量但没报错"**。
- `cart`：payment 族有 trace（4–6 条）但 `error_count` 恒为 0，
  即**测到了"没有传播"**——真正的负读数。

三种零在同一张表里各出现了一次，这正是探针存在的理由：
`recommendation` 是"没测到"，`cart` 是"测到没传播"，`frontend` 是真传播（excess 4–8）。

**模式唯一（`propagation_is_deterministic: true`）**：三个族各只有一种传播模式，
且三者都是同一个 `frontend`。所以级联没有增加任何需要分辨的取证工作——
它只是给每个答案多加了一个恒定的伴随信号。

## 判据 D：三条闸门全部成立，且都在最坏值

| 闸门 | 阈值 | 加宽前 | 加宽后 | 结果 |
| --- | --- | --- | --- | --- |
| D1 ≥ 0.75 | 0.75 | 0.9062 | **1.0000** | 成立（更差） |
| 任何单信号 recall=1.000 且 precision=1.000 | 任一条 | 5/6 | **6/6** | 成立（更差） |
| 单信号偏移比例 ≥ 0.75 | 0.75 | 0.75 | **1.0000** | 成立（更差） |

D4 消融：**六条信号全部 recall=1.000、precision=1.000、外族误报 0**。
加宽前 `adHighCpu` 还会在 8 个外族 case 上误报（precision 0.333），
现在连这一点噪声都没有了。`single_offset_fraction: 1.0000` 意味着
**32 个 case 每一个都恰好只有一条信号越阈**（`{1: 32}`）。

per-family accuracy spread 从 0.25 降到 **0.0**：六个族全部 100%。
加宽前有四个族满分，现在是六个。

**反向风险未发生**：D1 没有塌向多数类 0.25，真族信号全部合格。
不是"信号被淹了"，是**信号更干净了**。

## 为什么加宽把任务变简单了

这是本轮最重要的一条，且是实测而非推断：加宽**没有**打破"每个答案一条私有通道"，
它给三个 `trace_errors` 族**各加了一条第二私有通道**（`frontend` 的 error_count），
同时把 `adHighCpu` 原有的假阳性挤掉了。查表的格子变大，格子之间反而更不重叠。

D2（bare quantum）从 0.5938 涨到 0.7500 也指向同一件事。

## 用户指定的两个数

**(a) 加宽后 `descriptions` 泄漏率。** 携带非空 `incident_tokens` 的 case
从 16/32 降到 **14/32**；classifier A 多数投票 0.5000 → **0.4375**（弃权 16 → 18），
最近邻 0.7500 → **0.6875**。裁决码不变（`localized_leakage_trace_errors_families`），
但三族内部准确率从 1.0000 降到 **0.8750**。

**泄漏率下降不是好消息**：它下降的原因是新增服务的 `descriptions` 稀释了判别 token，
而不是文本变得不可用。三族仍显著泄漏，脱敏该三族仍然必要。

**(b) 脱敏 `descriptions` 对 D1 的影响：结构上为零，不需要测。**
D1–D4 只读六条 `ROOT_SIGNAL_FEATURES` 数值通道，不读任何文本
（`g03_separability.py` 模块文档与 `_assert_no_forbidden_input` 双重保证）。
**所以 D1 = 1.0000 本身就已经是脱敏后的数字。** 脱敏只动 classifier A。

这把用户的问题回答得比问法更彻底：脱敏 `descriptions` 之后任务不是变难，
而是**完全不变**，因为数值通道单独就已经 100% 可解。

## preflight 的 token 状态

`status: blocked`，`blockers: ["four_turn_token_headroom"]`，命令退出码 1。
`max: 66254` 对 `maximum_allowed: 58982`，`headroom_at_max: -718`。
预登记按最差 packet 估的是 +2282 B 超标；实测超 7272 B，**比预估更差**
（预估用的是空 `descriptions` 的下界原型 cell）。

**这只阻塞 live 路径，不影响以上任何结论**：`scenarios.json` 与 `deterministic.json`
在 token 检查之前已完整落盘，三个探针只读前者且不引用任何 token 逻辑。
未为让命令零退出而抬预算或删字段。

## 结论与出口（不给二元判定）

判据 D 三条全部成立 ⇒ **按预登记，报告并停，不进入模型预算。**

但 E 为真改变了下一步的性质。落在 `E 有 + D1 高` 格，产物 `interpretation` 字段的
登记出口是：

> propagation exists but its pattern is unique per family, so the task is still a
> lookup table with larger cells; the next mechanism is multi-fault injection,
> not a dead end

**3b（标量 per-service 化）现在明确不该做。** 计划写的是"仅当 E 为真才做 3b"，
E 确实为真——但 3b 的目的是打破独占通道，而本轮实测显示加宽观测面
**只会增加私有通道**。同一个机制再走一步没有理由期待相反的结果。

真正被本轮数据支持的下一步是**改注入面而不是观测面**：

1. **多故障同时注入**（多个 flag 同时开）。这是唯一能让"每个 case 恰好一条信号越阈"
   这个事实失效的机制——它直接攻击 `single_offset_fraction: 1.0`。
2. 如果多故障仍然可加性分解，才需要考虑换注入机制（kubectl / NetworkPolicy），
   让故障不再对应单一 flag。

`recommendation` 全程零 trace 也给出一条独立的可执行信息：
**当前 workload 不覆盖它**。任何依赖"下游服务有流量"的后续设计都要先解决这个，
否则会得到又一批"没测到"被误读成"没发生"。
