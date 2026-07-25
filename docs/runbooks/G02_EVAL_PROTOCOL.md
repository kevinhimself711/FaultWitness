# G02 Eval Protocol Runbook

## Purpose

本 Runbook 说明 I-0016 冻结的 phase、cache、trial、resume 与双 SHA 操作协议。它不授权
部署、故障注入、live service 或模型调用。只有一个 `in_progress` 的 G02 standard
orchestration Iteration、其 `eval_id`、完整十四-phase PLAN 和 candidate-binding 资产彼此一致
时，`eval-g02` 才能运行 Gate phase。终态 Iteration 永远不能再次选择其 Eval 资产。

## Iteration Eval

在 I-0016 实现候选已提交、工作树干净后运行：

```text
uv run python -m faultwitness_dev eval-iteration I-0016 --candidate-sha <HEAD>
```

该命令只执行 V-G02-001 的五个确定性 contract cases，并证明 V-G02-002、003、016 的
负例被其 runner 拒绝。它写入
`docs/evals/EVAL-G02-001/artifacts/phase-contract.json`，不执行任何 L2 phase。

## Gate phase commands

```text
uv run python -m faultwitness_dev eval-g02 --candidate-sha <SHA>
uv run python -m faultwitness_dev eval-g02 --candidate-sha <SHA> --phase <PHASE>
uv run python -m faultwitness_dev eval-g02 --candidate-sha <SHA> --resume
uv run python -m faultwitness_dev eval-g02 --candidate-sha <SHA> --from-failed
uv run python -m faultwitness_dev eval-g02-close --candidate-sha <SHA> --evidence-head-sha <SHA>
```

- `--phase` 要求所有依赖已有 exact-key pass。
- 默认执行 DAG 并复用 exact-key pass。
- `--resume` 只继续 pending 或 `infra_failed`。
- `--from-failed` 从最早 pending 或 `infra_failed` phase 开始。
- `metric_fail` 或确定性 `blocked` 使当前 orchestration terminal；修复只能产生前向
  corrective Iteration 和新 candidate。只有 `infra_failed` 可在原 trial 续跑。
- `scenario-matrix` 对同一 candidate/artifact/config/environment key 只执行一次。

## Candidate-binding asset

当前 standard orchestration Iteration 在 Gate Eval 前产生其 `eval_id` 对应目录下的
`candidate-binding.json`。I-0033 对应 EVAL-G02-018；I-0020/EVAL-G02-005、
I-0023/EVAL-G02-008、I-0025/EVAL-G02-010 与后续 012/014/016 是不可变失败历史。
binding 记录：

- `candidate_sha` 与 `evidence_head_sha`。
- runtime image、SUT image set、config、evaluator、dataset 和 environment digests。
- subject path 到 SHA-256 的映射。
- 13 个 upstream/Iteration manifest 路径。
- 同时含 `eval_id` 与完整 `candidate_sha` 路径段的 repository-external absolute journal
  root；不同 Eval 或 candidate 绝不共用或覆盖 journal。
- zero waiver/open-evidence/backlog/DLQ/fallback counters。

EVAL-G02-018 binding 不得含 `phase_inputs`。`isolation-access-matrix`、
`trace-six-stage-matrix` 与 `all-surface-canary` 必须由 handler 直接调用 I-0024 collector；
任何操作员预制 matrix 都会在 phase 启动前被拒绝。

`evidence_head_sha` 必须是 candidate 或仅修改 allowlisted evidence/status 路径的后代。Source、
fixture、threshold、workflow、dependency、deployment、dataset、config 或 runtime 变化不能作为
evidence-only 继承。

## Bounded and byte-exact privileged script transport

EVAL-G02-010 证明 privileged probe program/request 不能嵌入 Windows child-process command
line；EVAL-G02-012 又证明 Windows text mode 会在 stdin 边界把 LF 改为 CRLF。I-0028 后的
冻结协议是：所有 stdin 先显式 UTF-8 encode，以 binary subprocess mode 传输，再显式 UTF-8
decode stdout/stderr。脚本 bytes 通过第一条 SSH session 上传至权限受限的远端临时文件；
第二条 SSH session 只用固定长度命令通过 sudo 执行该文件，stdin 只承载 credential；最后
以固定长度命令清理。脚本、credential、Secret/PII canary 均不得进入 process argument。

