# 治理 v2 终局验证报告

## 裁决

**治理轻量化完成。** P0–P7 全部通过，活跃可达性审计的“活跃冗余”为 0；应用、Infra 与
算法/Eval 三类工程证明均通过。G03 保持 `not_started`，本轮没有调用模型、降低指标或改写任何
G02 冻结审计资产。

完成不等于删除历史。G00–G02 的 Gate/Iteration/Eval/CLAIMS 与 lifecycle schema 作为只读
legacy epoch 保留，但已退出 CLI、CI、active schema registry、模板、状态源和当前 import graph。

## 证明总表

| ID | 状态 | 可复核结果 |
|---|---|---|
| P0 历史成本 | Pass | 174 commits 互斥分类为 semantic 57、evidence-only 38、lifecycle/binding 54、policy/docs 22、other 3。 |
| P1 同 Gate A/B | Pass | 转折后 5 个连续修复只改现有 runner/test，`+540/-5`，无 lifecycle/binding/状态镜像。 |
| P2 活跃可达性 | Pass | CLI、Make/shim、CI、registry、模板、runbook、CLI import closure 与 pytest imports 无活跃旧治理。 |
| P3 192-trial resume | Pass | counting adapter 调用 1 次；191 个已通过 artifact digest 不变；32 clusters、B=2,000 aggregate 复现。 |
| P4 语义失效 | Pass | 313-unit DAG 由真实 runner 按具名 checkpoint 精确执行；未受影响 artifact digest 不变。 |
| P5 三条 debug campaign | Pass | 应用、Infra、Eval 均完成失败复现、单根因修复、targeted replay，无人工 pass 或新治理框架。 |
| P6 私有 K3s | Pass | exit-7 失败保存后只重建失败 Pod；Ready/log 匹配；namespace cleanup readback `NotFound`。 |
| P7 不变性/ruleset | Pass | G02 protected diff 为空；远端 ruleset 仅 deletion/non-fast-forward；模型/授权计数为 0。 |

## P0 与 P1：历史对照

一次性脚本：`tools/proofs/governance_v2_history.py`。它不进入 pytest 或 `verify-fast`，固定使用
`gate/G01-v1..gate/G02-v1^{}`，并按以下互斥顺序分类：lifecycle/binding → evidence-only →
other → semantic path → policy/docs。

| 历史事实 | 结果 |
|---|---:|
| G02 commits | 174 |
| semantic / evidence-only / lifecycle-binding / policy-docs / other | 57 / 38 / 54 / 22 / 3 |
| 治理/状态意图 commits（不含 Master Plan） | 93 |
| 触碰 `src/`/`tests/` 的 commits | 55 |
| 未触碰实现 commits 的 file touches / 总 touches | 1,111 / 1,616 |
| access-58 runtime / 完整 lifecycle | `+12/-7`；7 commits、59 touches、+1,593 lines |
| I-0034 | 5 commits、49 touches；实际 fix 只触碰 4 files |
| C-G02-012 | real seam 27.258932s；fix 至 close 21,935s；close commit 16 files、+362 lines |

旧的 55/57 差异已消除：55 只统计 `src/`/`tests/`，57 还包括两个只改变真实运行配置的 semantic
commit（`a66a6d1`、`81ae5ec`）。

自然 A/B 范围 `ceb82e3..e419e07` 恰有 5 个提交；所有 subject 都是 `fix(g02)`，diff 仅包含
`src/faultwitness_dev/g02_lab.py` 与 `tests/g02/test_g02_lab.py`，合计 `+540/-5`。之后 G02 在没有
新增 I/C/A、binding 或状态镜像的情况下完成全部指标并关闭。

## P2：旧治理不可达

机器审计位于 `tests/governance/test_governance_v2.py`，覆盖：

- CLI parser 与本地 AST import closure；
- 所有 pytest import；
- Makefile、Windows shim、Ubuntu/Windows advisory CI；
- `governance/ASSETS.yaml`、当前模板、runbook、AGENTS、README、PHASES 与 PROJECT_STATE；
- `verify_fast()` 的真实命令编排。

