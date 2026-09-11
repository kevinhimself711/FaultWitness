# r8 与 r9 的 live 结果差异：取证记录

`diagnostic_only: true`。本目录是**只读取证 + 证据入库**的产物，不是 Gate attempt，不登记 work
item，不改 `PROJECT_STATE.yaml`，G03 保持 `not_started`，不改任何阈值、数据集或
`g03_readiness.py` 的行为。本轮**只做取证与比对，不做修复**：没有重跑、没有作废、没有重命名任何
`.audit/` 目录，没有调用任何模型。

入库的原因是 `.audit/**` 被 gitignore，而 `AGENTS.md` §3 认为未提交的产物等于该次运行没有发生。
旧宿主 pci 的证据就是这样丢掉的（ADR-0016/0017）。

## 一句话结论

r8 与 r9 跑在**同一台宿主、同一个 SUT、同一个模型、同一份逐字节相同的数据集**上，评分规则也未变；
两轮 live 分数相差 5–6 倍的**全部原因是"证据引用完整性"，不是诊断准确率**——r8 的
prompt 缺少"evidence 必须完整"那段指令，导致 234 个 trial **说对了根因但只引用了一个 ID**，
按评分规则记为失败。**r8 是坏的那一轮**，而它当时输出了 `readiness_status: ready`。

## 两轮的基本事实

| | r8 | r9 |
| --- | --- | --- |
| 目录 | `g03-4622470-r8` | `g03-4622470-r9` |
| live trial 数 | 288（96 × 3 臂） | 288（96 × 3 臂） |
| live 执行时间（UTC） | 2026-09-05T10:16:04Z → 10:40:12Z | 2026-09-05T11:21:12Z → 2026-09-08T12:34:26Z |
| `producer_sha` | `4622470a…` | `4622470a…`（相同） |
| `dirty_worktree` | `True` | `True` |
| `relevant_source_digest` | `702f0ebb…` | `8c6f7d09…`（**不同**） |
| `config_digest` | `ece5a36f…` | `ece5a36f…`（相同） |
| `metric_definition_digest` | `fc6d001b…` | `fc6d001b…`（相同） |
| `dataset_digest` | `8f5a628a…` | `8f5a628a…`（相同） |
| `amd_digest` | `03da4df9…` | `de168c5c…`（不同） |
| `readiness_status` | **`ready`** | `blocked` |
| `blocked_reason` | `null` | `unclassified` |
| `deterministic_live_significant` | **`true`** | `false` |
| `best_baseline` | `deterministic` 0.8125 | `naive_react` 0.9167 |

`core_e2e`：

| 臂 | r8 | r9 |
| --- | --- | --- |
| deterministic | 0.8125 | **0.8125（两轮相同）** |
| no_rag | 0.1458 | 0.8750 |
| naive_react_single | 0.1250 | 0.8854 |
| naive_react | 0.1667 | 0.9167 |

deterministic 是规则臂、不过模型，两轮完全一致——这本身就把差异定位在了三条模型臂上。

## 输入是否真的相同

上一轮只比了 `scenarios.json` 和 `dataset_digest`，不足以下结论，所以本轮做了全量 sha256 比对。

两个目录各 **330 个文件，文件名集合完全相同**（任一侧独有 0 个），其中包括全部 288 个
live trial 的哈希文件名。sha256 比对：**35 个相同 / 295 个不同**。

- **相同（输入类）**：`scenarios.json`（2.6MB，逐字节相同）、`metric-definition.json`、
  `deterministic.json`、全部 32 个 scenario trial journal。
- **不同（输出类）**：`aggregate.json`、`live.json`、`preflight-summary.json`、
  `run-manifest.json`、`summary.json`、全部 288 个 live trial journal。
  （`aggregate-r3.json` / `live-r3.json` 与各自的基础文件逐字节相同，是重复文件，未入库。）

`config_digest` 与 `metric_definition_digest` 两轮一致 ⇒ **评分规则没有变过**。
差异不可能来自评分逻辑。

## 宿主是否相同

**相同，不构成 ADR-0016/0017 的不可比情形。**

- `checkpoint_identities` 两轮完全一致：模型 `qwen3.7-plus-2026-05-26`、
  `sut_image_set_digest 3df50295…`、`sut_producer_sha 86a459c0…`。
- `environment` 两轮一致：同一 hostname（已脱敏，见下）、`Windows-11-10.0.26200-SP0`、
  Python 3.12.7。
