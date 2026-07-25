# Governance Refactor Lessons Log

## GOV-OBS-013 — Corrective impact analysis must follow workload supply, not only changed files

- **Trigger:** C-G02-010 safely reduced ambient load from ten users to one and proved one no-fault
  checkout, but A-G02-010 then found that both payment fault observers still depended on incidental
  checkout timing. The 90-second oracle correctly failed because no correlated request trace existed.
- **Why the earlier seam was insufficient:** readiness, restart count zero, and one healthy checkout
  proved a clean lab but did not prove that every workload-dependent fault branch could generate its
  own diagnostic input. The changed ambient-workload supply affected payment oracles even though
  their source files were not modified by C-G02-010.
- **G02 action:** preserve the valid one-user/OOM correction. C-G02-011 adds one deterministic
  candidate-bound checkout for both payment variants and proves one real `paymentUnreachable` seam;
  no Gate L2 matrix or model call is folded into the corrective.
- **Post-G02 migration:** affected-dependency calculation must include declared runtime inputs such
  as ambient traffic, queues, clocks, credentials, and observability producers. A corrective that
  changes one of them needs one real proof per distinct dependent protocol, not a whole Gate replay
  and not a generic readiness smoke.
- **Metric impact:** none; N, 30-second spacing, 90-second window, trace oracle, cleanup, recovery,
  quality/performance thresholds, permissions, model route, and token/cost limits remain frozen.

## GOV-OBS-012 — Governance complexity, not CI compute, dominated G02 overhead

- **Measured evidence:** the 2026-07-25 full local `verify-fast` plus `eval-changed` run checked 378
  tests and 211 Markdown files in 28.7 seconds. The check runtime itself is not the dominant cost.
- **Dominant cost:** per-work-item plan/activate/evidence/close commits, duplicated lifecycle state,
  candidate/evidence/governance SHA coupling, manifest synchronization, and candidate-wide cache
  invalidation multiplied each small defect into repeated orchestration and documentation work.
- **Skill alignment:** basic tests, schema checks, resumable trial journals, and code/image/config/
  dataset/artifact provenance support application, infrastructure, and algorithm/evaluation skills.
  Repository ruleset simulation, per-Iteration SHA state machines, and repeated root-document mirrors
  add little evidence for those three engineering narratives.
- **G02 action:** do not refactor CI, schemas, or history during closure freeze. Keep the minimum
  checks required by the frozen Gate, apply selective phase inheritance, and close G02 before a
  governance migration. This entry is the final pre-candidate lesson update; later observations are
  collected in the one-time closure synchronization so they cannot create another candidate chase.
- **Post-G02 migration:** retain ordinary CI and experiment journals; replace the multi-SHA lifecycle
  with one Gate/release manifest containing code commit, runtime image, configuration, dataset, and
  result artifact digests. Documentation-only commits must never invalidate experimental evidence.
- **Metric impact:** none; this changes no Gate N, threshold, permission, model route, token/cost
  ceiling, health window, or failure semantics.

## GOV-OBS-011 — A global digest must not invalidate every phase

- **Trigger:** C-G02-005 changed only the `paymentUnreachable` scenario observer, while the current
  cache key put the complete candidate SHA and aggregate evaluator digest into every phase and
  therefore proposed rerunning the already-passing 60-cell isolation, six-stage trace, and
  22-surface canary matrices.
- **Avoidable cost:** those remote matrices would produce no new information and would violate the
  closure-freeze rule to rerun only a failed phase and affected dependencies.
- **G02 action:** ADR-0013 now rejects candidate-wide invalidation. EVAL-G02-032 uses explicit,
  reviewable manifest inheritance entries that preserve the original producing revision, artifact,
  timestamps, execution count, and private journal; candidate binding, static impact proof, affected
  deployment, the failed scenario phase, and downstream phases still execute.
- **Post-G02 migration:** cache keys and invalidation graphs must use phase-specific semantic
  subjects. Aggregate candidate/evaluator digests remain provenance and cannot alone invalidate an
  otherwise unchanged phase.
- **Metric impact:** none; N, thresholds, permissions, model route, token/cost ceilings, health
  windows, and failure semantics are unchanged.

