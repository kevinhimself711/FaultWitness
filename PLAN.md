# FaultWitness unblock plan

## 已完成项

- U1: 删除 CI 中依赖未追踪 G02 历史产物的冻结聚合测试，提交 `059c84b`。
- U7.1: 修正 `.gitignore` 的 docs/evals artifact 例外，提交 `fda9cd8`。
- U7.2: 原样补交 G02-046 的 6 个机器产物，提交 `d7979be`。
- U7.3: 记录数值来源不一致（见下方已知坑）。
- U7.4: `verify-fast` 新增 latest-release 追踪 artifact 检查，提交 `0e29742`。
- U8: metric-v3 `descriptions` 维度泄漏探针（诊断模式，零模型成本），结论见下方已知坑。
- U2: 将文档/治理检查移至手动 `verify-docs`，CI 只保留快速检查，提交 `dc5b9ee`。
- U2.5: 语义测试迁出 `tests/governance/`，删除治理形态断言，提交 `78a47d6`。
- U3: 清理 6 个旧 G02 candidate worktree；目标旧分支在本地和远端均已不存在。
- U4: 原样归档 G00–G02 流程资产到 `docs/_archive/`，修复活动文档断链，提交序列 `8bdd0c9`–`5c7ba53`。
- U5: 重写根 `AGENTS.md` 并建立 scoped `.claude/rules/`，提交 `20a74b1`、`7e4f1a3`。
- U6: 将文档政策逐字写入 `AGENTS.md` 第 3 节，提交 `9041946`。
- U9: r8/r9 live 差异只读取证 + 两轮产物入库（诊断模式，零模型成本），结论见下方已知坑。
- U10: metric-v3 根信号分化度检查（诊断模式，零模型成本），结论见下方已知坑。
- U11: ADR-0019 撤销四轮 token 预算的数值冻结（只改文档，不动代码），结论见下方已知坑。

## 未完成项

无。本次任务不改 roadmap、Gate 划分、Gate Plan、G03 计划或 Gate 报告。

## 已知坑

G02-046 入库的机器产物记录的是 deterministic core_e2e=0.5、live 0.000。
这两个值经复盘确认分别源于规则表缺陷与标签格式 artifact。
而后续审计文档中引用的四个 baseline
(deterministic 0.8125 / no_rag 0.8750 / naive_react_single 0.8854 / naive_react 0.9167)
来自 metric-v3 的 r1–r9 运行,这批运行没有对应的 EVAL 目录,原始产物未入版本控制。
G03 重跑前必须先确认这四个数字的原始产物是否仍在 pci-2 上;
在还原之前,任何对外表述都应标注它们的来源运行与仪器版本。
2026-09-10 补：四个数字的原始产物在 `.audit/g03-readiness/g03-4622470-r9/aggregate.json`
（`baselines.*.metrics.core_e2e.estimate` 与 `findings.naive_react_single`），四值逐一吻合。
2026-09-11 更新：**已入版本控制**——r8 与 r9 两轮共 656 个文件原样入库到
`docs/engineering/diagnostics/g03-r8-r9-live-divergence/`（仅 `environment.hostname` 脱敏 4 处，
`-r3` 重复文件未入库），`.audit/` 原目录未改动。
同目录 r8 的 live 三臂为 0.1458/0.1250/0.1667，只有 r9 是这四个数字的来源，引用时须写明 r9。

- 2026-09-09：宿主默认 Codex runtime 的 pnpm/Node 版本为 11.19.0/v24.19.0，导致审计测试拒绝运行；用项目声明的 Node 22.14.0、pnpm 11.9.0 重跑后通过。
- 2026-09-11：`checks.py:97` 的 `run(["pytest", "-q"])` 调裸 `pytest`，在这台机器上解析到
  Anaconda 的 `pytest`（缺项目依赖），39 个测试文件 collection 报
  `ModuleNotFoundError: No module named 'faultwitness'`，看起来像大面积回归，其实是环境问题。
  必须按 Makefile 走 `uv run python -m faultwitness_dev verify-fast`（439 passed）。
  与上面那条 pnpm/Node 是同一类坑。
