# metric-v3 根信号分化度检查：诊断记录

`diagnostic_only: true`。本目录产物**永不可升级为 readiness evidence**，不是 Gate attempt，
不登记 work item，不改 `PROJECT_STATE.yaml`，G03 保持 `not_started`。本轮**只测量，不修复**：
没有改数据集、没有改 `descriptions`、没有改任何阈值、没有改 `g03_readiness.py` 任何现有函数的行为
（只 import），没有调用任何模型（`model_calls: 0`）。

产物：`g03-metric-v3-root-signal-separability.json`
源运行：`.audit/g03-readiness/g03-4622470-r9/scenarios.json`
（`source_run: g03-4622470-r9`，`source_run_invalidated: false`，
`dataset_digest: 8f5a628ab1eb5e87fd5846194b8d679279e1b9a999ed3905e073eed606617b45`，
与 r8/r9 取证记录中逐字节相同的那份数据集是同一份）

## 要回答的问题

**如果把 `descriptions` 脱敏掉，这个任务还剩多少难度？**

上一轮泄漏探针已证实 `trace_errors.descriptions` 在 16/32 个 case 上明文点名故障族。
但那一轮的分类器 B 用的是**裸的逐族 quantum**而不是冻结的 leave-one-case-out healthy p99，
`adHighCpu` 的 quantum `1e-6` 低于环境漂移，在 25/32 个 case 上都满足（21 次误合格）。
B 自身的阈值测试 32/32 全中，因此有两种互斥读法：

- (i) 六条信号本来就正交，任务是六选一查表；
- (ii) 误合格互相抵消，凑出了一个巧合的满分。

两种读法指向**相反**的路线决定，现有数据无法区分。本轮就是为了区分它们。

## 一句话结论

**是 (i)。** 六条声明的数值信号各自单独就能把自己那一族完整召回（6/6，recall 全部 1.000），
冻结 p99 阈值下 24/32 个 case 只有一条信号偏移且那条就是真族，
零模型分类器 D1 达到 accuracy 0.9062 / macro-F1 0.9069。
**脱敏 `descriptions` 不足以给任务留下取证难度**：数值通道本身就是一张查表。

同时，(ii) 被**证伪**：清干净阈值以后判别力**上升**了（D1 0.9062 > D2 0.5938），
不是下降。我进入本轮时预登记的预期是「D1 会低于 D2，说明此前的 32/32 是阈值污染」——
**该预期被否证，如实记录。**

## 判据与实测（按注册顺序，非二元结论）

| 注册读法 | 判据 | 实测 | 是否成立 |
| --- | --- | --- | --- |
| `six_way_lookup_table` | D1 高分 + D4 每条信号单独识别自己那一族 + 绝大多数 case 只有一条信号偏移 | 0.9062 / 6-of-6 / 0.7500 | **成立** |
| `prior_32_of_32_was_threshold_contamination` | D1 明显低于 D2 | D1 − D2 = **+0.3125**（方向相反） | 不成立 |
| `room_for_investigation` | D1 明显低于满分且失败分散在多族 | 3 个错全部落在同一机制上 | 不成立 |
| `difficulty_fracture` | 逐族准确率跨度大 / 存在 0.0 族 | 跨度 0.2500，无 0.0 族 | 不成立 |

`six_way_lookup_table` 的三项里，单信号偏移比例 **0.7500 恰好压在注册下界
`SINGLE_SIGNAL_LOOKUP_FRACTION = 0.75` 上**，不是宽松通过。按「宁可报告任务过易」的取向，
边界情形归到「可能过易」一侧；下面 c 表给出全部计数，供人自行改判。

## a. 32 × 6 偏移量表（本表只列真族那一列；完整 6 列在产物里）

产物中的完整表在 `offset_table.<case_id>.signals.<label>`，每个 cell 都带
`healthy_median` / `fault_max` / `incident_excess` / `healthy_p99` / `quantum` /
`p99_threshold` / `quantum_threshold` / `qualifies_p99` / `qualifies_quantum` /
`standardized_excess_p99` / `standardized_excess_quantum` / `is_true_family`，
可以逐行手工复算。`nsig` 是该 case 在 p99 规则下合格的信号条数。

