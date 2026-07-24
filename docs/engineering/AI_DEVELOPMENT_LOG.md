# AI Development Log

## 2026-07-24 — I-0024 candidate-bound collector correction

Candidate `a2797037d1a3aa5c7f7264c2c3b122712b6d1677` replaces the three
operator-precomputed isolation inputs exposed by EVAL-G02-008 with candidate/environment-bound
provisioning and executable collectors. Credentials are generated only on the private host,
stale candidate credentials are disabled before rotation, images are digest pinned, and the
repository receives only named Secret references. Access evidence persists per cell; trace and
canary evidence persists per collection and per stage/surface. Only classified infrastructure
failures resume, while policy, metric, leakage, binding, capability, or artifact failures remain
terminal for that candidate.

EVAL-G02-009 passed exactly five local deterministic cases. It reran V-G02-009 and V-G02-011 at
their frozen Iteration N=4 and kept V-G02-010 Iteration N=0. Its fake 60/6/22 enumerations prove
runner shape only: private-server execution, Gate L2 cells, destructive scenarios, LangSmith,
Bailian, and model calls all remained zero. This corrective work occurs before replacement
orchestration; I-0025 is still forbidden to add implementation or a test framework.

## 2026-07-24 — G02 EVAL-G02-008 runner-readiness failure

Candidate `7d6648850108129c81fe98260aff8342683b5622` passed four fail-fast preflights and
`lab-deploy-and-bind` with 30 pinned image subjects and 24 ready Deployments. Before the first
zero-tolerance matrix ran, readiness inspection proved that `g02.access_matrix`,
`g02.stage_matrix`, and `g02.canary_matrix` only validated operator-precomputed JSON. There was no
candidate-bound identity/storage provisioner, 60-cell access collector, six-stage correlated span
collector, or 22-surface canary injector/collector. The expected object bucket, principal
credential Secrets, and all three phase inputs were absent.

This is a deterministic implementation/readiness failure, not an infrastructure retry. I-0023 and
EVAL-G02-008 are terminal with complete negative evidence and `open_evidence: []`; no complete
matrix cell, destructive scenario, or model call ran. I-0024 forward-corrects the missing runner
implementation locally without executing L2, and I-0025/EVAL-G02-010 performs replacement
orchestration. No closed Iteration reopens and no operator-precomputed input is accepted as a
substitute for an executable candidate-bound collector.

## 2026-07-24 — I-0022 forward isolation correction

Candidate `7d6e07bc142bdd5cb0bcd1a465ae3b04931b799c` corrected only the deterministic
V-G02-009 reachability root cause and the hard-coded terminal Eval route. EVAL-G02-007 passed five
local deterministic cases: exact baseline observability egress, exact ingress principal, rejection
of broad/private HTTPS egress, preservation of all four identity-deny contracts, and forward
orchestration/terminal-transition selection. It ran no Gate phase, destructive scenario, external
service, or model call and closed with `open_evidence: []`.

One launch wrapper first wrote its logs inside the repository, so the runner's clean-tree guard
rejected the command before any Eval case ran. The attempt was retained outside Git, the known
cause was corrected by moving wrapper logs to the external evidence root, and the unchanged
candidate then passed. This reinforces that supervision artifacts must never mutate the subject
checkout; it does not alter N, thresholds, retry semantics, or the classification of genuine
policy/metric failures.

## 2026-07-24 — G02 EVAL-G02-005 forward failure handling

Candidate `585deaee6548be0940d184bee3c73dadb4511fdb` passed four fail-fast preflights and
`lab-deploy-and-bind`. During live V-G02-009 input production, the `baseline-agent` principal was
denied at Loki and Tempo while same-target canonical-owner controls returned HTTP 200. The frozen
policy had neither baseline egress to `fw-observability` nor matching ingress there. The run stopped
before trace, canary, destructive scenario, or model phases.

The failure is recorded as deterministic policy/zero-tolerance failure with `open_evidence: []`.
I-0020 becomes immutable terminal `failed`; I-0022 corrects the exact policy and forward Eval
routing, and I-0023 replaces orchestration. This follows the I-0021 lifecycle policy: no completed
or failed owner Iteration is reopened, and no operator-adjudicated pass or same-candidate rerun is
created.

本日志永久记录 AI 协作开发中的重要执行事实、失误、负面实验和流程改进。它不替代
Gate Report、Eval Report 或 Git 历史，也不得用复盘结论回写已关闭 Gate 的证据。

## 2026-07-23 — G01 执行复盘

### 结论

G01 的标准和必要 live 验证没有失当；主要问题是 Iteration 验收债务被集中转移到
I-0015，同时最终 Eval runner 在最终审计阶段才实现。I-0015 因此承担了第二轮开发、
远程部署联调、故障矩阵、统一候选重绑定和 Gate 关闭协议修复，而不是单纯复验。

### 时间线与量化

以下时间取自 Git author time，是执行阶段的可审计近似，不将夜间无提交空档算作有效
工作时间。

