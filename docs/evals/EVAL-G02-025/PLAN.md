# EVAL-G02-025 Plan — LangSmith Access Probe Contract Corrective

## Purpose

复用 `tests/g02/test_g02_gate_collectors.py` 证明 operator-side LangSmith read probe 的三个变化
分支，并通过 `g02.langsmith_access_probe` 执行一次真实 credential seam proof。公开 artifact
只记录候选、环境、请求契约 digest、脱敏响应分类和 allow/deny 结果。

## Hard boundary

- 本 Eval 的 local N 是三个变化分支，real seam 是一次性 compatibility proof；两者都不是
  V-G02-009 Gate N=60。
- Gate L2、deployment、trace、canary、destructive、Bailian、模型调用、token 与费用均为 0。
- 401/403 或其他 credential-invalid 结果保持 blocking，不自动换 key、不转成 operator pass。
- 不新增 bespoke evaluator 或测试框架，不修改权限、N、阈值、Ground Truth 或 locked tests。
