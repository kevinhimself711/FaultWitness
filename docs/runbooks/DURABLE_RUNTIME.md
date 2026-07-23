# Durable Runtime Runbook

## 范围

I-0011 只部署 owner-isolated PostgreSQL state、idempotency、Outbox/Inbox/DLQ、lease 与 encrypted checkpoint 数据面，并使用现有 private-server Redis 作为 at-least-once event transport。它不声明 distributed exactly-once，也不执行外部动作。

## 部署

部署输入必须来自 clean、immutable candidate。命令不会读取或输出 Secret value；PostgreSQL 容器继续使用 `fw-postgres-env`，Redis 继续使用 `fw-redis-env`。

```powershell
$candidateSha = git rev-parse HEAD
uv run python -m faultwitness_dev deploy-runtime-schema --candidate-sha $candidateSha
uv run python -m faultwitness_dev inspect-runtime-schema --candidate-sha $candidateSha
```

Migration 以 transaction 和 `ON_ERROR_STOP` 执行，成功后用 `fw-runtime-candidate-binding` 绑定 candidate SHA 与 migration digest。重复执行必须幂等。

## 失败与恢复

- optimistic version mismatch：回滚整个 state/idempotency/Outbox transaction；调用方重新读取，不覆盖。
- duplicate command：相同 key/digest 返回原 event identity；相同 key、不同 digest fail closed。
- XADD 成功但 Outbox 未标记：允许再次发布；Inbox 以 `(tenant_id, consumer, event_id)` 吸收重复。
- consumer commit 后、XACK 前崩溃：`XAUTOCLAIM` 恢复 pending message，Inbox 判重后 ACK。
- incompatible/poison payload：不修改 owner state，写入 auditable DLQ 后 ACK。
- stale/expired fence：checkpoint transaction 在写入前锁定 lease 并拒绝；checkpoint 与 graph Outbox 同事务。
- checkpoint payload：仅支持 versioned JSON + AES-GCM；unknown version/key、AAD mismatch 与篡改全部 fail closed，不支持 pickle。

## 回滚

I-0011 migration 为 additive。应用回滚时停止 runtime writer，保留 owner state、Outbox、Inbox、DLQ 与 checkpoint 供审计；禁止在未导出和核对 pending record 前 drop schema。结构性回滚必须作为后续受控 migration 提交。
