# I-0014 ModelGateway Runbook

## 1. 边界与事实

ModelGateway 是 Qwen、DeepSeek、GLM 三个模型族的统一类型边界。G01 的三个模型族都通过同一个百炼上游；`NewAPI` 仅验证 OpenAI-compatible wire contract，不构成 live redundancy。此组件不实现 Agent 推理、诊断质量评测、Tool 执行或 provider 级容灾。

固定能力目录位于 `config/models/catalog.yaml`。目录同时固定 `catalog_version`、`route_policy.version`、精确模型 ID、能力和请求覆盖参数。模型目录变更必须作为新版本提交并重新运行 EVAL-G01-008，不得在运行时静默使用 `latest`。

当前北京地域使用百炼 OpenAI-compatible Chat Completions endpoint。生产迁移到 workspace-dedicated domain 时必须保持 API key 与地域一致，并把 endpoint 作为仓库外配置；不得将 workspace ID 或 key 写入公开资产。

## 2. 调用语义

`ModelRequest` 通过以下字段选择能力：

- 普通 `complete`：无 schema、无 tools、`stream=false`。
- `structured`：提供 `target_json_schema`；上游使用 JSON mode，返回值再次通过 Draft 2020-12 schema 严格验证。
- `forced_tool`：提供 OpenAI function schema；请求固定 `tool_choice=required`，工具名和 arguments 再次本地校验。
- `stream`：`stream=true`，要求 `stream_options.include_usage=true`；按 sequence 重建 content/tool-call delta。

所有成功或失败事件仅记录 request ID、模型族、channel、精确 snapshot、route/catalog version、attempt/fallback/repair 计数、usage 或明确的 unavailable 原因、Trace ID 和类型化 outcome。原始 prompt/response、用户身份、凭据和私有推理不得进入日志、Trace 或公开证据。

## 3. Retry、repair 与 fallback

```text
REQUESTED
  -> ATTEMPTING
       -> SUCCEEDED
       -> RETRY_WAIT       (仅 transient、输出前、最多一次)
       -> REPAIR_WAIT      (仅 invalid structured output、最多一次)
       -> FALLBACK_WAIT    (仅输出前且允许切换)
       -> FAILED           (typed terminal failure)
       -> PARTIAL_FAILED   (出现首个可见 chunk 后的任何中断)
```

- `408/429/5xx`、timeout 和 transport failure 是 transient；单 route 最多重试一次。
- `401/403`、配置错误、策略拒绝和非法 tool arguments 不重试也不 fallback。
- 结构化输出只允许一次修复；修复仍失败才允许在首个输出之前转到下一个冻结 route。
- 任意可见 content 或 tool-call delta 出现后，禁止切换模型或 channel；中断必须返回 `PARTIAL_FAILED`，调用者只能显式发起新请求。
- 不声称 exactly-once 模型调用；每次 attempt 都有独立、可归属的 Trace。

## 4. 本地验证

```powershell
uv run pytest tests/models -q
uv run python -m faultwitness_dev verify-fast
uv run python -m faultwitness_dev eval-changed
```

离线 suite 使用 controlled `NewAPI` fake upstream 覆盖成功、usage 缺失、408、429、5xx、认证/配置 4xx、timeout、非法 JSON、非法 tool arguments、畸形 chunk 和中断 stream。它不读取 live secret。

## 5. Private live Eval

候选提交后，在保存百炼与 LangSmith key 的 owner 主机运行：

```powershell
$candidate = git rev-parse HEAD
uv run python -m faultwitness_dev eval-iteration I-0014 --candidate-sha $candidate
```

命令对 Qwen、DeepSeek、GLM 分别执行 complete、structured、forced tool、stream，每项重复三次，共 36 次。每次必须：

- 命中所请求模型族的 primary route，fallback 为 0；
- structured/tool schema 通过，stream 可确定性重建；
- usage 存在且归属于 exact route/model；
- 生成一个只含 allowlist metadata 的 LangSmith Trace；
- 不在 stdout、公开 Report 或 Git 中写入 prompt、response、key、服务器信息或可逆凭据指纹。

私有明细写入仓库外 `FaultWitness/evidence/I-0014/<candidate>.json`。公开 Report 只记录 candidate SHA、catalog/evidence digest、聚合计数和受控 LangSmith run ID。

## 6. 故障处理

- 百炼 `401/403`：停止；核对 key 地域与 endpoint，不自动换模型掩盖认证错误。
- 模型能力 `400`：停止；保留失败候选，更新目录前先依据官方能力文档确认，不降低测试。
- `429/5xx/timeout`：让 Gateway 执行冻结的一次 retry；仍失败时只允许输出前 fallback。
- LangSmith 失败：本 Eval 失败。不得用本地日志替代 required integration。
- stream 中断：返回 `PARTIAL_FAILED` 及已见 chunk 数，不拼接另一模型的内容。
- structured/tool validation 失败：不得把未校验字典交给下游。

## 7. 参考接口

- 百炼 OpenAI-compatible endpoint 与地域说明：<https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope>
- Function Calling 支持与 GLM `tool_stream`：<https://help.aliyun.com/en/model-studio/qwen-function-calling>
- 结构化输出与 thinking 约束：<https://help.aliyun.com/zh/model-studio/error-code/>