## 用途与边界

本文件是 G02 关闭期间建立的追加式经验账本，用于捕获可证实的无效治理、治理成本异常和
后续轻量化候选。它不是 Gate 通过标准、状态源、waiver、ADR 或新的审批点，不阻塞当前
closure freeze，也不允许修改 Eval N、质量/性能阈值、权限、Ground Truth、locked tests、
模型路线、token/费用上限或失败语义。

记录遵循三个轻量原则：

- 只记录有代码、Git、journal、artifact 或明确执行时间线支撑的观察，不把普通实现故障
  自动归咎为治理成本。
- 新条目只追加到本文件；不要求同步 Master Plan、Claims、Gate Report 或已关闭资产，也不
  单独制造 planning/activation/closure 流程。
- G02 内只记录、不重构。治理迁移在 G02 关闭后单独决策、设计和实施。

已有量化复盘见 `docs/engineering/G02_CORRECTIVE_COST_POSTMORTEM.md`；本文件不复制其完整
提交统计，而是承接其结论并持续追加新观察。

## 2026-07-25 — 初始决策快照

### 1. G02 Master Plan 是否导致治理时间过长

是，但要区分两个层面。Master Plan 正确冻结了必要的安全、隔离、质量和统计标准；目前没有
证据证明 Gate N 或性能/质量阈值本身是 corrective 成本的主因。多次失败发生在完整 60-cell、
six-stage、22-surface、32-scenario 和 192-trial live matrix 完成之前。

不合理之处主要是 readiness 与执行结构：

- 把完整 live matrix 正确归到 L2 的同时，也把真实 client、平台、凭据、镜像、解释器和
  cross-namespace dependency 的最小 seam proof 一并推迟到 Gate，导致 Gate 成为首次真实集成。
- 计划冻结了 runner 名称和验证规模，却没有逐条证明 runner 在目标环境具备完整的部署、绑定、
  诊断和失败归因路径。
- 多份手写状态镜像、计划、报告、manifest 和全局索引被绑定到每次 corrective lifecycle，
  使小修复承担与实现规模不成比例的资产迁移。
- candidate、evidence 与治理 HEAD 的职责曾混合，造成与产品行为无关的 SHA 追逐和重复部署。

因此，Master Plan 对高治理成本负有实质责任，但问题是 work decomposition 与 evidence
architecture，不是应该趁机下调 Gate 指标。

### 2. G02 暴露的治理模式问题与轻量化方向

已确认的问题：

1. **手写镜像过多**：同一 lifecycle 状态散落在 `AGENTS.md`、`PROJECT_STATE.yaml`、
   `PHASES.md`、README、Gate/Iteration/Eval 文档中，修改量大于决策信息量。
2. **状态转换过细**：plan、activate、implementation、evidence、close 经常各占一次 commit；
   对单根因小修复，流程固定成本可超过代码与验证成本。
3. **失败证据非自动产出**：runner 未正常落 phase record 时，需要人工重建 manifest、REPORT
   和归因时间线，Eval 的可恢复性被治理补写替代。
4. **Gate 首次触碰真实 seam**：mock/memory/schema proof 证明了 shape，却没有证明真实工具、
   目标解释器、凭据通道或部署依赖能够执行。
5. **全局同步进入局部循环**：早期 corrective 会反复改 Master Plan、VALIDATIONS、Claims 和
   Gate Report；这些资产应只在最终 attempt/closure 汇总一次。
6. **成本类别混账**：root-cause engineering、targeted seam proof、Gate orchestration 和
   governance synchronization 未分账时，无法判断真正需要优化的是实现、Eval 还是治理。

G02 关闭后的重构候选：

- 只保留一个机器可读的 lifecycle source of truth，其余状态页生成或只在 Gate 边界更新。
- 由 phase journal 自动生成 Eval manifest 与失败 capsule，人工只写结论，不重抄时间戳、digest
  和 phase 清单。
- corrective 只登记单一 root cause、最小 diff、受影响分支和一次真实 seam proof；不创建专用
  harness，不同步全局 Gate 资产。
- Gate attempt 只消费冻结 runner；发现 deterministic defect 后一次性终止并前向纠错，成功后
  只复验失败项及受影响依赖。
