# G02 治理系统最终复盘

## 结论

G02 的实验标准没有过度：最终 14/14 phases、32/32 scenarios、192/192 live trials、60/6/22
安全与可观测性矩阵、32 clusters × 2,000 bootstrap 均完整通过，且没有 fallback、infra failure、
waiver 或 open evidence。过度的是围绕这些实验搭建的工作项、状态、SHA、binding、manifest 和
CI 机器治理。

最有说服力的 A/B 对照发生在同一个 Gate：在用户将目标改为“放弃不必要的 binding、schema，
压缩 debug 闭环”以后，后续五个修复都只触碰已有 runner 与已有 test，按失败 seed 续跑；直到
Gate 关闭，节奏保持稳定，最终严谨性没有下降。这证明重治理不是质量前提，而是成本放大器。

终局验证现已由 P0–P7 全部通过收口。活跃可达性审计中的“活跃冗余”为 0，故本轮可以宣布：
**治理轻量化完成**。这里的“完成”指 v2 热路径与迁移完成，不表示删除 G00–G02 的只读历史。

## 量化全景

| 项目 | 原计划/实际 |
|---|---:|
| Master Plan Iterations | 5 |
| Master Plan 预计总时长 | 17h33m |
| 实际治理 record / Eval directory | 46 / 46 |
| G02 期间 commits | 174 |
| 互斥分类中的 semantic commits | 57 |
| 触碰 `src/` 或 `tests/` 的 commits | 55 |
| 未触碰 `src/` 或 `tests/` 的 commits | 119 |
| 治理/状态意图 commits（不含 Master Plan） | 93 |
| 非实现 commits 的 file touches | 1,111 / 1,616 |
| access-58 runtime diff | +12 / -7 lines |
| access-58 完整 lifecycle | 7 commits、59 touches、+1,593 lines |
| I-0034 单个 corrective | 5 commits、49 touches |
| G02 关闭期 `verify-fast` | 400 tests、255 Markdown、约 31s |
| v2 终局验证 | 334 tests、260 Markdown；pytest 68.97s |

CI 计算本身很便宜。昂贵的是一次小改触发 plan → activate → candidate → evidence → close，
随后状态镜像产生新 SHA，新 SHA 又触发 binding/cache/manifest 同步，最终让远程实验等待治理。

旧统计“55 个实现提交”只计算 `src/`/`tests/` 路径；P0 的互斥分类还把两个只修改真实运行
`config/g02/lab.yaml` 的提交计为 semantic，因此正确分类数是 57。两种数字测量对象不同，不再混用。

## Master Plan 的责任

Master Plan 正确冻结了安全、隔离、质量、性能和统计指标；没有证据支持降低 Gate N。它的错误
主要有四类：

1. 把完整 live matrix 正确归到 L2，却把真实 client、平台、凭据、interpreter、image 和
   protocol 的最小 seam proof 也推到 Gate，导致 Gate 成为首次真实集成。
2. 把 runner 名、fixture 和 artifact 写进计划，却没有证明 runner 在目标环境能部署、诊断和
   归因。
3. 把 candidate/evidence SHA、phase cache、Iteration closure 和最终 Gate orchestration 绑成
   一套状态机，局部失败无法局部恢复。
4. 对最终审计的“冻结编排”理解过死：已有 runner 的小修也被迫返回新 corrective/attempt，
   使 debug 的固定治理成本远超实现成本。

因此问题不是“实验太严格”，而是 work decomposition 与 evidence architecture 设计不合理。

## 关键时间线

### 早期：纸面完整，真实 seam 后置

五个计划 Iteration 交付了 DSL、隔离、baseline 和 Eval 协议，但真实 Windows → SSH → Linux、
MinIO/K3s、trace relay、ambient workload 等 seam 没有在 owning work 内完整冒烟。Gate Eval 才
第一次暴露环境/协议 bug。每次暴露后又创建新的 I/C/A 与 Eval 资产，使第一次集成的自然 debug
成本被生命周期倍增。

### corrective 命名与重开问题

