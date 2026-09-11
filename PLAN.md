# FaultWitness unblock plan

## 已完成项

- U1: 删除 CI 中依赖未追踪 G02 历史产物的冻结聚合测试，提交 `059c84b`。
- U7.1: 修正 `.gitignore` 的 docs/evals artifact 例外，提交 `fda9cd8`。
- U7.2: 原样补交 G02-046 的 6 个机器产物，提交 `d7979be`。
- U7.3: 记录数值来源不一致（见下方已知坑）。
- U7.4: `verify-fast` 新增 latest-release 追踪 artifact 检查，提交 `0e29742`。
- U2: 将文档/治理检查移至手动 `verify-docs`，CI 只保留快速检查，提交 `dc5b9ee`。
- U2.5: 语义测试迁出 `tests/governance/`，删除治理形态断言，提交 `78a47d6`。
- U3: 清理 6 个旧 G02 candidate worktree；目标旧分支在本地和远端均已不存在。
- U4: 原样归档 G00–G02 流程资产到 `docs/_archive/`，修复活动文档断链，提交序列 `8bdd0c9`–`5c7ba53`。
- U5: 重写根 `AGENTS.md` 并建立 scoped `.claude/rules/`，提交 `20a74b1`、`7e4f1a3`。
- U6: 将文档政策逐字写入 `AGENTS.md` 第 3 节，提交 `9041946`。

## 未完成项

无。本次任务不改 roadmap、Gate 划分、Gate Plan、G03 计划或 Gate 报告。

## 已知坑

G02-046 入库的机器产物记录的是 deterministic core_e2e=0.5、live 0.000。
这两个值经复盘确认分别源于规则表缺陷与标签格式 artifact。
而后续审计文档中引用的四个 baseline
(deterministic 0.8125 / no_rag 0.8750 / naive_react_single 0.8854 / naive_react 0.9167)
来自 metric-v3 的 r1–r9 运行,这批运行没有对应的 EVAL 目录,原始产物未入版本控制。
G03 重跑前必须先确认这四个数字的原始产物是否仍在 pci-2 上;
在还原之前,任何对外表述都应标注它们的来源运行与仪器版本。

- 2026-09-09：宿主默认 Codex runtime 的 pnpm/Node 版本为 11.19.0/v24.19.0，导致审计测试拒绝运行；用项目声明的 Node 22.14.0、pnpm 11.9.0 重跑后通过。
- 历史缺 artifact 的 EVAL 目录仍有 G00-001–006、G01-001–009、G02-021、G02-022；U7.4 只报告，不追溯补造。
- GOVERNANCE_V2.md 实质承载「先量后冻」那一课（含代价数字与三条硬性程序），
  但它不在任何自动加载通道里：AGENTS.md（60 行）只规定教训该写到哪、本身不承载教训；
  .claude/rules/ 三个文件都有 paths 门控。当前该课仅靠本地 CLAUDE.md 进入上下文。
  **在建立替代通道之前，不要从本地 CLAUDE.md 删除该节。**
- SBOM/CycloneDX 生成（run_repository_audit，依赖 pnpm）已退出 CI 与 pytest，
  仅存在于 verify-docs 的外部工具组，缺 pnpm 时静默跳过。
  G10 生产前审计需要它时，必须显式在有 pnpm 的环境跑一次并把产物入库，
  不能假设 CI 已经覆盖。
