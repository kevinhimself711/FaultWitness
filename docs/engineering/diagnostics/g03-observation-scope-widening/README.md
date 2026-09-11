# 观测面加宽：目录说明

`diagnostic_only: true`。本目录所有产物**永不可升级为 readiness evidence**，不是 Gate attempt，
不登记 work item，不改 `PROJECT_STATE.yaml`，G03 保持 `not_started`。

## 这个目录在回答什么

前三轮的只读探针（U8 泄漏、U9 r8/r9 差异、U10 分化度）把一件事测实了：**当前任务表示是一张
六选一查表**。零模型分类器 D1 = 0.9062，模型臂根因准确率 0.9479，差距 3pp；D4 消融显示六条信号
6/6 单独就能识别自己那一族，召回全部 1.000。

读代码补上的那条事实解释了上面全部结果：**观测面与标签集是 1:1 构造的**。
`V3_TRACE_QUERY_SERVICES` 恰好是六个注入目标，三条标量通道各钉死一个服务。**每个答案有一条
私有通道**，所以 D1 高不是"抽到了简单 case"，是仪器被这样构造出来的。

由此产生一个必须先消灭的未知量。共现矩阵非对角全 0 被读成"故障不跨服务传播"，但这条读法有两个
互不相容的解释：

1. 故障确实不跨服务传播（SUT 的性质）；
2. 注入服务的下游从未被查询过——观测面与标签集 1:1，**传播在构造上不可观测**。

两者对"加宽观测面能不能增加难度"给出相反的答案，而现有任何产物都分不开它们。
**判据 E 就是为了分开这两条。** 它必须先于"任务有多难"回答：不知道级联是否存在，
就无法解释任何 D1 的变化。

## 文件

| 文件 | 是什么 |
| --- | --- |
| `PRE_REGISTRATION.md` | **改代码之前提交的预登记**。判据 E 与四组合解释表、D 的三条闸门、预期 D1 区间、反向风险、以及改代码之前就实测出的 token 可行性裁决表。顺序本身是证据。 |
| `cascade-wide.json` | 判据 E 的产物：逐 case 表，不聚合。由 `uv run python -m faultwitness_dev g03-cascade` 产出。 |
| `separability-wide.json` | 加宽后的 D1–D4。由 `g03-separability` 产出。 |
| `leakage-wide.json` | 加宽后的 `descriptions` 泄漏率。由 `g03-leakage-probe` 产出。 |

## 怎么读判据 E 的产物

**逐 case 读，不要只读 rate。** 一个族级比率会正好盖住最该看见的东西：传播发生时是不是每次都落在
同一组邻居上。落在同一组 = 查表的格子变大了，仍然是查表；每次不同 = 存在真正需要分辨的取证工作。
所以 `families[*].distinct_propagation_patterns` 与 `propagation_pattern_is_unique` 比
`cascade_observed_rate` 更重要。

**三个必须区分的零**，这是本探针存在的全部理由：

| 读数 | 含义 | 产物里的位置 |
| --- | --- | --- |
| 服务在 fault 期有 trace、但无 error | **测到了**"没有传播" | `observed_under_fault: true` + `excess_over_healthy: 0` |
| 服务在 fault 期一条 trace 都没有 | **没测到**，不是没传播 | `observed_under_fault: false`，汇总进 `candidate_cases_with_no_upstream_traces` |
| 服务 healthy 期也报同样多的错 | 噪声，不是传播 | `nonzero_in_healthy: true` + `excess_over_healthy: 0` |

第二行是关键：Jaeger 对从未见过的服务返回空 trace 列表，采集端记成 `0`，**和"有流量但没出错"
写出来一模一样**（Prometheus 不同，缺 series 记 `null` 并归类为 infrastructure）。所以若全部候选
case 的上游都没有 trace，`e_verdict` 是 `cascade_unobservable` 而**不是** `cascade_absent`——
那是 1:1 观测面的问题在加宽之后原样存活，把它读成"级联不存在"就是在新地方犯同一个错。

第三行是 `excess_over_healthy` 存在的理由：按 `nonzero_in_fault` 判定会把一个 baseline 就有噪声的
服务在该族每个 case 上都算成级联。

## E 与 D1 是两个正交的问题

**不要合并成一个结论。** 报告必须明确落在四格中的一格；每格的下一步机制写在产物的
`interpretation` 字段里，不只写在预登记里，因为**后来的读者打开的是产物**：

```
  E 有 + D1 掉  → 加宽有效，级联是真难度来源，继续 3b
  E 有 + D1 高  → 级联存在但模式唯一，仍是查表只是格子变大。
                  下一步机制是多故障注入，不是死路
  E 无 + D1 掉  → 警报：D1 下降来自噪声而非难度。这是假阳性，
                  比 D1 不掉更危险，因为它看起来像成功
  E 无 + D1 高  → flagd 注入面不产生跨服务传播。这是 SUT 的性质，
                  换观测面救不了 → 换注入面（kubectl / NetworkPolicy / 多 flag 同时开），
                  不是项目终结
```

最后一行是刻意保留的：**闸门失败的出口是"换机制"，不是"停"。** 一个只有 stop 没有 switch 的闸门，
会让下一个 session 以为项目到头了。

## 已知的、预期的失败

**preflight 必然 `blocked: four_turn_token_headroom`，命令非零退出。这是预期结果，不是待修的故障。**

四轮各带一份完整 packet，每 packet 7 个窗口，所以每服务每窗的字节要乘 28；加三个服务 = +2282 B，
而余量只有 301 B（详数见 `PRE_REGISTRATION.md` 的裁决表）。但 `run_retest_baselines_v3` 的写入顺序
是 `scenarios.json` → `deterministic.json` → 才跑 `token_preflight_v3`，**所以数据集与 deterministic
矩阵已完整落盘**，三个探针只读 `scenarios.json` 且不引用任何 token 逻辑。

**token 天花板阻塞的是 live 路径，不是零模型闸门。** 不要为了让命令零退出去抬预算数值或删字段
（`AMD-0007:57`）。数值冻结的撤销见 `docs/adr/ADR-0019.md`；去重四轮重复表示已被
`AMD-0007:168` 的例外条款允许，但正确时机是工具化改造那一轮，不是本轮——本轮只改观测面一个变量。

## 顺序

1. `docs/adr/ADR-0019.md`（撤销 token 预算的数值冻结，只改文档）
2. `PRE_REGISTRATION.md`（**先于任何代码改动**）
3. 3a：`V3_TRACE_QUERY_SERVICES` 6 → 9，加 `frontend` / `recommendation` / `cart`
4. 跑 preflight + 三个探针，报数
5. 3b（标量 per-service 化）**仅当 E 为真**；E 为假则 3b 白做，出口是换注入面