- r9 的 `host_identity.host_key_digest = adcb731a…` / `runner_kernel = Windows-11` 与当前这台机器
  相符。r8 缺这个字段的唯一原因是 `host_identity_v3` 当时还不存在，不是宿主不同。
- 时间窗不重叠（r8 于 10:40 结束，r9 于 11:21 开始），不存在两轮互相干扰。

## 第一分歧点（Q1）

**prompt 构造，发生在模型调用之前。**

证据，按排除顺序：

1. 输入侧逐字节相同（上一节），`config_digest` / `metric_definition_digest` 相同 ⇒
   不是数据集差异，也不是评分规则差异。
2. 288 个 live trial 的**文件名与 `cache_key` 两轮完全一致**，`(baseline, case_id, repetition)`
   三元组也一一对应 ⇒ trial 身份与缓存身份相同，不是调度差异。
3. 然而**第 1 轮对话的 input_tokens 在全部 288 个 trial 上恰好相差 +64**
   （min = max = mean = 64，三条臂各 96 个，无一例外）。
   常数偏移是模板改动的特征，不是数据或采样差异。
   （naive_react 的 *总* token 差异分布很宽，那是多轮上下文累积，属于第一分歧点的下游效应；
   turn-1 才是干净信号。）
4. `relevant_source_digest` 不同而 `producer_sha` 相同，且两轮都是 `dirty_worktree: True`
   ⇒ 存在未提交的源码改动，只能通过 `relevant_source_digest` 观察到。
5. 当前 `src/faultwitness_dev/g03_readiness.py` 的 `build_baseline_prompt_v3`（行 1710 起）
   system prompt 中含一段 355 字符 / 56 词的 evidence 完整性指令
   （"evidence must be COMPLETE as well as correct: cite every observation ID that supports the
   diagnosis, including the trace observation that localises the failing service, not only the
   single most striking signal. A diagnosis naming the right cause with an incomplete evidence set
   is scored as a failure. Most incidents require more than one observation ID."），
   量级与 +64 token 吻合。

**未能直接验证的一项**：trial journal 不持久化 prompt 原文，也不记录 prompt digest
（payload 只有 `baseline` / `case_id` / `cost_cny` / `input_tokens` / `output_tokens` /
`repetition` / `result` / `trial_telemetry`）。所以"这 64 个 token 就是上述那段指令"是
**由 token 计数 + 源码 digest 差异 + 行为后果三方推出的，不是逐字比对出来的**。
这是本记录中唯一的推断环节；下面的机制部分则是直接测量的。

## 机制：差异 100% 落在证据引用完整性上

把 `core_e2e` 拆成"根因是否正确"与"证据集是否完整且无干扰项"两项：

| | r8 | r9 |
| --- | --- | --- |
| 根因正确 | 276/288 = **0.9583** | 273/288 = **0.9479** |
| 证据完整 | 42/288 = **0.1458** | 257/288 = **0.8924** |

**r8 的根因准确率反而比 r9 略高。** r8 有 234 个 trial 说对了根因但证据集不完整。

引用的 evidence ID 个数分布：

- r8：`{1: 241, 2: 47}`
- r9：`{1: 3, 2: 272, 3: 11, 4: 2}`

`REQUIRED_KINDS` 每个故障族要求恰好 2 个证据 kind，所以 r8 那 241 个"只引 1 个 ID"的 trial
按规则必然失败。逐臂失败原因（naive_react / naive_react_single / no_rag）印证同一件事：

- r8 由 `missing_required_evidence` 压倒性主导：**77 / 80 / 77**，`wrong_root_cause` 仅 3 / 4 / 5，
  `distractor_evidence` 0 / 0 / 0。
- r9 的 `missing_required_evidence` 降到 **0 / 3 / 0**，剩下的失败是
  `distractor_evidence` 4 / 2 / 7 与 `wrong_root_cause` 4 / 6 / 5。

算术闭合：96 − 77 − 3 = 16 → 16/96 = 0.1667（naive_react）；96 − 77 − 5 = 14 → 14/96 = 0.1458
（no_rag）；96 − 80 − 4 = 12 → 12/96 = 0.1250（naive_react_single）。
本记录中的六个臂分数均由独立重算复现，与 `aggregate.json` 逐一吻合。

**泄漏不能解释这个差异**：r8 用的是同一份已确认存在 `descriptions` 泄漏的数据，却只有 0.1458。

## r9 那 10 个重跑 trial（已核查，不影响结论）

