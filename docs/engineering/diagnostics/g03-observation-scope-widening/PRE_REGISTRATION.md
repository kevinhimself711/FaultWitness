# 观测面加宽：预登记

`diagnostic_only: true`。本目录产物**永不可升级为 readiness evidence**，不是 Gate attempt，
不登记 work item，不改 `PROJECT_STATE.yaml`，G03 保持 `not_started`。

**本文件在任何代码改动之前提交。** 顺序本身是证据：先登记预期与判据，再实测，
被否证就如实记录。按 `.claude/rules/experiments.md` 与
`docs/engineering/POSTMORTEM_MEASURE_BEFORE_FREEZE.md` 的"先量后冻"。

**重算不等于实测。** 下面所有"预期"都是预期，不是重算结果。实测覆盖预期时以实测为准，
并明确写出被否证。这句话写在这里，事后就不能重新解释。

前三轮我的预登记被否证了三次（U8 的"无捷径"、U10 的"D1 会低于 D2"、r8/r9 的"r9 更可能坏"），
所以这一条不是形式。

## 为什么做这件事

三个只读探针已把一件事测实：**当前任务表示是一张六选一查表**。零模型分类器 D1 = 0.9062，
模型臂根因准确率 0.9479，差距 3pp。D4 消融显示六条信号 6/6 单独就能识别自己那一族，召回全部 1.000。

读代码补上的那条事实解释了上面全部结果：**观测面与标签集是 1:1 构造的**。
`V3_TRACE_QUERY_SERVICES`（`g02_lab.py:60-67`）恰好是六个注入目标；三条标量通道在 packet builder
里各钉死一个服务（`cpu_window` → `ad`、`memory_window` → `email`、`queue_window` → `fraud-detection`）。
**每个答案有一条私有通道。**

"故障不跨服务传播"（共现矩阵非对角全 0）因此至少部分是**测量伪影而非 SUT 属性**——
这是推断，未测量。`product-catalog` 报错本该出现在 `frontend` 与 `recommendation` 的 trace 里，
而这两个服务从未被查询。**这条推断是本轮要消灭的第一个未知量**，它比"任务有多难"更靠前：
不知道级联是否存在，就无法解释任何 D1 的变化。

## 判据 E：级联存在性（独立判据，不并入 D1）

```
E. 注入 productCatalogFailure / paymentFailure / paymentUnreachable 时,
   frontend / recommendation / cart 的 trace_errors 是否出现非零?
   逐 case 报告,不聚合。
```

**预期 E**：注入 `productCatalogFailure` 时 `frontend`/`recommendation` 出现非零 trace error；
注入 `paymentFailure`/`paymentUnreachable` 时 `cart` 出现非零。猜 3 族里至少 2 族成立。

E 与 D1 是两个正交的问题，必须分开报。四种组合，报告必须明确落在其中一个上：

```
  E 有 + D1 掉  → 加宽有效,级联是真难度来源,继续
  E 有 + D1 高  → 级联存在但模式唯一(prod-catalog 一坏就是固定那组邻居),
                  仍是查表只是格子变大。需要多故障注入,不是死路
  E 无 + D1 掉  → 警报:D1 下降来自噪声而非难度。这是假阳性,
                  比 D1 不掉更危险,因为它会让你误以为成功
  E 无 + D1 高  → flagd 注入面不产生跨服务传播。这是 SUT 的性质,
                  换观测面救不了 → 换注入面(kubectl/NetworkPolicy/多 flag),
                  **不是项目终结**
```

**最后一行必须写进报告。** 闸门失败的出口是"换机制"，不是"停"——
一个只有 stop 没有 switch 的闸门，会让下一个 session 以为项目到头了。

## 判据 D：任务是否仍是查表

**预期 D1**：加宽观测面后 D1 明显下降（猜 **0.60–0.75**），因为每族不再独占通道。

**闸门（任一条成立就报告并停，不进入模型预算）**：

- 加宽后 D1 仍 **≥ 0.75**；或
- D4 里仍有**任何**单信号 recall = 1.000 且 precision = 1.000（该族仍可零推理识别）；或
- 单信号偏移比例仍 ≥ 0.75。

**反向风险**（必须同等记录）：若 D1 塌到接近多数类 0.25，说明加宽把信号也淹了，
那是**任务不可解**而非"有难度"，同样是失败，不是好消息。
靠"真族信号是否仍 32/32 合格"区分这两种情形。

