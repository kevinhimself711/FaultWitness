# BC-PROC-0002: Candidate SHA Cascade Invalidates Evidence

Status: recorded; ADR-0009 accepted; tooling pending

## 现象

业务候选通过后，修改 Eval fixture 或同步 manifest 会产生新 HEAD。所有要求
`evaluated_revision == HEAD` 的历史 Eval 随即过期，部署绑定、报告和关闭检查需要再次
重绑，新的 evidence commit 又继续改变 HEAD。

## 可独立复现

从一个所有 manifest 都绑定候选 A 的仓库开始，只修改允许的 evidence asset 并提交为
B。若关闭检查只接受 `candidate_sha == HEAD`，A 被拒绝；若把 manifest 全改成 B，运行
时 artifact 实际仍来自 A，证据语义变得不准确。

## 根因

一个 Git SHA 同时承担“业务与运行时身份”和“证据文档版本”两个不同职责，且没有
定义 asset-only descendant、artifact digest 和环境指纹的适用边界。

## 当时的错误处置

多次更新 manifest 和报告去追逐最新 HEAD，并在测试 fixture 修复后再次重绑定最终
候选。`2e82126` 只局部允许 evidence-only descendant，尚未建立完整模型。

## 正确处置

使用 ADR-0009：`candidate_sha` 永久指向行为和运行产物候选；`evidence_head_sha` 指向
只含允许资产的后继。任何行为、测试语义、阈值、workflow 或 runtime artifact 变化
都创建新 candidate；纯证据变化不使运行证据失效。

## 防复发规则

- GR-09：所有未来 Gate 采用双 SHA 证据模型。
- 证据记录 runtime image、Chart、配置 digest 与 environment fingerprint。
- ancestry 和 changed-path allowlist 必须 fail closed；不能用“看起来等价”人工替代。
