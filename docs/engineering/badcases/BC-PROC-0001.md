# BC-PROC-0001: Fail-late Manifest Debt After Stability Window

Status: recorded; prevention accepted; tooling pending

## 现象

一个存在 stale 或 open Eval manifest 的候选仍会先执行恢复、900 秒稳定窗口、服务
检查、failure matrix 和 walkthrough，最后才返回 `upstream_eval_debt`。

## 可独立复现

在隔离 fixture 中令任一 EVAL-G01-001–008 manifest 的 `evaluated_revision` 不等于
候选 SHA，保持远程检查可调用，然后执行完整 private-server Gate Eval。当前调用顺序
会在昂贵工作完成后才检查该 manifest。

## 根因

确定性的 `_eval_manifest_debt` 被放在 Gate evaluator 尾部，没有 cheap preflight 与
expensive execution 的阶段边界。

## 当时的错误处置

继续运行完整 Eval，并把最终 pending 视为远程流程的一部分，而不是在调用服务器前
直接拒绝候选。

## 正确处置

先验证 manifest、candidate ancestry、binding contract、schema、publication boundary
和 required checks；任一失败立即停止，禁止启动 soak、恢复或付费 live trial。

## 防复发规则

- GR-05：所有确定性 preflight 必须早于昂贵阶段。
- 为调用顺序增加负面测试：stale manifest 时远程函数调用次数必须为 0。
- 未来 phase runner 必须把 preflight 结果作为其他 phase 的显式依赖。