mock runner 只用于失败注入与 channel/cleanup 断言；跨平台 byte-integrity 必须由受影响平台
上的真实 child process 比较收到的 bytes。upload、execute 或 cleanup 的确定性失败保持
blocking；协议不增加 preset wall-clock timeout，也不改变任何 Gate N、阈值或失败语义。

## Remote interpreter compatibility

EVAL-G02-014 证明 current-version local import 不能替代目标 interpreter 证明。所有上传到
私有 host 或 sealed runtime 的 Python runner，必须在 owning Iteration 内以目标实际 major/minor
版本执行 import 与最小 runtime path。I-0030 对 `gate_probe.py` 的冻结目标是 Python 3.8；
syntax-only parse、mock import 或 Python 3.11+ 执行均不能单独证明 compatibility。
冻结实现以 `timezone.utc` 保持原 UTC-aware 语义；Iteration Eval 使用 managed Python 3.8
在隔离、无项目依赖环境中实际加载 probe，并执行 `datetime.now(UTC).isoformat()`。该证明只含
import 与 timestamp 两个本地 deterministic cases，不连接私有服务器，也不执行任何 Gate L2。

## Journals and recovery

Phase record 位于 journal root 的 `phases/<phase>.json`；trial 位于
`trials/<trial-id>.json`。写入使用同目录临时文件和 atomic replace。每条记录包含 status、
attempt/execution count、UTC 时间与 cache key。

60-cell access matrix 逐 cell 写入；六阶段 trace 与 22-surface canary 分别先写 collection
record，再逐 stage/surface 写入。发生传输故障时保留已经通过的 unit，只续跑失败或待运行
unit。`metric_fail`/`blocked` unit 在同一 candidate 上不可重试。不得删除 journal 以强制
重跑；若 cache key 改变，保留旧 evidence，并在新 Eval/candidate journal root 建立记录。

## Revision-identity guardrail (2026-07-24)

- `--candidate-sha` is the explicit frozen business candidate. The command must not replace it with
  current HEAD merely because an evidence or governance commit is newer.
- A Gate runner may execute at the candidate or a validated evidence-only descendant. For the
  descendant case it proves ancestry, the full changed-path allowlist, and every bound subject
  digest; HEAD mismatch alone is neither deployment drift nor a reason to rerun a phase.
- `candidate-binding.json` records the execution checkpoint that already existed before the runner
  produced it. It is not required to contain the SHA of the later commit that stores the file. That
  commit is verified through ancestry/tag, so the protocol has no SHA self-reference.
- A runner defect discovered after an Iteration closed creates a new forward corrective Iteration.
  Do not reactivate a completed Iteration or move `PROJECT_STATE.yaml` backward.
- A deterministic implementation, policy, zero-tolerance, cleanup, metric, quality, performance,
  reconciliation, or close-readiness failure makes the current orchestration Iteration terminal.
  Correction uses a higher-numbered corrective Iteration, and full Gate orchestration resumes only
  through a higher-numbered replacement standard Iteration.
- EVAL-G02-008 proved that a validator consuming operator-precomputed phase input is not a complete
  L2 runner. The owning forward corrective must implement candidate-bound provisioning and
  collection before a replacement orchestration starts; the final Gate Iteration never fabricates
  the missing input.
- A classified transient infrastructure or transport failure remains in the same phase/trial and
  resumes only pending or `infra_failed` work; it does not create a corrective Iteration.
- These rules change only provenance and orchestration. All frozen samples, thresholds, locked-test
  and Ground Truth isolation, health windows, token/cost ceilings, and failure semantics remain
  unchanged.

## Fail-closed diagnostics

- `phase handler is not implemented`：终止当前 orchestration，创建前向 corrective Iteration；
  禁止在任何 Gate orchestration Iteration 现场补写。
- `dependency lacks an exact-key pass`：先运行或恢复依赖，不可跳过。
- `cannot rerun on the same candidate`：metric failure 需要修复并生成新候选。
- candidate/subject/environment digest drift：停止，不得批量改写 manifest SHA。
- 环境兼容、rollout、凭据传递与外部工具尝试不限次数和累计时间；每次必须绑定候选与
  环境并记录归因。确定性根因须先修复，只有已分类的瞬时基础设施失败可原样重试。