| case | 真族 | healthy median | fault max | incident excess | p99 阈值 | excess / 阈值 | 合格 | nsig |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SEED-G02-0001 | kafkaQueueProblems | 0 | 86 | 86 | 0.001 | ×86000.00 | 是 | 2 |
| SEED-G02-0002 | paymentUnreachable | 0 | 2 | 2 | 1 | ×2.00 | 是 | 1 |
| SEED-G02-0003 | adHighCpu | 0.000334204 | 4.00058 | 4.00025 | 0.000128275 | ×31184.87 | 是 | 1 |
| SEED-G02-0004 | productCatalogFailure | 0 | 1 | 1 | 1 | ×1.00 | 是 | 1 |
| SEED-G02-0005 | paymentFailure | 0 | 2 | 2 | 1 | ×2.00 | 是 | 1 |
| SEED-G02-0006 | paymentUnreachable | 0 | 4 | 4 | 1 | ×4.00 | 是 | 1 |
| SEED-G02-0007 | paymentFailure | 0 | 2 | 2 | 1 | ×2.00 | 是 | 2 |
| SEED-G02-0008 | emailMemoryLeak | 4.62316e+07 | 5.10362e+07 | 4.80461e+06 | 2.31158e+06 | ×2.08 | 是 | 1 |
| SEED-G02-0009 | productCatalogFailure | 0 | 1 | 1 | 1 | ×1.00 | 是 | 2 |
| SEED-G02-0010 | kafkaQueueProblems | 0 | 82 | 82 | 0.001 | ×82000.00 | 是 | 1 |
| SEED-G02-0011 | adHighCpu | 0.0006043 | 4.00069 | 4.00008 | 0.000128275 | ×31183.60 | 是 | 1 |
| SEED-G02-0012 | emailMemoryLeak | 4.44457e+07 | 4.9238e+07 | 4.79232e+06 | 2.22228e+06 | ×2.16 | 是 | 2 |
| SEED-G02-0013 | kafkaQueueProblems | 0 | 90 | 90 | 0.001 | ×90000.00 | 是 | 1 |
| SEED-G02-0014 | adHighCpu | 0.000384641 | 4.00112 | 4.00073 | 1e-06 | ×4000730.74 | 是 | 1 |
| SEED-G02-0015 | adHighCpu | 0.000676844 | 4.00066 | 3.99999 | 0.000128275 | ×31182.83 | 是 | 1 |
| SEED-G02-0016 | productCatalogFailure | 0 | 2 | 2 | 1 | ×2.00 | 是 | 1 |
| SEED-G02-0017 | kafkaQueueProblems | 0 | 57 | 57 | 0.001 | ×57000.00 | 是 | 1 |
| SEED-G02-0018 | productCatalogFailure | 0 | 1 | 1 | 1 | ×1.00 | 是 | 1 |
| SEED-G02-0019 | emailMemoryLeak | 4.44539e+07 | 4.92872e+07 | 4.83328e+06 | 2.22269e+06 | ×2.17 | 是 | 1 |
| SEED-G02-0020 | kafkaQueueProblems | 0 | 85 | 85 | 0.001 | ×85000.00 | 是 | 1 |
| SEED-G02-0021 | emailMemoryLeak | 5.55418e+06 | 4.92913e+07 | 4.37371e+07 | 277709 | ×157.49 | 是 | 2 |
| SEED-G02-0022 | productCatalogFailure | 0 | 1 | 1 | 1 | ×1.00 | 是 | 1 |
| SEED-G02-0023 | productCatalogFailure | 0 | 3 | 3 | 1 | ×3.00 | 是 | 1 |
| SEED-G02-0024 | productCatalogFailure | 0 | 1 | 1 | 1 | ×1.00 | 是 | 1 |
| SEED-G02-0025 | paymentUnreachable | 0 | 4 | 4 | 1 | ×4.00 | 是 | 1 |
| SEED-G02-0026 | paymentFailure | 0 | 2 | 2 | 1 | ×2.00 | 是 | 2 |
| SEED-G02-0027 | paymentUnreachable | 0 | 4 | 4 | 1 | ×4.00 | 是 | 1 |
| SEED-G02-0028 | kafkaQueueProblems | 0 | 49 | 49 | 0.001 | ×49000.00 | 是 | 1 |
| SEED-G02-0029 | kafkaQueueProblems | 0 | 83 | 83 | 0.001 | ×83000.00 | 是 | 2 |
| SEED-G02-0030 | productCatalogFailure | 0 | 2 | 2 | 1 | ×2.00 | 是 | 2 |
| SEED-G02-0031 | kafkaQueueProblems | 0 | 41 | 41 | 0.001 | ×41000.00 | 是 | 1 |
| SEED-G02-0032 | paymentFailure | 0 | 2 | 2 | 1 | ×2.00 | 是 | 1 |

