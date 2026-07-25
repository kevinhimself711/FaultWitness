# Governance Refactor Lessons Log

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
- **不必要成本**：一次重复进程启动和一次额外 diff 检查；没有新增信息。
- **G02 内处置**：不重复已通过的治理扫描；后续 progressing command 使用可持续等待与轮询，
  只补未完成步骤。
- **关闭后候选**：统一 command supervisor 默认不实施 wall-clock kill，并明确区分命令终态与
  orchestration wrapper 终态。
- **指标影响**：无。