迁移结果：

- 删除 `evals.py`、`g01_eval.py`、`g02_eval.py`、`model_eval.py`、`changes.py` 及 lifecycle tests；
- CLI 不再暴露 G00/G01/G02 Eval、closure、I/C/A、binding 或历史 recovery matrix；
- 模板只剩 ADR 与 Requirement；CLAIMS 退出 registry 和 cross-reference；
- `PROJECT_STATE.yaml` 是唯一机器状态源；
- 本迁移完成时，`verify-fast` 只调用 ruff、pytest、Markdown、active schemas/contracts、
  UTF-8/link 与 diff；2026-07-28 的安全修正
  [AMD-0006](../blueprint/AMENDMENTS/AMD-0006.md) 在不恢复生命周期的前提下接回本地
  repository publication audit；
- 通用 deploy/inspect/smoke 不要求 `--candidate-sha`、clean tree、HEAD equality 或 binding ConfigMap；
- provenance 计算只在需要它的命令分支执行；publication audit 的 lock/pin/SBOM 内容哈希属于
  安全检查，不重新引入 HEAD binding 或全局 evaluator cache。

扫描到的旧词汇必须且只能归类为：

1. `historical/tag narrative`：说明已经退出的 G00–G02 协议；
2. `necessary runtime provenance`：冻结 `TraceEnvelope.candidate_sha` 及其 DB/export 链；
3. `active redundancy`：必须为空。

最终第三类为空。`VersionBundle` 与 `EvalResult` 已前向改为 `producer_sha`；活跃 OpenAPI 中的
`I-0012` 路径泄漏也已删除。

## P3：真实 192-trial resume

测试复制冻结的 192 个 live trial 到临时 `TrialJournal`，把词典序第一个 trial 标为
`infra_failed`，随后由真实 `ExperimentRunner` 续跑：

- deterministic counting adapter 调用：1；
- reused trials：191；
- 只有失败 trial 的 `execution_attempt` 增加；
- 其余 191 个 `artifact_digest` 完全不变；
- 再现 32 `case_id` clusters、2,000 bootstrap resamples 与冻结 aggregate；
- 模型调用、tokens、费用：0。

这不是手工把记录补回去；cache key、resume、handler dispatch 与 journal 写入全部经过现行 runner。

## P4：313-unit 精确失效

runner 首先真实执行 60 access、6 trace、22 canary、32 scenario、192 baseline 与 1 aggregate，
随后逐一改变 checkpoint。第二轮的执行数为：

| 变化 | 执行数与范围 | 复用范围 |
|---|---|---|
| docs/REPORT/状态或 producer SHA | 0 | 313 全部 |
| `identity_and_storage` | 60 access | 其余 253 |
| `trace_service` | 6 trace + 32 scenario + 192 baseline + aggregate = 231 | 60 access + 22 canary |
| `writer_surfaces` | 22 canary | 其余 291 |
| `sut` | 32 scenario + 192 baseline + aggregate = 225 | 60 access + 6 trace + 22 canary |
| `model_route` | 192 baseline + aggregate = 193 | 60 access + 6 trace + 22 canary + 32 scenario |
| `email-memory` | seeds 8/12/19 + 18 baseline + aggregate = 22 | 其余 291 |

所有未执行 unit 的 artifact digest 均与第一轮一致。测试没有直接调用 `affected_units()` 伪装
runner 行为。

## P5：三大工程素养

| 素养 | 受控失败 | targeted proof |
|---|---|---|
| 应用 | request builder 注入跨租户 header，得到 403 | 修复后同 trial 得到 201；body override 仍 400；同幂等 key/digest 冲突仍 409。 |
| Infra | LF 被故意转换为 CRLF，child process 出现 byte mismatch | 改回 UTF-8 bytes transport，只复验该 trial并 byte-exact。 |
| 算法/Eval | adapter 返回 malformed/unsupported claim | scorer fail closed；改变 adapter checkpoint 后只续跑该 trial，unsupported critical claim 为 0。 |