逐族汇总：

| 族 | n | healthy median 区间 | incident excess 区间 | p99 阈值区间 | excess/阈值 区间 | 真族合格 |
| --- | --- | --- | --- | --- | --- | --- |
| adHighCpu | 4 | 0.000334–0.000677 | 3.99999–4.00073 | 1e-06–0.000128 | ×31183–×4000731 | 4/4 |
| emailMemoryLeak | 4 | 5.55e+06–4.62e+07 | 4.79e+06–4.37e+07 | 2.78e+05–2.31e+06 | ×2.08–×157.49 | 4/4 |
| kafkaQueueProblems | 8 | 0 | 41–90 | 0.001 | ×41000–×90000 | 8/8 |
| paymentFailure | 4 | 0 | 2 | 1 | ×2.00 | 4/4 |
| paymentUnreachable | 4 | 0 | 2–4 | 1 | ×2.00–×4.00 | 4/4 |
| productCatalogFailure | 8 | 0 | 1–3 | 1 | ×1.00–×3.00 | 8/8 |

**表里最显眼的两件事：**

1. **真族信号 32/32 全部合格，一个不漏。** 没有任何 case 需要在「信号没动」的情况下推断根因。
2. **四个族的 healthy median 恰好是 0**（`productCatalogFailure` / `paymentFailure` /
   `paymentUnreachable` / `kafkaQueueProblems`）。也就是说健康期该计数器**完全静默**，
   故障期只要出现任何一个错误（excess = 1，`productCatalogFailure` 有 3 个 case 就落在
   ×1.00 的最小合格边界上）就合格。这不是「从噪声里分辨信号」，是「从零变成非零」。
   `kafkaQueueProblems` 更极端：0 → 41~90 秒 lag，是阈值的四万到九万倍。

## b. 误合格率：冻结 p99 对比裸 quantum

每条信号在**不属于它的**那些 case 上误合格多少次。裸 quantum 仍然计算并并列报告，但
**不再作为主判据**。

| 信号 | 真族 support | 外族 case 数 | p99 误合格 | 裸 quantum 误合格 | p99 消除的误合格 |
| --- | --- | --- | --- | --- | --- |
| adHighCpu | 4 | 28 | **8** | **21** | 13 |
| emailMemoryLeak | 4 | 28 | 0 | 0 | 0 |
| kafkaQueueProblems | 8 | 24 | 0 | 0 | 0 |
| paymentFailure | 4 | 28 | 0 | 0 | 0 |
| paymentUnreachable | 4 | 28 | 0 | 0 | 0 |
| productCatalogFailure | 8 | 24 | 0 | 0 | 0 |

**CPU 是唯一不干净的通道，其余五条在两种规则下都是零误合格。**
这解释了上一轮 B 的行为，也解释了为什么换成冻结 p99 会让分数**上升**而不是下降：
p99 只是把 CPU 通道的噪声压下去 13 次，没有削弱任何真信号。