已关闭 Iteration 被重新检查或等价重开的根因不是指标，而是 runner-readiness、preflight、
reconciliation、close-readiness 被当成独立生命周期。后来引入 C/A namespace 试图解决“不要
重开”，却增加了第二套命名与 machine policy。它修正了审计语义，却没有降低固定成本；一个
失败仍可能生成多个 C/A。

正确抽象不是更多 work-item 类型，而是同一实验 journal 的失败闭环。已关闭计划工作不重开；
小缺陷不另建生命周期；大范围新 scope 才修订 Gate Plan。

### access-58：轻 bug 被治理放大

access matrix 第 58 项多次失败。runtime 修复只有十几行，但 candidate/binding、计划、状态、
evidence 和复验登记扩张为 7 commits、59 touches、1,593 新增行。schema 能确认字段存在，却不能
说明真实目标环境中的访问语义；SHA 能确认来源，却不能替代 access operation。这是“证明
provenance 的工具反客为主”的典型。

### C-G02-010：全局失效与 journal 误导

清理污染的 `fw-sut` 并降低 ambient load 后，scenario 从 seed 1 复验是合理的，因为 SUT 与输入
语义改变；22-surface canary 也受重建影响。但 60-cell access 和独立 trace 被全局 candidate/
environment key 一刀切失效，没有新增信息。

同一 seed 的 `running` 与 `metric_fail` 两次写入被记成 `attempt: 1/2`，让一次执行看起来像两次。
schema 验证了整数形状，却没有验证字段语义。v2 分离 `execution_attempt` 与 `record_version`。

### C-G02-012：六小时空转的直接证据

- 修复 commit `86a459c`：2026-07-25 20:07:48（本地记录）。
- 真实 trace seam：20:11:48–20:12:16，27 秒通过。
- close/activate：约 2026-07-26 02:13:23 才完成。
- 中间约六小时没有新的 phase、scenario、baseline trial 或模型调用。
- 同步 commit 触碰 16 个文件并增加 362 行。
- 随后又为继承旧 access 与修改 candidate label 编写约 9.9 KB 一次性 adapter；实际执行 16 秒，
  deployment=0、access execution=0、binding update=1。

必要工作只有一次 targeted test、一次 real seam、一次健康检查和便宜 preflight。其余是状态仪式、
provenance mutation 和临时兼容层。

## 八次打断如何逐步定位问题

1. 用户首先区分 CI 计算与 ruleset/SHA 机器治理，指出 30 秒检查不应制造数小时工作链。
2. binding 死锁暴露矛盾：必须先改状态才能运行，但状态变化又被视为 candidate 污染。
3. C-G02-010 让全局重跑和 `attempt: 2` 误导变得可见，促成 phase impact 与 journal 语义拆分。
4. 用户追问 schema/candidate 是否必要，明确它们不是 `fw-sut` 污染根因，而是成本放大器。
5. C-G02-012 后六小时无实验，证明经验日志“记了但未控制下一步”。
6. 用户要求立即执行，trace 真正启动；这证明治理并非 runner 的技术前置。
7. 转折指令明确放弃不必要 binding/schema、压缩 debug 闭环，覆盖了旧 closure-freeze 目标。
8. 旧 Goal 删除并以新目标重建后，工具层不再把过时冻结措辞拉回编排，节奏持续稳定。

核心教训：用户多次授权和口头纠偏并非不清楚；旧 AGENTS、Goal 与 machine checks 仍把“服从
冻结治理”设成局部最优，执行器缺乏主动删除无信息规则的明确 stop condition。v2 把“两次连续
治理动作无 runtime observation”定义为死锁，要求删除 blocker。

## 转折前后 A/B

| 维度 | 转折前 | 转折后 |
|---|---|---|
| defect 身份 | 新 C + 新 A + Eval 目录 | 同一失败 journal 中的一个 root cause |
| 变更 | runner/test + 多份状态/计划/报告 | 已有 runner + 已有 test |
| 验证 | 全局 SHA 失效、重复矩阵 | targeted test、real seam、受影响 seeds |
| pass seed | 经常被候选变化作废 | 独立输入/checkpoint 未变即保留 |
| 文档 | 每轮同步 | Gate 关闭汇总一次 |
| 运行节奏 | 数十秒实验夹数小时治理 | 连续 debug → replay → resume |
| 最终严谨性 | 尚未完成 | 14/14、32/32、192/192、60/6/22、B=2,000 |

