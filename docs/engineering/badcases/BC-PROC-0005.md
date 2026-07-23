# BC-PROC-0005: All-or-Nothing Thirty-Six-Trial Model Matrix

Status: recorded; prevention accepted; tooling pending

## 现象

模型矩阵在内存中完成 3 个 family × 4 个 capability × 3 次 repetition 共 36 个 trial，
只有 36/36 全部通过后才写最终 evidence 文件。第 36 个 trial 的可归因传输失败会使前
35 个已完成 trial 在 resume 语义上不可用。

## 可独立复现

让前 35 个 live trial 成功且产生 trace，在第 36 个调用注入一次 transient transport
failure。当前 `run_model_eval` 在 matrix 完成前不会写 candidate evidence，下一次只能
从第一个 trial 重新开始。

## 根因

trial 没有稳定 ID、原子 journal 和 per-trial status；matrix report 同时承担运行日志与
最终汇总，缺少 resume contract。

## 当时的错误处置

把 36/36 的 Gate 阈值误解为必须全量重跑，而没有区分“最终必须全部通过”和“执行可
从失败 trial 继续”两个不同约束。

## 正确处置

为每个 trial 使用由 candidate、catalog digest、family、model、capability、repetition
和 evaluator version 派生的稳定 ID，调用结束后原子落盘。重启时跳过已通过且绑定未变
的 trial，只重跑 failed/pending；最终汇总仍严格要求 36/36。

## 防复发规则

- GR-11：外部 live matrix 必须逐 trial 持久化并可续跑。
- 单次 transport 抖动不得删除已完成 trial，但对应 trial 在成功前仍阻塞 Gate。
- unplanned fallback、模型或 evaluator 版本变化必须使受影响 trial 失效。