- candidate identity 只随行为、运行 artifact、配置或测试语义变化；纯证据与复盘文档不得制造
  新业务候选。
- 下一 Gate 的 Master Plan 必须为每个外部 seam 登记真实最小执行、只读诊断、部署/绑定责任和
  artifact 路径，避免把完整 Gate 当作首次联调。
- 持续分别统计实现、targeted verification、Gate execution 与治理同步的耗时和 diff，依据实测
  选择重构目标，不用文档数量代替风险控制。

### 3. 现在是否重构全部治理资产

不推荐现在重构整套体系或迁移全部历史资产。当前最稳妥的顺序是：

1. 保持 G02 closure freeze，用现行协议完成最小剩余 corrective、统一候选 Eval 和一次性关闭。
2. G02 关闭后形成完整的执行时间线与成本分账，确认哪些规则有效、哪些只是重复手工同步。
3. 以独立治理迁移工作包设计新 canonical record、生成视图、manifest 自动化和兼容策略；先前向
   适用于 G03，再决定是否值得迁移仍活跃的资产。
4. 已关闭 G00/G01/G02 的审计资产保持不可变，不为格式统一回写历史。

原因是当前全面重构会同时改变 runner 的治理契约、active Gate 状态和 closure 资产边界，既会
扩大 G02 候选面，也会让我们失去对“旧治理完成 G02 的真实成本”的最后一组数据。先关闭再迁移
能够切断循环，同时保留可比较基线。

## 动态观察

### GOV-OBS-001 — corrective 固定治理成本超过实现成本

- **状态**：confirmed
- **证据**：`G02_CORRECTIVE_COST_POSTMORTEM.md` 记录 I-0034 使用 5 个 commit、累计 49 次
  文件触碰；Legacy I-0036 在实现前已有 31 次文件触碰。
- **不必要成本**：重复 plan/activate/close 状态镜像、全局文档同步和 per-corrective harness。
- **G02 内处置**：采用 C/A namespace、单根因 corrective、复用既有测试入口，并把全局同步
  推迟到最终 closure。
- **关闭后候选**：canonical lifecycle record + 生成视图 + journal 自动生成 manifest。
- **指标影响**：无。

### GOV-OBS-002 — EVAL-G02-028 trace 前置依赖未进入部署责任

- **状态**：confirmed readiness gap；尚不计为治理耗时结论
- **证据**：`lab-deploy-and-bind` 只部署 `fw-sut`；冻结 `trace-six-stage-matrix` 随后要求
  `fw-control/fw-trace-candidate` 等于新 candidate。一次冻结只读 inspect 失败，而既有 sanitized
  diagnose 显示 trace-service Pod 为 `1/1 Running` 且应用正常启动。
- **风险**：runner 健康但候选绑定未由任何已通过依赖建立；统一错误还未写 phase/trial journal，
  迫使操作层补做归因。
- **G02 内处置**：按 closure freeze 终止当前 A attempt，前向建立单根因 corrective；不原样重跑、
  不现场造诊断、不改验证 N 或失败语义。
- **关闭后候选**：Master Plan 的外部 seam contract 增加“谁部署、谁绑定、谁诊断、失败写到哪里”
  四项，并由 runner 自动把 operator-side prerequisite failure 写入 trial/phase journal。
- **指标影响**：无。

### GOV-OBS-003 — 外层工具默认 timeout 打断已完成的定点校验

- **状态**：confirmed operational waste
- **证据**：activation 的定点 governance check 已输出 `passed`，但 shell wrapper 在约 10.8 秒
  以 124 退出，后置 `git diff --check` 需要单独补跑。
- **再次发生**：A-G02-004 证据固化后的本地 `verify-fast` 被操作层误设的 1 秒 wrapper 上限
  中断；随后只补跑尚未完成的本地校验并正常得到 374 tests 与 Markdown 全通过，没有重跑任何
  Gate phase。这证明“禁用业务 timeout”仍需由统一 supervisor 默认值落实，不能依赖操作员记忆。
