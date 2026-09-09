# G00–G02 遗留治理 epoch

## 边界

以下资产是 G00–G02 的只读审计证据，不是治理 v2 的活跃输入：

- `governance/gates/G00.yaml` 至 `G02.yaml`；
- `governance/iterations/` 下全部 I/C/A record；
- `governance/policies/iteration-lifecycle-v1.yaml` 与 `work-item-lifecycle-v2.yaml`；
- `docs/roadmap/iterations/` 下全部历史工作项；
- `docs/evals/EVAL-G00-*`、`EVAL-G01-*`、`EVAL-G02-*` 及其 manifest/binding/evidence；
- 只服务上述 epoch 的 Iteration、Gate、manifest、validation 与 lifecycle schemas。

这些文件保留原路径和原内容，不逐份增加 `deprecated` 字段，不回写失败记录，不迁移 SHA，
也不重新生成 manifest。`governance/ASSETS.yaml`、`verify-fast`、CI 和未来模板不再加载它们。

## 复现

历史结论以对应 tag 为准：G02 使用 `gate/G02-v1`。需要重跑旧 runner 时 checkout 该 tag，按该
epoch 的 runbook 执行；不要在当前治理 v2 HEAD 恢复 I/C/A、candidate binding 或 evidence-head
状态机。

## 前向规则

G03 及以后只使用 Gate Plan 中的工作包、运行 journal 和 Gate/release 证据。历史编号可在复盘
中引用，但不能重新打开、续号或作为未来运行前置。
