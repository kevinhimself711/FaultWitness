# FaultWitness Threat Model v0.1

## 范围和方法

本初版覆盖从身份入口、Agent、检索、调度、Sandbox、Action Executor 到 Eval/Data 的信任边界，并用 STRIDE 加 Agent 特有威胁检查。它定义必须阻断的路径和后续 Gate 验证责任，不声称系统已经部署或通过渗透测试。

## 关键资产

- Tenant 身份、角色、环境授权和 delegated credentials。
- Incident、Task、Checkpoint、ActionTransaction 及不可变审计链。
- Action digest、ApprovalGrant、idempotency token 和 postcondition evidence。
- 文档、memory、EvidenceRef、Trace、Artifact、Dataset 和模型版本。
- Locked Ground Truth、judge rubric、hidden test 和训练 split lineage。
- SUT 写入口、Sandbox host boundary 和网络策略。

## 对手与假设

- 恶意或被入侵的租户用户试图越权读取、审批或执行。
- 文档、告警、工具返回或 SUT 数据包含 prompt injection 和伪造指令。
- 模型输出错误、恶意或不稳定，不能作为身份、策略或执行授权。
- Worker、publisher、网络和外部依赖会 crash、超时、重复或丢失响应。
- 普通开发者可能误接触 locked data 或 secret；环境管理员是受审计的高权限主体。
- 不假设消息 exactly-once、外部 action 原子、模型诚实或第三方服务永远可用。

## 威胁与控制

| ID | STRIDE/Agent threat | Attack | Required control | Verification Gate |
| --- | --- | --- | --- | --- |
| TM-001 | Spoofing | 请求体伪造 tenant/user/role | OIDC signature/audience/expiry；TenantContext 只取 token | G01/G06 |
| TM-002 | Tampering | 审批后修改 action 参数或资源版本 | canonical digest、expected version、single-use grant、dispatch revalidation | G05 |
| TM-003 | Repudiation | 否认审批或执行 | append-only actor/time/scope/version/result/compensation audit | G05/G06 |
| TM-004 | Information disclosure | 跨租户检索、artifact 或 trace 泄漏 | RLS、召回前 ACL、tenant prefix、query policy、canary tests | G04/G06 |
| TM-005 | Denial of service | Agent loop、队列、工具或模型耗尽资源 | budget、quota、deadline、backpressure、circuit breaker、bounded retry | G03/G06/G08 |
| TM-006 | Elevation of privilege | Agent 直连 shell、Kubernetes 或 SUT write | Tool/Action 分离、sole executor、typed adapter、network deny | G01/G05/G06 |
| TM-007 | Prompt injection | 检索或工具结果要求泄露 secret/修改 policy | untrusted-data envelope、policy outside prompt、tool allowlist、injection eval | G04/G07 |
| TM-008 | Confused deputy | 低权限用户借高权限 Worker/Executor 操作别的环境 | end-to-end tenant/scope propagation、delegated identity、OPA recheck | G05/G06 |
| TM-009 | Replay/duplicate | 重放 approval、Command、Event 或 external action | idempotency scope、event dedupe、expiry、nonce、resource precondition | G01/G05 |
| TM-010 | Stale worker | lease 丢失后旧 Worker 提交 checkpoint/action | monotonic fencing token checked at every commit/dispatch | G01/G06 |
| TM-011 | Uncertain side effect | action 已执行但响应丢失后自动重试 | `UNCERTAIN`、reconciliation、manual deadline、no blind retry | G05 |
| TM-012 | Sandbox escape | 生成代码读 host secret 或未授权网络 | gVisor/Kata、ephemeral identity、seccomp、quota、network allowlist | G06 |
| TM-013 | Data poisoning | failed/duplicate/sensitive episode 写入 memory 或 training | write gate、provenance、dedupe、PII/secret scan、human policy | G04/G09 |
| TM-014 | Evaluation leakage | Ground Truth 进入 Prompt、retrieval、memory 或 training | sealed identity/network/store、split lineage checks、canaries | G02/G07/G09 |
| TM-015 | Observability leakage | Trace 保存 secret、PII 或 private chain-of-thought | schema allowlist、redaction、canary scan、structured public rationale only | G01/G10 |
| TM-016 | Dependency fail-open | OPA/Keycloak/LangSmith 不可用时默认允许 | explicit fail-closed write policy and degraded read-only state | G01/G05 |

## 零容忍安全不变量

- 未授权写、R2 审批绕过、digest 篡改接受、重复外部副作用、跨租户泄漏、Ground Truth 泄漏和 Sandbox escape 目标均为 0。
- `UNCERTAIN` 不得存在自动重复路径；Action Executor 以外不得存在 SUT write path。
- private chain-of-thought 不采集；可观测性只保存结构化输入、输出、公开理由、证据引用、决策与版本。
- 安全控制或必需审计依赖缺失时，高风险行为 fail-closed，不允许以“降级体验”豁免。

## Residual risk 与后续验证

G00 只建立设计与检查资产。G01 验证 contract、身份和 Trace；G04 验证 injection/RAG/memory；G05 验证审批和 action transaction；G06 验证租户、lease、Sandbox 与负载；G07/G09 验证 Eval/Training leakage；G10 进行发布前完整审计。每个实证失败都进入 Badcase/Claim，不用更新本文件掩盖失败。

## 关联资产

- [Deployment and Trust Boundaries](../architecture/DEPLOYMENT_AND_TRUST_BOUNDARIES.md)
- [Data and Control Flow](../architecture/DATA_AND_CONTROL_FLOW.md)
- [Architecture source of truth](../architecture/ARCHITECTURE.yaml)