- **不必要成本**：一次重复进程启动和一次额外 diff 检查；没有新增信息。
- **G02 内处置**：不重复已通过的治理扫描；后续 progressing command 使用可持续等待与轮询，
  只补未完成步骤。
- **关闭后候选**：统一 command supervisor 默认不实施 wall-clock kill，并明确区分命令终态与
  orchestration wrapper 终态。
- **指标影响**：无。

### GOV-OBS-004 — 外层 timeout 禁用未覆盖内嵌工具 timeout

- **状态**：confirmed implementation gap
- **证据**：共享 `run_remote_script` 已忽略旧 `timeout=` 参数，但即将接入 G02 的
  trace-service 脚本仍含 `kubectl rollout status --timeout=5m`。
- **风险**：治理规则在外层成立，内层工具仍可把正常 rollout 按墙钟强杀，造成假失败。
- **G02 内处置**：只移除当前 corrective 实际接入路径上的 rollout kill；不扩大为全仓重构，
  不改变 HTTP 请求失败、Eval 指标或性能裁决。
- **关闭后候选**：治理迁移增加 nested-command timeout inventory，规则验证必须覆盖最终执行的
  子命令而不只检查 wrapper API。
- **指标影响**：无。

### GOV-OBS-005 — 失败 attempt 的外部残留未进入 cleanup contract

- **状态**：confirmed execution gap
- **证据**：A-G02-003 在 trace ingest 后、relay 前失败；新 candidate 的首次 smoke 因非空 buffer
  失败。既有 relay 随后恰好导出 2 条记录（旧 attempt 1 条、首次 smoke 1 条）并归零。
- **不必要成本**：一次必然失败的 smoke、一次额外归因和一次清理后复验。
- **G02 内处置**：不放宽 frozen smoke matrix；用既有 relay 修复已归因状态后只复验 smoke。
- **关闭后候选**：phase failure capsule 必须声明已发生的 side effect 与 cleanup owner；后续 candidate
  的 preflight 在执行 smoke/matrix 前检查并归因 stale external state。
- **指标影响**：无。

### GOV-OBS-006 — 必需的运行期 binding 被 clean-tree 规则误认成候选污染

- **状态**：confirmed operational waste
- **证据**：EVAL-G02-030 的四个 preflight 已通过后，首次 `lab-deploy-and-bind` 调用因
  `docs/evals/EVAL-G02-030/candidate-binding.json` 尚未进入本地 exact exclude 而被 clean-tree
  guard 拒绝；该文件正是 runner 启动所必需、候选绑定且禁止提交前伪造的运行期输入。
- **不必要成本**：操作员必须补本地 exclude 后重新调用 phase；失败发生在 trace-service deploy
  子步骤之后而 phase record 之前，导致同一候选的 trace deploy 再执行一次。
- **G02 内处置**：只加入该 Eval/路径的 `.git/info/exclude`，不放宽 clean-tree guard；四个已通过
  preflight 不重跑，后续 phase 继续使用原 exact-key journal。
- **关闭后候选**：运行期 binding 应位于天然 repository-external 的 Eval workspace，或由 runner
  在 clean-tree 判断中显式识别自己的 exact input；phase 内具有外部副作用的子步骤必须各自记录
  完成 checkpoint，phase 外层失败后不得从头重复已完成 deploy。
- **指标影响**：无；未改变候选、环境、N、阈值、性能或失败语义。

### GOV-OBS-007 — terminal scenario trial 丢弃原始失败 sample

- **状态**：confirmed evidence-design gap
- **证据**：EVAL-G02-030 的 `SEED-G02-0002` trial 只保存
  `fault oracle did not reach FAULT_ACTIVE`；`LiveScenarioObserver` 在 90 秒窗口终点已经拥有最后
  一个原始 sample，但 `run_gate_scenario_matrix` 的失败分支没有把它写入 trial payload。
- **不必要成本**：代码静态证据强烈指向 `paymentUnreachable` 的 caller/callee trace 选择错误，
  但冻结 evidence 无法证明最后 sample 中 checkout/payment 各有什么；必须在 C-G02-005 追加一次
  最小只读 real-seam 归因，而不能直接做一行修复。
