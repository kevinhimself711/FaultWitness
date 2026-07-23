# G02 Eval Protocol Runbook

## Purpose

本 Runbook 说明 I-0016 冻结的 phase、cache、trial、resume 与双 SHA 操作协议。它不授权
部署、故障注入、live service 或模型调用。只有 I-0020 active 且 candidate-binding 资产完整
时，`eval-g02` 才能运行 Gate phase。

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
- `metric_fail` 需要新 candidate；`blocked` 需要解除外部阻塞。
- `scenario-matrix` 对同一 candidate/artifact/config/environment key 只执行一次。

## Candidate-binding asset

I-0020 在 Gate Eval 前产生 repository evidence path 下的 `candidate-binding.json`。它记录：

- `candidate_sha` 与 `evidence_head_sha`。
- runtime image、SUT image set、config、evaluator、dataset 和 environment digests。
- subject path 到 SHA-256 的映射。
- 13 个 upstream/Iteration manifest 路径。
- repository-external absolute journal root。
- zero waiver/open-evidence/backlog/DLQ/fallback counters。

`evidence_head_sha` 必须是 candidate 或仅修改 allowlisted evidence/status 路径的后代。Source、
fixture、threshold、workflow、dependency、deployment、dataset、config 或 runtime 变化不能作为
evidence-only 继承。

## Journals and recovery

Phase record 位于 journal root 的 `phases/<phase>.json`；trial 位于
`trials/<trial-id>.json`。写入使用同目录临时文件和 atomic replace。每条记录包含 status、
attempt/execution count、UTC 时间与 cache key。

发生传输故障时保留已经通过的 trial，只续跑失败 trial。不得删除 journal 以强制重跑；若
cache key 改变，保留旧 evidence 并建立新候选记录。

## Fail-closed diagnostics

- `phase handler is not implemented`：返回 owning Iteration，禁止在 I-0020 补写。
- `dependency lacks an exact-key pass`：先运行或恢复依赖，不可跳过。
- `cannot rerun on the same candidate`：metric failure 需要修复并生成新候选。
- candidate/subject/environment digest drift：停止，不得批量改写 manifest SHA。
- 环境兼容、rollout、凭据传递与外部工具尝试不限次数和累计时间；每次必须绑定候选与
  环境并记录归因。确定性根因须先修复，只有已分类的瞬时基础设施失败可原样重试。