每条 campaign 都记录真实 executed/reused unit、`execution_attempt` 与 tracked-tree fingerprint；没有
创建 lifecycle、binding、状态镜像或一次性 harness。确定性 `metric_fail/blocked` 在 checkpoint
未变时禁止原样重试，也没有 operator pass 路径。

## P6：私有 K3s 副作用恢复

一次性脚本：`tools/proofs/governance_v2_k3s.py`。私有 journal 位于
`%APPDATA%/FaultWitness/evidence/platform/governance-v2-k3s/`，使用已有授权、现有 byte-safe
SSH/sudo transport 与 digest-pinned BusyBox：

`docker.io/rancher/mirrored-library-busybox@sha256:101b4afd76732482eff9b95cae5f94bcf295e521fbec4e01b69c5421f3f3f3e5`

真实记录：

1. execution 1 创建 `fw-governance-v2-proof` namespace 和 `side-effect-proof` Pod；
2. journal 逐项保存 namespace、Pod 与 terminal observation；
3. Pod 终态精确为 `Failed`、exit code 7，trial 终态为 `metric_fail`；
4. 只改变 `pod_command` checkpoint；execution 2 读回原 namespace 为 existing；
5. 仅删除并重建失败 Pod，观察 `Running`、`Ready=true` 与日志 `governance-v2-ready`；
6. 删除 namespace，readback 为 `not_found`；
7. 最终 `execution_attempt=2`、`record_version=11`，旧失败与 checkpoint 保留在同 trial history；
8. tracked-tree fingerprint 前后相同。

P6 没有 preset wall-clock timeout。SSH `ConnectTimeout=10` 是单次连接协议 deadline；Pod observer
只在 Ready、terminal state 或确定性 image/config failure 时结束。传输失败的语义是
`infra_failed` 并从同 journal checkpoint 续跑，不能裁定通过。

P6 source digest：`09e93c5ceefcbc25484f786df96a1bab35a97bd44af7e18aca49af6596a68cd5`。
授权请求、模型调用、tokens、费用均为 0。

## P7：冻结资产与远端治理

一次性脚本：`tools/proofs/governance_v2_invariance.py`。

- `gate/G02-v1^{}` 仍为 `4622470a6afebc77e71519ee905d461fb0e86635`；
- 全部 `docs/evals/EVAL-G02-*`、G02 Gate 文档、CLAIMS、`config/g02`、isolation policy、冻结
  deployment packages 与 G02 negative fixtures 的 tag diff 为空；
- 因此 G02 N、B=2,000、95% CI、质量/性能阈值、90/900 秒 oracle/稳定窗口、权限、locked test、
  Ground Truth、model route、费用和失败语义均未改变；
- GitHub ruleset `19545995` (`main-governance`) 为 active，target=branch，include default branch，
  rules 精确为 `deletion`、`non_fast_forward`；
- `.github/rulesets/main.json` 已删除，仓库内不存在第二 authority。

## 当前仓库验证

命令：`uv run python -m faultwitness_dev verify-fast`

- ruff、active schemas/contracts、UTF-8、local links：pass；
- pytest：334 passed；
- Markdown：260 files，0 issues；
- `git diff --check`：pass；
- Git history scan、Gate Eval、live service/model 调用：0。

一次预验证在最后一步发现 `audit.py` 与 `g02_lab.py` 各多一个 EOF 空行；语义阶段已全部通过，
删除两处空行后 `git diff --check` 通过。另一个预验证真实发现 CLAIMS 已退出 registry、但旧
cross-reference 仍硬索引它；该残余已删除并由 P2/全套测试复验。两者均按 direct-debug loop
处理，没有创建 corrective、Gate attempt、binding 或状态资产。

## 不变性与结束条件

- P0–P7 全部通过；
- 每个已知 G02 治理浪费项均在 retrospective 中映射到执行证明；
- 活跃冗余为 0；
- 未受影响 phase/trial 执行数为 0且 artifact digest 不变；
- 三大工程素养证明通过；
- G02 指标、tag 与审计资产不变；
- proof 不再把手工恢复称为 runner resume；
- G03 仍为 `not_started`。

因此终局二元结论为：**治理轻量化完成**。