- 历史缺 artifact 的 EVAL 目录仍有 G00-001–006、G01-001–009、G02-021、G02-022；U7.4 只报告，不追溯补造。
- GOVERNANCE_V2.md 实质承载「先量后冻」那一课（含代价数字与三条硬性程序），
  但它不在任何自动加载通道里：AGENTS.md（60 行）只规定教训该写到哪、本身不承载教训；
  .claude/rules/ 三个文件都有 paths 门控。当前该课仅靠本地 CLAUDE.md 进入上下文。
  **在建立替代通道之前，不要从本地 CLAUDE.md 删除该节。**
- SBOM/CycloneDX 生成（run_repository_audit，依赖 pnpm）已退出 CI 与 pytest，
  仅存在于 verify-docs 的外部工具组，缺 pnpm 时静默跳过。
  G10 生产前审计需要它时，必须显式在有 pnpm 的环境跑一次并把产物入库，
  不能假设 CI 已经覆盖。
- ADR-0018 只解除了 +0.10 的文档层阻塞。代码层仍在执行：
  g02_baselines.py:55/:286/:290（:286 做精确字符串比对，:290 是实际门槛解析）、
  g03_readiness.py:2757、tests/g02/test_g02_baselines.py:394（registry 相等断言）。
  真跑 readiness 时门槛仍解析为 1.0167，仍不可达。
  解冻条件满足后需一次性改完这五处（代码与测试同一 commit）。
  解冻条件：泄漏探针通过 + 分化度检查通过 + 第一次 naive_react baseline 入库。
  注：诊断模式（diagnostic_only: true）不走 resolve_quality_floor，不受此阻塞。
- 2026-09-10 泄漏探针（`diagnostic_only`，零模型调用，源 r9，产物
  `docs/engineering/diagnostics/g03-metric-v3-descriptions-leakage-probe.json`）：
  **`trace_errors.descriptions` 存在局部泄漏，解冻条件的第一项未通过。**
  只读 descriptions 文本的 leave-one-out 分类器 A 在
  productCatalogFailure / paymentFailure / paymentUnreachable 三族 **16/16 = 1.0000**，
  另外三族 0/16 = 0.0000；总 0.5000（16 次弃答）、macro-F1 0.5000，
  多数类基线 C 为 0.2500。关键词表里直接出现 `catalog` `product` `feature` `flag` `fail`
  `enabled`（8 例）、`payment` `invalid` `token`（4 例）、`resolver` `unavailable`
  `addresses`（4 例）——明文点名故障族，无需推理。
  即数据集半数（16/32）是阅读理解而非取证推理，harness 在其上不可能显出价值。
  A(0.5000) 低于 B(0.5938) **不能**读作"无捷径"：B 用裸 quantum 而非冻结的
  leave-one-case-out healthy p99，`adHighCpu` 的 quantum 1e-6 低于环境漂移，
  在 25/32 个 case 上都满足（21 次误合格）从而污染 B 的排序；
  B 的阈值本身其实是 32/32 全中（`qualification_detail.true_label_qualification_rate = 1.0`）。
  判据只对 C 与三族/三族分裂成立，不对 B 成立。
  本轮只测量不修复：未改数据集、未改 `descriptions`、未动任何阈值。
  下一步是工具层脱敏（`_public_window` 的 `descriptions` 直通）后重采，
  现有四条 baseline 在脱敏后全部作废。