- **G02 内处置**：不重跑 destructive phase、不把假设裁定为 pass；C-G02-005 先对冻结时间窗做
  具名只读对照，确认后只改观测 seam，并保留一次最小场景证据。
- **关闭后候选**：所有 terminal trial 必须原子保存最后可用的 sanitized observation、注入 readback、
  cleanup 结果和判定输入；失败 capsule 应由 runner 自动生成，不能由人工从散落日志重建。
- **指标影响**：无；补强失败可观测性不改变 oracle、窗口、N 或性能裁决。
- **本次实测成本**：由于 terminal sample 缺失，C-G02-005 需要 3 次约 3 秒的只读 Jaeger
  对照才把“caller 有 connection error、callee 无 span、PaymentService 关联位于标准 RPC tag”完整
  证实；修复后的单场景 seam 本身为 108.8 秒且一次通过。若失败 trial 原子保留 sanitized sample
  与 span shape，前三次归因查询可全部省去。

### GOV-OBS-008 — candidate-wide cache key 阻止受影响范围复验

- **状态**：confirmed design mismatch；实际重复成本待 A-G02-005 计量
- **证据**：`PhaseContext.cache_key` 把完整 `candidate_sha` 纳入每个 phase key。即使
  C-G02-005 只改变 `g02_lab.py` 的一个 fault observer，新 SHA 也会让 access、trace、canary 等
  未受影响 phase 无法继承；这与“修复后只复验失败项和受影响依赖”的治理目标不一致。
- **G02 内处置**：closure freeze 内不重构 PhaseEngine、不伪造跨候选 pass、不批量替换 SHA；按
  现行冻结协议完成 G02，并单独记录真实重复成本。
- **关闭后候选**：phase cache key 应绑定该 phase 的 subject digests、运行 artifact/config 和环境，
  再由依赖图证明未受影响继承；candidate SHA 保留为 provenance，而不是所有 phase 无差别失效键。
- **指标影响**：无；选择性继承只能复用 digest 完全相同的证据，不得减少 N、阈值或受影响复验。

### GOV-OBS-009 — wrapper 被打断时必须先读远端 checkpoint，不能盲目重跑

- **状态**：confirmed operational safeguard
- **证据**：C-G02-005 的 candidate-bound lab 命令在本地等待层被人工打断后已无本地进程，但远端
  `fw-g02-candidate-binding` 已是 `679d756...`，且 24/24 Deployments Ready。只读检查证明部署
  实际完成，因此没有再次调用 deploy。
- **避免的成本**：一次完整、无新增信息的 SUT redeploy；同时避免把“本地未收到终态”误分类为
  “远端未完成”。
- **G02 内处置**：沿用已完成远端状态，继续唯一一次 targeted scenario；不重跑部署，不伪造本地
  command pass。
- **关闭后候选**：外部副作用 runner 应把每个完成 checkpoint 原子写入 repository-external
  journal；supervisor 重连后先 reconcile checkpoint，再决定 resume 哪个子步骤。
- **指标影响**：无。

### GOV-OBS-010 — ADR 冻结了 selective inheritance，但 runner 从未实现

- **状态**：confirmed compatibility debt
- **证据**：ADR-0013 明确允许依赖闭包与 digest 完全一致的未受影响 phase 建立
  `inherited_from_manifest`；manifest schema 也有该字段。但仓库搜索表明该字段只出现在 schema、
  tests 和已填 `null` 的 manifest 中，没有 writer、validator 或 CLI。`PhaseContext.cache_key` 同时把
  完整 `candidate_sha` 与全局 `evaluator_digest` 放入每个 phase key，`PhaseEngine._exact_pass` 只接受
  当前 key 的私有 journal pass，`inspect_g02_close_readiness` 也只读取这些 journal records。
- **当前触发**：C-G02-005 只改变 `g02_lab.py` 的 payment observer、对应测试与 runbook，按当前
  closure freeze，A-G02-005 应只重跑受影响的 lab/scenario/downstream baseline 闭包；但新 SHA 与
  全局 evaluator digest 会让 A-G02-030 已通过的 60-cell access、six-stage trace 和 22-surface
  canary 全部 cache miss。