CPU 通道为什么脆：128 个健康漂移样本里**只有 8 个非零**，其中最大的两个来自
`SEED-G02-0014`（0.000690）与 `SEED-G02-0021`（0.000127），其余 6 个都是 `1.08e-19` 量级的浮点残渣。
p99 是 nearest-rank，124 个样本取第 123 位，于是**整条 CPU 阈值实际上由那一个非零样本决定**：
留出 0014 或 0021 时阈值塌回 `1.08e-19`（threshold ≈ quantum `1e-6`），
留出其他任何 case 时阈值是 `0.000127`。这是本次测量里唯一一处阈值对单个样本敏感的地方，
记录在此以便人判断是否要单独处理，本轮不改。

## c. 正交性：一个 case 同时有几条信号偏移

| 规则 | 平均偏移信号数/case | 分布 | 单信号 case | 单信号比例 | 单信号且就是真族 |
| --- | --- | --- | --- | --- | --- |
| 冻结 p99 | **1.2500** | {1 条: 24, 2 条: 8} | 24/32 | **0.7500** | 24（100%） |
| 裸 quantum | 1.6562 | {1 条: 11, 2 条: 21} | 11/32 | 0.3438 | 11（100%） |

p99 规则下的共现矩阵（对角线是该信号总合格次数）：

| | adHighCpu | emailMem | kafkaQueue | payFail | payUnreach | prodCatalog |
| --- | --- | --- | --- | --- | --- | --- |
| **adHighCpu** | **12** | 2 | 2 | 2 | 0 | 2 |
| **emailMemoryLeak** | 2 | **4** | 0 | 0 | 0 | 0 |
| **kafkaQueueProblems** | 2 | 0 | **8** | 0 | 0 | 0 |
| **paymentFailure** | 2 | 0 | 0 | **4** | 0 | 0 |
| **paymentUnreachable** | 0 | 0 | 0 | 0 | **4** | 0 |
| **productCatalogFailure** | 2 | 0 | 0 | 0 | 0 | **8** |

**除 `adHighCpu` 那一行/一列外，所有非对角元素都是 0。** 也就是说六条信号之间
**不存在任何真实的级联或共现**——8 个「两条信号偏移」的 case 全部是 CPU 通道误合格造成的，
不是故障本身牵动了第二个信号。若把 CPU 的 8 次误合格剔掉，单信号比例就是 32/32 = 1.0000。
这是判断「任务是查表」最直接的证据：**故障不传播。**

## d. 逐族准确率与分化度断裂检查

| 族 | support | D1 正确 | D1 准确率 | 备注 |
| --- | --- | --- | --- | --- |
| adHighCpu | 4 | 4 | **1.0000** | 免费分 |
| kafkaQueueProblems | 8 | 8 | **1.0000** | 免费分 |
| paymentFailure | 4 | 4 | **1.0000** | 免费分 |
| paymentUnreachable | 4 | 4 | **1.0000** | 免费分 |
| emailMemoryLeak | 4 | 3 | 0.7500 | 1 个被 CPU 抢走 |
| productCatalogFailure | 8 | 6 | 0.7500 | 2 个被 CPU 抢走 |

跨度 0.2500（最好 1.0000，最差 0.7500），**`fractured: false`，无 0.0 族**。

按泄漏探针那条三族/三族分界线再切一次（`grouped_accuracy`）：

| 分组 | 族 | support | D1 | D2 | D3 |
| --- | --- | --- | --- | --- | --- |
| `trace_errors` 三族 | productCatalogFailure / paymentFailure / paymentUnreachable | 16 | **0.8750** | 0.2500 | 0.0000 |
| 其余三族 | adHighCpu / emailMemoryLeak / kafkaQueueProblems | 16 | **0.9375** | 0.9375 | 0.5000 |

**这是本轮最直接回答原始问题的一行**：那 16 个被 `descriptions` 明文泄漏的 case，
在完全不读 `descriptions`、只看数值的情况下仍然拿到 0.8750。
即泄漏是**冗余**的捷径，不是唯一的捷径；去掉它，数值通道自己就够。
（D2 在这一组只有 0.2500，正是 CPU 污染的落点——见 e 表。）

难度没有断裂，但原因是「六族普遍偏易」，不是「六族难度均衡且适中」——
四个族是免费分，另两个族的失分**全部**来自同一个 CPU 误合格机制。