转折后五次修复均只修改 runner 与现有 test，先复现并修根因，再只 replay 失败 seed 及真实下游；
没有重跑独立 60/6/22，也没有新 lifecycle。这个节奏稳定到 Gate 关闭，说明它不是临时取巧。

## 系统性根因

1. **状态镜像过多**：AGENTS、README、PHASES、PROJECT_STATE、Gate/Iteration/Eval 同时表达状态。
2. **身份职责混淆**：producer provenance、release identity、governance HEAD 被当成同一正确性。
3. **cache key 过粗**：global candidate/evaluator/environment 变化使无关 phase 失效。
4. **schema 形状替代语义**：字段齐全不等于真实 seam、clean environment 或 attempt 语义正确。
5. **固定 lifecycle 成本**：小修复也承担 planning/activation/evidence/closure。
6. **历史审计进入热路径**：每次 PR 扫描全历史 transition，却不增加当前实验信息。
7. **Goal 与规则优先级错误**：closure-freeze 被解释为执行旧流程，而非冻结指标、简化道路。
8. **经验无执行触发器**：日志已有 GOV-OBS-008/010/011，编排仍继续 binding adapter。
9. **首次真实集成过晚**：mock/schema 单测不能替代目标 interpreter、client 和 credential seam。
10. **副作用 checkpoint 太粗**：phase boolean 无法表达“部署已完成、relay 未完成”。

## 轻量治理 v2 的删除清单

彻底退出活跃路径：

- per-Iteration/corrective/Gate-attempt YAML 与 Eval placeholder；
- plan/activate/evidence/close commit 序列；
- candidate SHA、evidence SHA、governance HEAD 三套身份；
- HEAD 精确相等、ancestry changed-path allowlist、candidate-binding JSON；
- root documents 的 lifecycle front matter；
- `eval-changed`、历史 transition 扫描、manifest revision coupling；
- ruleset 的 PR/thread/strict-up-to-date/required-status 组合；
- candidate-wide cache 与 provenance ConfigMap mutation；
- 以 test count、文档数、commit 数代替工程质量。

保留：

- 一次 Gate Plan 与 L1/L2/L3 ownership；
- product/contracts/security schemas；
- pytest/ruff/Markdown/UTF-8/link/diff；
- Ubuntu/Windows advisory CI；
- named runtime checkpoints、trial journal、resume；
-真实 external seam；
- 一个 producer SHA 与一个 Gate/release SHA；
- image/config/data/model/locked/GT/environment/artifact digests；
- Gate Report 与 release manifest 各一次。

## 三大素养证明

治理 v2 不以“资产更多”证明素养，而以六个可执行 benchmark：

1. **应用：tenant identity override** 必须被拒绝，认证上下文仍是唯一租户来源。
2. **应用/Infra：idempotency digest conflict** 同 key 不同 payload 必须 fail closed。
3. **Infra：Windows/Linux byte transport** 子进程 stdin 必须 byte-exact，不依赖 shell quoting。
4. **Infra：private K3s disposable seam** 真实 namespace 创建、失败/修复、部署和 cleanup 可归因；
   public CI 只验证协议，不持有凭据。
5. **算法/Eval：malformed/unsupported claim** scorer 必须按冻结失败语义计分。
6. **算法/Eval：192-trial resume copy** 删除一个 trial 后只补一个，再复现 32 clusters、2,000
   bootstrap 的 CI；不调用模型。

另有四个治理回归：docs/status 不失效实验；`running → metric_fail` 保持一次 execution；SUT
checkpoint 不失效 access/独立 trace；active CLI 不再暴露 I/C/A、binding 或 `eval-changed`。

## P0–P7 终局实验