| 阶段 | 起止提交时间（America/New_York） | 近似耗时 |
| --- | --- | ---: |
| G01 Master Plan 冻结 | 2026-07-22 12:41 | 基准点 |
| I-0007 | 12:49–13:53 | 1 小时 4 分 |
| I-0008 | 13:54–16:27 | 2 小时 33 分 |
| I-0009 | 16:27–17:21 | 54 分 |
| I-0010 | 17:21–17:42 | 21 分 |
| I-0011 | 17:42–17:57 | 15 分 |
| I-0012 | 17:57–19:33 | 1 小时 36 分 |
| I-0013 | 19:33–20:25 | 52 分 |
| I-0014 handoff | 20:25–20:49 | 23 分 |
| handoff 后补 Model Gateway 部署 | 20:49–21:12 | 23 分 |
| I-0015 有提交的最终审计窗口 | 2026-07-23 05:46–12:39 | 6 小时 53 分 |

从 G01 实施启动到最后一个 I-0014 私有 checkpoint 约 8 小时 23 分；I-0015 最终
审计约 6 小时 53 分。排除夜间空档后，最终审计约占二者合计有效时间的 45%。从
I-0015 handoff `384b8a8` 到最终业务候选 `4c84355` 有 46 个提交、57 个文件变化、
3,131 行新增和 134 行删除。这个规模证明最终审计发生了实质性实现泄漏。

### 七类浪费

1. **Iteration Eval debt rollover**：I-0008、I-0009、I-0011、I-0012、I-0013
   在 handoff 时保留了恢复、故障注入、负载和相关 Trace 等大块 open evidence。
2. **Final-audit implementation leakage**：I-0015 才新增 Gate evaluator、恢复工具、
   PostgreSQL/Redis/API/Trace 故障矩阵及其测试。
3. **Fail-late ordering**：确定性的 manifest debt 检查位于 900 秒稳定窗口、恢复和
   多个 live matrix 之后，已知不可能通过的候选仍先消耗昂贵流程。
4. **Candidate SHA cascade**：测试 fixture 或 evidence sync 改变 HEAD 后，八个历史
   manifest、部署绑定和关闭检查被连锁判旧。
5. **Repeated stability work**：两个独立 15 分钟窗口验证了相同目标；第二轮没有增加
   与其成本相称的新证据。
6. **Unattributed transport handling**：generic transport error 没有阶段和通道归因，
   先增加全局 SSH retry，再定位到 fresh-session probe 使用错误通道。
7. **All-or-nothing and duplicate live work**：36 次模型 trial 只在全部完成后统一写盘；
   walkthrough 还会重新调用部分已经产生证据的 remote smoke。

### 必要成本

- 一次绑定明确候选、artifact digest 和环境指纹的 15 分钟稳定窗口。
- 一次 K3s snapshot/restore、PostgreSQL fresh-target restore 和 Helm rollback/reinstall。
- 真实 PostgreSQL、Redis、SSE、Trace 故障矩阵和 36 次模型能力 trial。
- Ubuntu、Windows、private-server 的统一候选验证和最终 reconciliation。
- 安全、租户隔离、审批、Ground Truth 与 locked-test 零豁免检查。

### 可压缩或可消除成本

- 重复的第二个稳定窗口、相同 remote smoke 和已通过 trial。
- 在昂贵步骤之后才发现的 manifest、binding、schema 和 publication 静态失败。
- 由 evidence-only 文档提交或非运行时测试 fixture 引发的完整重新部署和证据重绑。
- 对 generic error 增加无关全局重试，而不是先隔离失败 stage/channel。
- 在最终 Gate audit 内现场实现本应属于前序 Iteration 的 Eval harness。

### 固化措施

- GR-02–GR-12 已登记到 G02 占位资产并写入根协作规则；GR-01 因 Iteration-local 与
  Gate-candidate evidence 的分层尚未复核，保持 `under_review`。
- ADR-0009 接受业务候选 `candidate_sha` 与资产后继 `evidence_head_sha` 双 SHA 模型，
  但本轮不实现其 phase cache 或 runner 工装。
- Gate closure 的受控资产集合前向增加根状态文档，并由 `verify-fast` 检查生命周期
  front matter 与 `PROJECT_STATE.yaml` 一致。
- 已定位的 `exit=2` 不再允许 `operator_adjudicated_pass`；generic transport error
  恢复为正常阻塞错误。
- 过程缺陷记录在 [process badcase namespace](badcases/README.md)，不混入未来产品
  incident、Agent trajectory 或 locked Eval case 数据。

### 新发现的状态漂移

复盘时还发现 README、AGENTS 和 PHASES 未随 G01 closure 更新，以及 G02 handoff
占位标题与权威总规划冲突。前者由生命周期一致性检查和新的 closure 资产集合修正；
后者前向纠正为“Fault Laboratory and Baselines”，但没有借此启动 G02 Master Plan。
