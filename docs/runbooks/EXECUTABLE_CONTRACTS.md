# Executable Contracts and Transition Kernel Runbook

## Purpose and boundary

本 Runbook 约束 I-0010 的确定性 contract compilation、严格 boundary model 和四 owner transition kernel。它不授权数据库写入、HTTP API、Agent graph 执行、工具调用或模型调用。

权威输入固定为 `docs/contracts` 下登记的九个 YAML/OpenAPI/AsyncAPI 文件。运行时只读取生成的 `contracts-v1.1.0.json` package resource；不得在生产路径动态解释 YAML guard 文本。

## Canonical workflow

```text
uv run python -m faultwitness_dev compile-contracts
uv run python -m faultwitness_dev check-contracts
uv run python -m faultwitness_dev verify-fast
uv run python -m faultwitness_dev eval-changed
uv run python -m faultwitness_dev eval-iteration I-0010 --candidate-sha <full-sha>
```

`compile-contracts` 只在权威输入被有意修改后运行。生成文件、源文件 digest、整体 artifact digest、契约版本和对应测试必须在同一 commit 中提交。`check-contracts` 是常规只读检查；生成结果缺失、手工编辑或 byte drift 必须失败。

## Runtime contracts

- `models.py` 提供 21 个 frozen core model 和 12 个 G01 support model；全部使用 strict Pydantic、`extra="forbid"`、typed IDs、UTC timestamp 和显式版本字段。
- Command、Event、Checkpoint、Model、Trace 和 Stream payload 递归拒绝 private chain-of-thought 字段。
- `TransitionKernel` 只接收完整确定性输入并返回无副作用 `TransitionDecision`。
- Incident、Runtime Task、Agent Graph 和 ActionTransaction 分别由四个固定 owner service view 管理，禁止跨 owner 调用。
- Guard 使用代码中显式注册的命名 predicate；未知、缺失或多余 predicate 均阻止启动。
- state version、fencing token、action digest 和 idempotency policy 在 decision 前验证；terminal state 不得继续转换。

## Failure handling

- Source/resource drift：重新审查权威 source 变更并生成资源，禁止直接编辑 JSON 消除失败。
- Registry mismatch：补齐或删除显式 Python predicate binding，禁止执行 YAML expression。
- Illegal transition acceptance：保留 mutation badcase，修复 kernel；不得删除 locked transition 或降低拒绝条件。
- Breaking contract：停止实施，提交 ADR、migration/replay analysis 和兼容性审查后再更新版本。

EVAL-G01-004 是 deterministic Eval，不产生 LangSmith Trace。公开证据只包含 candidate SHA、计数、source/artifact digest 和 aggregate mutation 结果，不包含 payload、tenant、credential 或 private reasoning。