- 2026-09-11 r8/r9 live 差异排查（只读取证，`diagnostic_only`，零模型调用，记录见
  `docs/engineering/diagnostics/g03-r8-r9-live-divergence/README.md`）：
  **r8 是坏的那一轮，且 r8 就是 postmortem 里的假通过。**
  两轮同宿主、同 SUT、同模型（`qwen3.7-plus-2026-05-26`）、`scenarios.json` 逐字节相同、
  `config_digest`/`metric_definition_digest` 相同（评分规则未变），330 个文件名集合完全一致，
  sha256 35 同 / 295 异（异的全是输出类）。**不构成 ADR-0016/0017 的宿主不可比情形。**
  第一分歧点在 **prompt 构造、模型调用之前**：全部 288 个 trial 的 turn-1 input_tokens
  恰好相差 +64（min=max=mean=64，三臂各 96），而 `cache_key` 与文件名两轮完全一致，
  `relevant_source_digest` 不同而 `producer_sha` 相同且两轮均 `dirty_worktree: True`。
  机制：把 `core_e2e` 拆开后，**r8 的根因准确率 276/288=0.9583 反而高于 r9 的 273/288=0.9479**，
  差异 100% 在证据引用完整性 42/288=0.1458 vs 257/288=0.8924；r8 有 234 个 trial 说对根因
  但只引 1 个 ID（evidence 数分布 r8 `{1:241, 2:47}` / r9 `{1:3, 2:272, 3:11, 4:2}`），
  `missing_required_evidence` r8 三臂 77/80/77、r9 降到 0/3/0。
  即 r8 的 prompt 缺少"evidence 必须完整、不完整即算失败"那段指令，而评分照此扣分——
  **披露对称性失效**，失效方式是让门通过：r8 输出 `readiness_status: ready`、
  `deterministic_live_significant: true`、`best_baseline: deterministic 0.8125`，
  那个"显著"正是被它本应检出的缺陷制造的。deterministic 两轮均 0.8125（规则臂不过模型），
  印证影响只在三条模型臂。
  预登记的预期是"r9 更可能坏（有 10 个重跑 trial）"，**已被否证**：那 10 个的 `history[0]`
  全部是 `infra_failed` / `transport:ConnectError` 且 cache_key 与当前一致，是正常传输重试，
  不是改判路径。
  **推断环节（唯一）**：trial journal 不存 prompt 原文也不存 prompt digest，
  "+64 token 就是那段指令"由 token 计数 + 源码 digest + 行为后果三方推出，非逐字比对。
  对四个 baseline 的影响：r9 的数字不是 r8 那种仪器故障读数，但仍受 `descriptions` 泄漏
  （16/32 case）制约，引用限定条件见上述 README 的 Q3 一节。
  r8 的 0.1458/0.1250/0.1667 **不可**当作同一数据集的"另一次测量"参与对比或取平均。
- 2026-09-11 四轮 token 预算（ADR-0019，只改文档、零代码改动）：
  `MAX_CUMULATIVE_INPUT_TOKENS = 65_536`（`g03_readiness.py:117`，镜像
  `config/g03/baselines-v3.yaml:5`）**在整个 repo 里没有任何推导依据**——grep 全部
  `src/`/`config/`/`docs/` 只有常量与配置镜像两处命中，也不对应所用模型的上下文窗口。
  它先被挑选、再被 AMD-0007:168「the budget may not be raised」冻结，
  与 `+0.10` 是同一类错误（测量之前冻结一个数值目标）。
  **而且预算大头不是证据**：四轮上界固定开销 19902 的分解为
  假设性 assistant 草稿 **12288（61.7%）**、system×4 4644、framing 1280、template 1024、
  correction 666（逐项相加精确闭合）。草稿按 `MAX_COMPLETION_TOKENS × prior_count`
  （`:1801`，即 2048×(0+1+2+3)）计，**不论那几轮是否真的发生**。
  packet 只分到 9770 B；最差现有 packet（`SEED-G02-0008`）9469 B，**余量 301 B**。
  边际成本每服务 `trace_activity` +226 B / `trace_errors` +534 B（下界），
  即加一个上游服务就要 760 B，**塞不下**。AMD-0007:57 保护的 measured value
  正在被一个记账约定挤压，不是被数据量挤压。
  ADR-0019 只把**数值**改为待定，**形式不变**（仍算上界、仍留 headroom、
  `four_turn_token_headroom` 仍阻塞 live、`budget_exhausted` 仍计入分母），**不动任何代码**。
  **ADR-0019 不编辑 `AMD-0007.md`**——它是 hashed input 第 7 个
  （`_source_inputs_v3:2852-2864`），改它就会动 `config_digest` 破坏 resume 身份（r6/r7 即如此）。
  另：AMD-0007:168 的例外条款（"removing repeated representation metadata without removing
  measurements"）**已经允许**去掉四轮重复的 packet——packet 逐字重发正是 repeated
  representation，去掉它是执行该条款而非违反。但正确时机是**工具化改造
  （agent-collected evidence）**，那时每轮只带被请求的结果、四轮结构自然消失；
  现在手工拆是在解一个后续改造会删掉的问题，且会在只该改一个变量的轮次里改第二个。
  两处顺带记录的冲突：AMD-0007:639-641「future amendment」与 CLAUDE.md:91-92
  「不写修正案文档」不可同时满足（现行 ADR+PLAN.md 已选后者）；
  `max_tool_calls: 6` 声明于 AMD-0007:160-161 并在同句承认未实现，
  在 `config_digest` 里却无任何消费方（live 请求体无 `tools` 键），仍在改变 run 身份。