- **不能采用的路径**：手工伪造新 key 的私有 pass records 会绕过 runner 与独立复核；在 active
  Gate attempt 内补 inheritance tooling 又违反 closure freeze 的“不得新增框架”。
- **G02 内处置**：EVAL-G02-030 的 pass records 保持不可变且不在同一 exact key 重跑；A-G02-005
  按现有冻结 DAG 为新 candidate 各执行一次必需依赖，再执行 scenario/downstream。该重复成本单独
  记为当前 runner 的 compatibility debt，不以重构 Gate Eval 为代价阻断 G02 关闭。
- **附带 allowlist 缺口**：新经验账本不在当前 `EVIDENCE_ONLY_FILES`/prefixes 中，因此包含动态经验
  的 handoff commit 不能作为 `679d756...` 的 evidence-only descendant。G02 内不改 allowlist，
  而是在 A-G02-005 freeze 前提交账本并把最终 HEAD 作为新 candidate，显式计量这次纯治理 SHA churn。
- **关闭后候选**：phase subject ownership、依赖闭包、source-manifest digest 验证和 inheritance
  materialization 必须成为同一个机器校验 runner；全局 evaluator digest 应拆成 phase-specific
  digest，否则 selective rerun 只是文档承诺。
- **指标影响**：无；合法继承必须证明未受影响 phase 的原 N、artifact、环境与失败语义完全相同。

### GOV-OBS-011 — subject-equivalent descendant 与 detached-worktree 强制规则互相冲突

- **状态**：confirmed governance contradiction；已在 G02 内前向止血
- **证据**：`G02_EVAL_PROTOCOL` 与 `AGENTS.md` 前一条规则允许经 ancestry、changed-path 和
  subject digest 验证的 evidence-only descendant 执行；紧邻规则却又要求 governance/evidence
  HEAD 必须切到 detached candidate worktree。A-G02-009 激活后 24 个运行/Eval subject 与
  `17be4f2...` 完全一致，额外切换 worktree 不会增加任何实验信息。
- **不必要成本**：为让缺少 active-attempt 资产的旧 checkout 能启动 runner，需要复制或临时同步
  状态资产，并再次处理 clean-tree/binding；这正是治理 SHA 与运行 SHA 互相追逐的来源之一。
- **G02 内处置**：统一为“subject-equivalent descendant 可直接执行；只有存在未提交或非 allowlist
  subject 变化时才使用 detached checkout”。不重绑候选、不重部署、不重跑已通过 phase。
- **关闭后候选**：Gate runner 只接收 release/candidate ID 与 phase-owned subject manifest；Git
  worktree 位置和治理 HEAD 不再是执行语义。文档与状态资产不参与实验 cache identity。
- **指标影响**：无；仍验证候选 ancestry、运行/Eval subject、镜像/config/dataset/environment digest，
  不改变 N、阈值、权限、模型路线、token/费用、health window 或失败语义。

### GOV-OBS-012 — `kubectl apply` 与 Ready 不能证明候选实验环境干净

- **状态**：confirmed implementation-boundary gap；targeted seam 已在 Gate attempt 前拦截
- **证据**：A-G02-009 在 24/24 Ready 后遇到 fleet-wide POST 504，`accounting` 已累计 62 次
  OOM。C-G02-010 第一候选把 ambient users 从 10 降为 1 后仍在单 checkout 返回 504；部署只是
  apply 到旧 namespace。加入 `fw-sut` 自然等待式重建后，同一 seam 达到 restart 0、cart/checkout
  200、24/24 Ready。
- **避免的成本**：第一条 138 秒 real seam 拦住了又一次完整 Gate attempt、32 scenarios 与后续
  baseline；失败证据直接收敛根因，没有新建第二个 corrective。
- **G02 内处置**：只重建 disposable `fw-sut`，保留镜像/config/权限/阈值；新环境不继承任何
  60/6/22 或 scenario live evidence。
- **关闭后候选**：Master Plan 必须为每个 stateful/live environment 明确 `fresh`、`reused` 或
  `restored` 语义及可机器检查的 epoch；Pod Ready 只能是就绪证据，不能替代 clean-state 证明。
- **指标影响**：无；环境重建不降低 N、oracle、质量/性能阈值、安全边界或模型预算。