r9 有 10 个 trial 的 `execution_attempt = 2` / `record_version = 4`，执行于 2026-09-08，
其余 278 个为 2026-09-05 一次成功。逐个核查：10 个的 `history[0].status` 全部是
`infra_failed`，原因全部是 `transport:ConnectError`，且 `history[0].cache_key` 与当前
`cache_key` **完全一致**。即这是传输失败后的正常重试（`.claude/rules/experiments.md`
允许 resume infra-failed trial），不是重新评分路径，没有"改判"任何结果。
两轮最终 trial 状态均为 288 个 `pass`（此处 `pass` 指 trial 执行成功，评分结果在 payload 内）。

继承关系：r8 从 r5 继承 32 个、r9 从 r8 继承 32 个，**全部是 scenario trial，live trial 继承 0 个**
——288 个 live trial 每轮都是全新执行的。

## 三个问题的回答

**Q1 第一分歧点在哪？**
prompt 构造，模型调用之前。见上文五条证据。分歧不在数据集、不在调度、不在评分规则。

**Q2 哪一轮是坏的？**
**r8。** 判据不是"r8 分数低"（低分本身可以是真实的难度），而是：r8 的根因准确率
（0.9583）**高于** r9（0.9479），差异全部来自证据引用完整性（0.1458 vs 0.8924），
且 r8 有 234 个 trial 说对根因却引用不足。r8 的 prompt 没有告诉被测臂"证据必须完整、
不完整即算失败"，而评分规则照此扣分——这正是**披露对称性失效**：评分标准没有对被测臂披露。

其governance后果是 postmortem 点名的那件事：r8 记录 `readiness_status: ready`、
`blocked_reason: null`、`deterministic_live_significant: true`、
`best_baseline: deterministic 0.8125`。**deterministic 对 live 的"显著优势"是由那个抑制了
live 证据引用的 prompt 缺陷制造出来的**，而这个缺陷恰恰是该统计判据本应检出的东西。
r8 就是 postmortem 里的假通过。

**预登记与否证**：进入本次排查前我预登记的预期是"r9 更可能是坏的那一轮"——理由是 r9 有 10 个
重跑 trial 且分数高得可疑，怀疑存在改判。**该预期被否证**：10 个重跑经核查是 transport
重试、cache_key 一致，而分数差异的方向与根因准确率相反，指向 r8。如实记录。

**Q3 r9 的四个数字能用吗？**
可以引用，但**不是干净的**，必须带限定条件。它们不是 r8 那种意义上的仪器故障读数
（r8 的读数由未披露的评分标准产生，r9 的 prompt 与评分规则一致），但仍受两项已知问题制约：

1. **`descriptions` 泄漏**：同一数据集 32 个 case 中有 16 个（productCatalogFailure /
   paymentFailure / paymentUnreachable 三族）的 `trace_errors.descriptions` 明文点名故障族，
   零模型分类器可 16/16 命中。见 `../g03-metric-v3-descriptions-leakage-probe.json`。
   数据集半数是阅读理解而非取证推理，harness 在其上无法显出价值。
2. **来源目录未提交过**（现已入库，见下），且 `dirty_worktree: True`，
   源码状态只能靠 `relevant_source_digest` 定位，无法从 git 历史还原。

**引用这四个数字时必须附带的限定条件**：

- 写明来源是 **r9**（不是 r1–r9 泛指，也不是 r8）：
  deterministic 0.8125 / no_rag 0.8750 / naive_react_single 0.8854 / naive_react 0.9167。
- 写明仪器版本 **metric-v3**、模型 `qwen3.7-plus-2026-05-26`、N = 96/臂、
  `config_digest ece5a36f…`、`dataset_digest 8f5a628a…`。
- 写明**数据集存在 `trace_errors.descriptions` 局部泄漏，16/32 个 case 受影响**，
  这四个数字是在该泄漏数据上取得的，脱敏重采后全部作废。
- 写明 r9 自身的判定是 `blocked` / `unclassified`，**不是一次通过的运行**。
- 不要把 r8 的 0.1458 / 0.1250 / 0.1667 当作同一数据集的"另一次测量"来做对比或取平均——
  它们出自一个未向被测臂披露评分标准的 prompt，是仪器故障读数。
- n = 32 个 case，不报置信区间、不做显著性检验。

## 入库范围与脱敏

每轮各 328 个文件（原 330 减去 2 个逐字节重复的 `-r3` 文件），共 **656 个文件，15MB**：

- 顶层结果类：`aggregate.json`、`live.json`、`summary.json`、`preflight-summary.json`、
  `run-manifest.json`、`metric-definition.json`、`deterministic.json`、`scenarios.json`（各 2 份）