| ID | 结果 | 关键可证伪事实 |
|---|---|---|
| P0 | Pass | 174 commits 被互斥分为 semantic 57、evidence-only 38、lifecycle/binding 54、policy/docs 22、other 3；复现 access-58、I-0034 与 C-G02-012 时间线。 |
| P1 | Pass | `ceb82e3..e419e07` 恰为 5 个 semantic fix，只改 `g02_lab.py` 与原测试，合计 `+540/-5`，无生命周期资产。 |
| P2 | Pass | CLI、导入图、pytest imports、Make/shim、CI、schema registry、模板和 runbook 均已审计；旧引用只剩历史叙述与冻结 TraceEnvelope runtime provenance，活跃冗余为 0。 |
| P3 | Pass | 真实 `ExperimentRunner` 在 192-trial 副本中只执行被标为 `infra_failed` 的 1 个 trial；其余 191 artifact digest 不变，32 clusters 与 B=2,000 aggregate 完整复现，模型调用 0。 |
| P4 | Pass | 313 个 unit 由 runner 决定失效：docs/producer 变化执行 0；identity 60；trace 231；writer 22；SUT 225；model 193；email-memory 22。未受影响 artifact digest 全不变。 |
| P5 | Pass | 应用、Infra、Eval 三条 campaign 均走 `失败 → 单根因 → targeted fix → affected replay`，没有 I/C/A、binding、状态镜像或一次性 harness。 |
| P6 | Pass | 私有 K3s 同一 journal 保存 exit-7 失败，再只重建失败 Pod；观察 Ready 与固定日志，cleanup readback `NotFound`，授权请求和模型调用均为 0。 |
| P7 | Pass | G02 tag 与全部冻结 G02 evidence/config/权限/locked/GT 路径 diff 为空；远端 ruleset 只含 deletion 与 non-fast-forward。 |

P0 与 P6 是一次性 proof 脚本，不进入 `verify-fast`；P3–P5 是当前实验内核的确定性回归。这样既可
复核迁移，又不把历史扫描或私有 K3s 重新塞回日常 CI。

## G02 浪费项逐条闭环

| 历史浪费项 | v2 的删除或证明 |
|---|---|
| per-Iteration plan/activate/evidence/close | P0/P1/P2/P5；未来只有 Gate Plan、journal、一次 release。 |
| 已关闭 Iteration 重开 | 历史 lifecycle 退出活跃导入图；失败只在同 journal 前向修复。 |
| C/A 两套命名膨胀 | 模板、CLI、schema registry 不再生成或消费 I/C/A。 |
| candidate/evidence/governance 三 SHA | producer 仅作事实 provenance；release 只有一个 tag SHA。 |
| binding/allowlist/HEAD 死锁 | CLI 无 HEAD 等式、clean-tree gate 或 binding ConfigMap；P6 在 dirty tree 通过。 |
| `evaluated_revision` 自引用 | 历史 manifest 不再活跃；后继文档 commit 无 evidence 身份。 |
| global candidate/evaluator invalidation | P4 证明 producer/docs 单独变化执行 0。 |
| 无关 60/6/22/32 重跑 | P4 按 checkpoint 与依赖闭包精确执行。 |
| ADR 声明 inheritance、runner 未实现 | `ExperimentRunner` 真实驱动 313-unit 失效，而非只测辅助纯函数。 |
| 9.9 KB 一次性 inheritance adapter | P0 固化时间线；现行 runner 原生复用 pass 与 resume。 |
| journal 写入误增 `attempt` | `execution_attempt` 只在 `begin()` 递增，`record_version` 负责写入版本。 |
| compound phase boolean 丢副作用 | checkpoint 逐项记录 namespace、Pod、terminal observation、Ready、cleanup。 |
| terminal trial 丢最后 sample | 语义修复时旧终态和 checkpoint 进入同 trial `history`。 |
| AGENTS/README/PHASES/STATE 多源状态 | `PROJECT_STATE.yaml` 是唯一机器状态源，其余只作导航叙述。 |
| `verify-fast` 扫 lifecycle history | P2 对调用序列做机器断言；只运行当前 lint/test/schema/docs/diff。 |
| PR/thread/required-status ruleset 编排 | P7 readback 只有 deletion/non-fast-forward；跨平台 CI 为 advisory。 |
| preflight/readiness 失败后倒退生命周期 | P5 保持同 unit、同 journal，不创建新 work item。 |
| closure freeze 阻止已有 runner 小修 | P1 五个连续修复证明 direct-debug 节奏稳定到 G02 关闭。 |
| 经验日志记录后仍继续空转 | 两次连续治理动作无 runtime observation 被定义为 deadlock，必须删 blocker。 |
| 真实平台/凭据/interpreter seam 后置 | AGENTS 要求 Gate-scale 前在目标环境逐 seam 冒烟；P5/P6 给出实证。 |
| Ready/binding 替代 clean health | inspect/smoke 读取实际 workload image、annotation、健康与业务 observation。 |
| preset timeout/固定轮询次数 | 活跃实验/部署无墙钟强杀；只保留协议 deadline 与冻结 oracle 窗口。 |
| 已授权后重复请求授权 | AGENTS 固化一次授权语义；P6 授权请求计数 0。 |
| 旧 Goal/规则压过最新指令 | AGENTS 明确最新用户指令优先于过时 Goal/workflow，同时不降低安全/Eval。 |
| 一次传输失败丢弃 live matrix | P3 只续跑 1 个失败 trial，191 个 pass 原样继承。 |
| provenance 文档变化触发重跑 | P4 的 producer/docs 变化执行数为 0。 |
| Iteration ID 泄漏到活跃私有路径 | 新证据路径按 `platform` 等能力命名；P2 清除活跃契约中的 `I-0012`。 |
| CLAIMS/旧模板/runbook 继续同步 | CLAIMS 退出 registry/cross-reference；Gate/Claim/Iteration/Eval 模板已删除，G02 runbook 只指向 tag。 |
| 已定位根因仍可人工裁定通过 | runner 只接受正常 pass；P5/P6 的确定性失败必须修复 checkpoint 后复验。 |