D1 的 3 个错**全部**预测成 `adHighCpu`，零弃答：

| case | 真族 | 预测 | 真族 standardized excess | adHighCpu standardized excess |
| --- | --- | --- | --- | --- |
| SEED-G02-0009 | productCatalogFailure | adHighCpu | 0 | **5.587** |
| SEED-G02-0012 | emailMemoryLeak | adHighCpu | 1.156 | **3.679** |
| SEED-G02-0030 | productCatalogFailure | adHighCpu | 1 | **1.610** |

三个错是同一个机制：CPU 的标准化超出量把真族排到了第二位。
**这不是「任务有难度」的证据，是「CPU 阈值太松」的证据**——如果这三例修好，D1 就是 32/32。
按「宁可报告任务过易」的取向，我把 D1 的 0.9062 读作**下界**，而不是任务留有 9% 难度。

## e. D1 与 D2 的逐族差值（冻结 p99 − 裸 quantum）

| 族 | support | D1 正确 | D1 准确率 | D2 正确 | D2 准确率 | 差值 |
| --- | --- | --- | --- | --- | --- | --- |
| paymentFailure | 4 | 4 | 1.0000 | 0 | 0.0000 | **+1.0000** |
| paymentUnreachable | 4 | 4 | 1.0000 | 1 | 0.2500 | **+0.7500** |
| productCatalogFailure | 8 | 6 | 0.7500 | 3 | 0.3750 | **+0.3750** |
| adHighCpu | 4 | 4 | 1.0000 | 4 | 1.0000 | +0.0000 |
| emailMemoryLeak | 4 | 3 | 0.7500 | 3 | 0.7500 | +0.0000 |
| kafkaQueueProblems | 8 | 8 | 1.0000 | 8 | 1.0000 | +0.0000 |

总体：accuracy **+0.3125**（0.9062 − 0.5938），macro-F1 **+0.3763**（0.9069 − 0.5306）。

D2 的 13 个错**全部**预测成 `adHighCpu`（真族分布：productCatalogFailure 5、paymentFailure 4、
paymentUnreachable 3、emailMemoryLeak 1）。差值集中在「excess 数量级小」的三个 trace_errors 族：
它们的 excess 是 1~4，而 CPU 在裸 quantum 下的标准化超出量可以到 9.6（例：SEED-G02-0002，
CPU excess `1.06e-5` 对 quantum `1e-6`，标准化 9.606 压过 paymentUnreachable 的 1.000）。
**这就是上一轮 B 的 32/32 的真相**：B 的阈值测试是「真族是否合格」（32/32 确实全合格），
而排序判别力被 CPU 污染了；两件事不是一回事。

## D4 单信号消融：每条信号单独能识别自己那一族吗

每一行只读一条信号，其余五条完全不看。分类器要么报自己那一族，要么弃答——
代码层强制：受限运行若预测出别的族，`ablation()` 直接抛 `SeparabilityProbeError`。

| 信号 | 只读 | 服务 | quantum | support | 召回 | 精确率 | 外族误报 | 弃答 | 单独识别自己那族 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| productCatalogFailure | `trace_errors.error_count` | product-catalog | 1.0 | 8 | **1.000** | 1.000 | 0 | 24 | 是 |
| paymentFailure | `trace_errors.error_count` | payment | 1.0 | 4 | **1.000** | 1.000 | 0 | 28 | 是 |
| paymentUnreachable | `trace_errors.connection_error_count` | checkout | 1.0 | 4 | **1.000** | 1.000 | 0 | 28 | 是 |
| emailMemoryLeak | `memory_window.working_set_bytes` | email | 1.0 | 4 | **1.000** | 1.000 | 0 | 28 | 是 |
| kafkaQueueProblems | `queue_window.consumer_poll_lag_seconds` | fraud-detection | 0.001 | 8 | **1.000** | 1.000 | 0 | 24 | 是 |
| adHighCpu | `cpu_window.cpu_cores` | ad | 1e-06 | 4 | **1.000** | 0.333 | 8 | 20 | 是 |