**这条约束是整轮的要点**：重构后的任务如果只能证实、不能显示 harness 毫无增益，
那它就不是任务，是布景。这是唯一能防住"把任务调到让 harness 好看"的东西——
而那和把门槛冻在仪器故障读数上，是同一类错误。

## 已测得的可行性裁决（改代码之前就已知）

用项目自己的 `four_turn_input_upper_bound_v3`（`g03_readiness.py:1779`）在 `uv run` 下实测，
纯离线字符串计算，零模型调用。源：`.audit/g03-readiness/g03-4622470-r9/scenarios.json`。

| 量 | 值 |
| --- | --- |
| 最差现有 packet（`SEED-G02-0008`） | 9469 B（bound 57778，status pass） |
| 四轮上界固定开销（与 packet 无关） | 19902 |
| `FOUR_TURN_INPUT_LIMIT` | 58982 |
| **允许的最大 packet** | **9770 B** |
| **可用余量** | **301 B** |

固定开销 19902 的分解（逐项相加精确闭合）：

| 组成 | tokens | 占比 |
| --- | --- | --- |
| 假设性 assistant 草稿（`MAX_COMPLETION_TOKENS × prior_count`，`:1801`） | **12288** | **61.7%** |
| system prompt × 4 轮 | 4644 | 23.3% |
| message framing | 1280 | 6.4% |
| request template | 1024 | 5.1% |
| correction 指令文本 | 666 | 3.3% |

最差 packet 的逐组字节：`journey_window` 497、`trace_activity` 1809、`trace_errors` 4920、
`cpu_window` 572、`memory_window` 557、`queue_window` 907。

边际成本（每服务，含 7 窗 × 4 轮的 28 倍放大）：

| 通道 | 边际成本 |
| --- | --- |
| `trace_activity` | **+226 B / 服务** |
| `trace_errors` | **+534 B / 服务**（下界：原型 cell 的 `descriptions` 为空） |

**加 `frontend`/`recommendation`/`cart` 三个服务 = +2282 B，对 301 B 余量超 7.6 倍。**
**连"只扩 trace 服务集"的最小版本也塞不下**；甚至只加一个服务（760 B）也塞不下。

### 但这不阻塞本轮 —— 已核实的执行路径

`run_retest_baselines_v3` 的写入顺序：

- `scenarios.json` 写于 **`:3225`**
- `deterministic.json` 写于 **`:3279`**
- `token_preflight_v3` 才跑于 **`:3283`**
- `four_turn_token_headroom` 装配于 `:3141-3142`，`GovernanceError` 抛于 **`:3354`**

**即 token 不可行的 packet 仍会把数据集与 deterministic 矩阵完整写盘**，然后命令非零退出。
两个探针只读 `scenarios.json`，且都不引用任何 `four_turn` / `token_preflight`（已 grep 确认）。

**结论：token 天花板阻塞的是 live 路径，不是零模型闸门。**
所以本轮照常加宽、照常取数，并如实记录 preflight 为 `blocked: four_turn_token_headroom`、
命令非零退出——**这是预期结果，不是待修的故障**。

**不抬预算数值、不删任何 measured value。** 见 `docs/adr/ADR-0019.md`：
预算的数值冻结已撤销（数值待定、形式不变、不动代码），而 `AMD-0007:168` 自己的例外条款
已允许去掉四轮重复的 packet 表示——但那件事的正确时机是工具化改造，不是本轮，
因为本轮只改观测面一个变量。

另核实：`presence_only_probe_v3`（`:795-827`）按**组签名**计数、不按服务数，
`expected_top1_count: 8` / `maximum_top3_count: 20` 与 trace 服务集无关，
加宽不会触发 `leak_not_eliminated`。

## 新增服务集

`frontend`、`recommendation`、`cart`，6 → 9。

选择判据：**必须包含注入目标的上游调用方**，这才是级联的检验。
`frontend` 与 `recommendation` 是 `product-catalog` 的调用方，`cart` 是 `checkout` 的相邻方——
这三个是最小充分集。不扩到全部 19 个：判据 E 只需要上游，多余服务只添噪声。

## 两条用户已定的边界