- `journals/live-reference/trials/` 288 个 × 2
- `journals/scenarios/trials/` 32 个 × 2

**未入库**：`aggregate-r3.json`、`live-r3.json`（与 `aggregate.json` / `live.json`
逐字节相同的重复文件，各 2 份，共 4 个）。两轮均无 `journal-index.json`。
无单文件超过 5MB（最大 `scenarios.json` 2.6MB），因此 5MB 规则未触发，全部原样入库。

**脱敏扫描**：扫了全部 660 个候选文件，模式覆盖 `口令 / 私钥 / token / api[_-]?key /
BEGIN .*PRIVATE KEY / RFC1918 与 loopback 网段 / 退化通路公网 IP / 已知宿主名与 SSH 用户名 /
绝对本地路径（Windows 与 POSIX）/ ssh 公钥 base64`。具体模式串不写进本文件——
它们本身含宿主名，而 CLAUDE.md 要求宿主名不出现在任何提交物里；
模式来源见 CLAUDE.md 的「环境事实」一节。

- 私钥 / `api_key` / 内网 IP / 退化通路 IP / 宿主名 / SSH 用户名 / 绝对路径 / ssh 公钥：
  **0 命中**。
- `token` 类关键词 19,802 次命中，**逐个归类后全部为非敏感**：`input_tokens` / `output_tokens`
  各 9,633 次（遥测计数）、`token_stats` / `cumulative_*_tokens` / `max_completion_tokens` /
  `four_turn_token_preflight`（预算字段）36 次、以及 500 次
  `"Payment request failed. Invalid token."`——这是 `paymentFailure` 故障族的**故障文本本身**，
  是证据的一部分，不脱敏。
- **实际脱敏 1 项**：`environment.hostname` 的机器名，出现 4 次
  （r8 与 r9 的 `summary.json` 与 `preflight-summary.json` 各 1 次），
  替换为 `<redacted-runner-hostname-A>`。**两轮用同一个占位符，因为"两轮 hostname 相同"
  本身是同宿主的证据，必须保留这个相等关系。**

脱敏前后 sha256（脱敏破坏了这 4 个文件的字节同一性，故在此登记原值以备核对；
两轮的 `artifact_digests` 均不覆盖这两个文件名，因此脱敏未破坏任何已记录的校验链）：

| 文件 | 脱敏前 sha256 | 脱敏后 sha256 |
| --- | --- | --- |
| `g03-4622470-r8/summary.json` | `44dd8f810d4c318ef6d52e6ae6c16f504736f4c54fe111e4799a88da3a072f71` | `081eb13932128ac4a4486b2415fa9f76cc899508bfd0daeac1b1ede3ac6b686e` |
| `g03-4622470-r8/preflight-summary.json` | `45653a7c7a09e621f849ca3011e066dcb222216f9666e53652be2ae987f2444d` | `ee607e5adbb7ea635ece2d3d1ec03b9612d940ea8f5a96f24fcff454c47ca73f` |
| `g03-4622470-r9/summary.json` | `6537a0e8ae6fded2311ff123dfa985d885049a18f701fe743f225ecaf6ad9abd` | `fd707121c36d2c74ec6dbe0b779f6a20e991edd8d65c51dd9047f285d00dba8d` |
| `g03-4622470-r9/preflight-summary.json` | `aadd153ebd96498da7c6ddee6de5aacb8725a2a4bbd043ab97b04db9985f7a38` | `3ac9ab2d8ffc6177d31e5c1eb507613c01b34dd9c084be742a0ca2f078a4e108` |

其余 652 个文件**逐字节原样入库**，未做任何修改。
**数值、case_id、标签、时间戳、digest 一律未脱敏**——它们是 provenance 的一部分。

原始位置：`.audit/g03-readiness/g03-4622470-r8` 与 `…-r9`（仍在原处，未改动、未作废、未重命名）。

## 候选 postmortem 教训

**评分标准必须对所有被比较的臂同等披露，否则失效方式是"门通过"而不是"门失败"。**
r8 按 `REQUIRED_KINDS` 要求证据集完整，却没在 prompt 里告诉被测臂这一点；
被测臂说对了根因（0.9583）却因少引一个 ID 而记为失败（完整性 0.1458），
于是 deterministic 显得"显著优于" live，`readiness_status` 输出 `ready`——
制造那个"显著"的正是该判据本应检出的缺陷。
（这条已在 `POSTMORTEM_MEASURE_BEFORE_FREEZE.md` 与 `.claude/rules/experiments.md`
的披露对称性条目中，本次为它补上了逐 trial 的量化证据。）