**6/6 全部成立，召回全部 1.000。** 五条信号精确率 1.000、零外族误报——
即「这条信号动了」与「就是这一族」在这份数据集上**完全等价**。只有 CPU 有 8 次外族误报。

`overall_accuracy` 那一列（0.125 / 0.125 / 0.125 / 0.125 / 0.25 / 0.25）等于各族的
support/32，即每条信号恰好收回自己那一族、一个不多一个不少，这是「单独识别」的算术印证。

注意 `productCatalogFailure` 与 `paymentFailure` **读的是同一个字段**
（`trace_errors.error_count`），仅靠**读哪个服务**区分。这两族之间的区分不需要任何推理，
只需要知道服务名与族名的对应表——而这张表在 `TARGET_SERVICES` 里是公开的。

## 方法与自证

- **阈值**：leave-one-case-out。对每个 case，用**其余 31 个** packet 的健康期
  连续正向漂移（每个 packet 4 个，共 124 个）做 nearest-rank p99，再加该族 quantum。
  镜像 `g03_readiness.py` 的 `build_deterministic_thresholds_v3`（行 908），
  `DETERMINISTIC_PERCENTILE = 0.99`。
- **代码层断言**：`_frozen_thresholds_loo` 强制 `case_id not in training_case_ids`、
  `len(training_case_ids) == 31`、`len(drifts) == 31 * 4`，违反即抛 `SeparabilityProbeError`。
  单元测试 `test_leave_one_case_out_threshold_never_reads_the_held_out_healthy_samples`
  用**行为**验证而非只看列表：把某个 case 的健康期 CPU 抬高，它**自己**的阈值必须不变，
  **其余 31 个**的阈值必须全部上移。
- **唯一继承的不对称**：`emailMemoryLeak` 的相对下界是
  `0.05 × median(留出 case 自己的健康值)`，这是真实 registry 里唯一读到留出 case 的地方
  （尺度参照，不是判别信号）。**故意保留**——改掉它就是在测量一条 metric 并不使用的规则。
  设定 p99 的漂移池仍然完全排除留出 case。
- **封印字段**：`offset_table` 在真实抽取路径上调用 `_assert_no_forbidden_input`，
  单元测试覆盖「封印键进入分类器输入即硬停」。
- **n = 32**：只报点估计与完整表，**不报置信区间、不做显著性检验**。
- **零模型调用**：`model_calls: 0`。
- 边界取向：遇到判断边界往「可能过易」那边靠。具体两处已标注——
  单信号比例 0.7500 恰在下界；D1 的 0.9062 读作下界而非「剩余 9% 难度」。

## 复现

```sh
uv run python -m faultwitness_dev g03-separability \
  --dataset .audit/g03-readiness/g03-4622470-r9/scenarios.json \
  --output docs/engineering/diagnostics/g03-metric-v3-root-signal-separability.json
```

## 这份测量支持什么、不支持什么

**支持的**：在**当前任务表示**下，六条声明的数值根信号构成一张六选一查表。
故障不传播（非对角共现全为 0），真族信号 32/32 必然偏移，四个族的健康基线是恒零，
每条信号单独就有 1.000 召回。脱敏 `descriptions` 会去掉「阅读理解」那一半的捷径，
但**剩下的一半也不是取证推理**，而是「哪个计数器从 0 变成非零」。

**不支持的**：本轮**没有**测量任何重构后的任务表示，**没有**测量真实 agent 在这份数据上的表现，
**没有**给出通过/不通过的结论。路线决定由人做。若要走「重构任务表示」，
本记录里可直接用作设计输入的三项事实是：健康基线恒零（4/6 族）、
故障不跨服务传播（非对角共现全 0）、族与服务是一一对应的公开映射。

**四条 baseline 的处境不变**：r9 的 deterministic 0.8125 / no_rag 0.8750 /
naive_react_single 0.8854 / naive_react 0.9167 仍受 `descriptions` 泄漏（16/32 case）制约，
现在再叠加本轮结论——即便脱敏，这四个数字所在的任务仍是查表。引用限定条件见
`g03-r8-r9-live-divergence/README.md` 的 Q3 一节。