## 仍保留但不是冗余的兼容面

- G00–G02 Gate/Iteration/Eval/CLAIMS 文件仍在当前树中作为只读 legacy evidence，也可由 tag 完整
  复现；它们不在 registry、CI、CLI、模板或状态机热路径。
- `TraceEnvelope.candidate_sha` 是已冻结并持久化的产品契约字段；其值现在装载 producer
  provenance。其他活跃 candidate 字段已前向改为 `producer_sha`。
- SSH connect、HTTP connect/read、模型 token/费用、90 秒故障 oracle 和 900 秒稳定窗口是协议或
  Eval 语义，不是编排强杀，因此保留。
- Git SHA 仍回答“哪份代码/镜像产生结果”，但不再决定无关 trial 是否失效。

上述项目均被 P2 分类为“历史/tag 叙述”或“必要 runtime provenance”；没有未分类项，也没有
“活跃冗余”。因此不再需要第三轮治理重构。

## 迁移策略与完成定义

不回写 61 个 iteration YAML、61 个 roadmap record 或 G00–G02 Eval 目录。它们形成不可变 legacy
epoch，并从 active registry、CI、template 与状态源退出。这既保留审计，也避免把治理重构变成
新的大型迁移项目。

治理 v2 完成条件均已满足：

- `PROJECT_STATE.yaml` 是唯一当前机器状态；
- AGENTS 与 v2 文档不含双 SHA、I/C/A 热路径或历史扫描要求；
- `verify-fast` 不读取 legacy epoch、Gate Eval、Git history 或 live 服务；
- remote ruleset 只剩 deletion 与 non-fast-forward；
- P0–P7、六项工程 benchmark 和全部治理回归通过；
- G03 仍为 `not_started`，没有借治理迁移实施任何 G03 scope；
- G02 tag、REPORT、PLAN、VALIDATIONS、manifest、CLAIMS、config 和原始 evidence 不变。

最终裁决：**治理轻量化完成**。未来若出现新 scope、指标或框架，走 Gate Plan amendment；普通
缺陷继续使用同一 journal 的 direct-debug loop，不恢复旧治理。
