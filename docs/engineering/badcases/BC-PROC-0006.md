# BC-PROC-0006: Gate Handoff Placeholder Drifts From Authoritative Roadmap

Status: current drift corrected; prevention recorded

## 现象

权威总规划将 G02 定义为“故障实验室与基线”，但 G01 closure 创建的 G02 placeholder 和
machine gate record 将其写成“Agent Orchestration and Diagnosis Core”，会把后续规划带
入实际属于 G03 的 Agent 纵切方向。

## 可独立复现

比较 `docs/blueprint/FINAL_PLAN.md` 的 G02 标题与 G02 plan/governance title，即可发现
scope identity 不一致；原有 schema 只检查引用存在，不检查权威 Gate identity。

## 根因

关闭资产只校验状态转换和文件集合，没有在 handoff 时按 source-of-truth 顺序复核下一
Gate 的标题与上位边界。占位内容由关闭阶段临时生成并被误当成正确 handoff。

## 当时的错误处置

G01 closure 接受并提交了错误标题；由于它不影响 G01 runtime evidence，问题直到复盘
读取权威总规划时才暴露。

## 正确处置

前向修正 G02 placeholder 和 machine gate title，只登记权威总规划已有的故障实验室与
baseline 边界，不借此编写 G02 Master Plan 或启动 Iteration。

## 防复发规则

- 每次 Gate handoff 必须先对照 authoritative plan，再生成 next-Gate placeholder。
- closure review 同时检查 lifecycle state 和 next-Gate identity，不能只检查路径存在。
- 发现漂移时停止规划，先按 source-of-truth 顺序解决，不静默选择任一版本。