1. **`descriptions` 本轮保持原样，不做任何改动。** 加宽后单独跑一次泄漏探针，报两件事：
   (a) 加宽后的 `descriptions` 泄漏率（新增服务会带自己的 `descriptions`，现在的 16/32 届时会变）；
   (b) 脱敏 `descriptions` 对加宽后 D1 的影响——用探针现成的分类器 A/D1 直接测，**不真的改数据**。
2. **零模型闸门先于任何模型预算。** 加宽后先跑 preflight + 两个探针，报数，停。

## 阶段划分

- **3a**：只扩 trace 服务集（`trace_errors`/`trace_activity` 已是 per-service，无需改 packet 形状）
  → 跑一轮 → 答判据 E。
- **3b**：**仅当 E 为真**，再做标量 per-service 化去打破独占通道。
  **如果 E 为假，3b 白做**——那时的出口是换注入面。

## 本轮不改

`ROOT_CAUSE_LABELS`、`TARGET_SERVICES`（族→服务映射）、arms registry、任何门槛数值、
`+0.10` 的五处代码残留、`PROJECT_STATE.yaml`、`.audit/` 下既有目录、`docs/audit/**`、
`descriptions` 的处理逻辑、`AMD-0007.md`（hashed input #7）。
## 预登记之后的补充（2026-09-11，实现判据 E 探针时发现）

**这一节写在预登记提交之后，所以标明为补充，不冒充预登记内容。** 它不改判据 E 的问题，
也不改上面四种组合中的任何一格，只补上一个原本会把 E 读错的测量语义。

写探针时核实了采集端的行为：**Jaeger 对从未见过的服务返回空 trace 列表，采集端记成 `0`**
（`g02_lab.py` 的 Jaeger 循环：`trace_activity[svc] = len(traces)`，随后 error 计数从同一批
traces 累加）。Prometheus 不是这样——缺 series 记 `null` 并归类为 infrastructure。
于是 `trace_errors` 里有三种不同的零，写出来一模一样：

| 读数 | 含义 |
| --- | --- |
| 有 trace、无 error | **测到了**"没有传播" |
| 一条 trace 都没有 | **没测到**，不是没传播 |
| healthy 期也报同样多的错 | 噪声，不是传播 |

第二种正是 **1:1 观测面那个问题在加宽之后原样存活**：把它读成"级联不存在"，
就是在新地方犯同一个错。所以探针增加第五种读数 `cascade_unobservable`——
当且仅当全部候选 case 的上游服务在 fault 期都没有 trace 时报出，
**它不等于 `cascade_absent`，也不落在上面四格中的任何一格**，
对应的下一步是查采集面而不是查 SUT 性质。

第三种是 `excess_over_healthy` 存在的理由：按"fault 期非零"判定会把一个 baseline 就有噪声的
服务在该族每个 case 上都算成级联。

预登记里判据 E 的原话是"是否出现非零"。**实测按 `excess_over_healthy > 0` 判定，比原话严格**，
差别在此明写，事后不重新解释。

### 再补一条（2026-09-11，r3 采集期间实测）：healthy 期的零是"该窗没流量"，不是"服务未知"

跑 r3 时看到 r2 那个 case 的 healthy 窗里只有 `frontend` 有 trace（3→6），
六个原服务全为 `0`，一度像是"新服务可观测、老服务不可观测"。
**回查加宽之前的 r9 数据集否证了这条读法**：r9 的 healthy 窗（index 0–4）
`ad`/`checkout`/`email`/`fraud-detection`/`payment`/`product-catalog` **同样全为 0**，
trace 只在 fault 窗（index 5–6）出现（`checkout: 5`、`payment: 4`…）。

原因在采集端而非观测面：workload 只在 fault 轮询时被驱动
（`restimulate_each_poll`），healthy 窗的 Jaeger 回看窗口里本来就没有请求。
**所以 healthy 期的零对判据 E 无信息量，唯一有信息量的是 fault 期的零。**

探针的 `observed_under_fault` 恰好只读 fault 窗的 `trace_count` 最大值
（`g03_cascade.py:181-182`），healthy 期的零不会污染它。这一条是核实而非改动：
未改任何代码。

`frontend` 在 healthy 期有 trace，是因为它承接 load generator 的常驻首页流量；
这也说明加宽引入的三个服务里至少 `frontend` 在 Jaeger 里确实存在，
`cascade_unobservable` 若发生不会是"服务名根本没注册"这种平凡原因。