- 2026-09-11 preflight 的写入顺序（已核实，本轮据此执行）：
  `scenarios.json` 写于 `:3225`、`deterministic.json` 写于 `:3279`、
  `token_preflight_v3` 才跑于 `:3283`、`GovernanceError` 抛于 `:3354`。
  **即 token 不可行的 packet 仍会把数据集与 deterministic 矩阵完整写盘**，然后命令非零退出；
  两个探针只读 `scenarios.json` 且不引用任何 token 检查。
  **token 天花板阻塞的是 live 路径，不是零模型闸门。**
- 2026-09-11 分化度检查（`diagnostic_only`，零模型调用，源 r9，产物
  `docs/engineering/diagnostics/g03-metric-v3-root-signal-separability.json` 与同名 `-README.md`）：
  **脱敏 `descriptions` 不足以给任务留下取证难度——数值通道本身就是一张六选一查表，
  解冻条件的第二项按"任务过易"读，不按"通过"读。**
  最直接的一行：被 `descriptions` 明文泄漏的那 16 个 case（三个 `trace_errors` 族），
  在完全不读 `descriptions`、只看数值的情况下 D1 仍达 **0.8750**（其余三族 0.9375）——
  **泄漏是冗余捷径，不是唯一捷径**。
  冻结 leave-one-case-out healthy p99 的零模型分类器 D1 = **0.9062 / macro-F1 0.9069**（零弃答），
  裸 quantum D2 = 0.5938 / 0.5306，多数类 D3 = 0.2500 / 0.0667，**D1 − D2 = +0.3125 / +0.3763**。
  D4 单信号消融：**六条信号 6/6 单独就能识别自己那一族，召回全部 1.000**，
  其中五条精确率 1.000、零外族误报；只有 `adHighCpu` 精确率 0.333、8 次外族误报。
  真族信号 **32/32 全部合格**；四个族（productCatalogFailure / paymentFailure /
  paymentUnreachable / kafkaQueueProblems）healthy median 恒为 0，即"从零变成非零"而非信噪分辨。
  正交性：p99 下平均 1.2500 条偏移信号/case、{1条:24, 2条:8}、单信号比例 0.7500（恰在注册下界）
  且 24 个全是真族；**共现矩阵除 `adHighCpu` 行列外非对角元素全为 0 ⇒ 故障不跨服务传播**，
  剔掉 CPU 的 8 次误合格后单信号比例即 32/32。
  逐族 D1：四族 1.0000、emailMemoryLeak 与 productCatalogFailure 各 0.7500，跨度 0.2500，
  `fractured: false`，无 0.0 族。**D1 的 3 个错与 D2 的 13 个错全部被 `adHighCpu` 抢走**——
  该通道 124 个漂移样本里只有 1 个非零决定整条阈值，留出 0014 或 0021 时阈值塌回 quantum。
  **预登记的预期"D1 会低于 D2、此前 32/32 是阈值污染"已被否证**：清干净阈值后判别力上升。
  即上一轮 B 的 32/32 是真族全合格（这点为真）叠加 CPU 污染排序，两件事不是一回事。
  本轮只测量：未改数据集、未改 `descriptions`、未改任何阈值、未改 `g03_readiness.py` 行为。
  下一步的路线决定（脱敏后重采 vs 重构任务表示）由人做；可直接用作重构设计输入的三项事实是
  健康基线恒零（4/6 族）、故障不跨服务传播、族与服务是 `TARGET_SERVICES` 里公开的一一映射。
