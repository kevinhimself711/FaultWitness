# I-0009 Platform Services Runbook

## 1. Purpose and boundary

本 Runbook 约束 I-0009 在 private server 上部署、检查和恢复 platform services 的操作。范围仅包括 PostgreSQL、Redis、Qdrant、MinIO、Keycloak、OPA、OpenTelemetry Collector、Prometheus、Loki、Tempo 和 Grafana，以及它们的 workload identity、持久化、resource bounds、backup/restore、私有访问和 supply-chain evidence。

本 Iteration 不创建 FaultWitness 业务表或 Agent trace，不调用模型，不开放 public ingress，也不声称完成 G06 的 PostgreSQL RLS、Qdrant ACL、MinIO tenant isolation 或规模认证。I-0008 遗留的 EVAL-G01-002 debt 仍独立阻塞 G01 closure；I-0009 不替它补证或修改阈值。

## 2. Public and private evidence boundary

允许进入公开仓库的证据：

- 完整 candidate Git SHA、公开 deployment asset digest 和 image digest；
- synthetic identity 名称、非敏感版本与 resource bound；
- 聚合的 readiness/restart timeline、allow/deny matrix 结果和 telemetry control-signal 计数；
- canonical PostgreSQL test dataset 的输入规范、restore digest 和精确相等结论；
- SBOM、license audit 和 provenance 的公开摘要。

必须保留在 repository 外的证据：

- kubeconfig、cluster/server locator、SSH material 和 private filesystem path；
- Kubernetes Secret、database/Redis/MinIO/Keycloak credentials、tokens 和 session；
- raw database dump、object bodies、IdP export、Grafana session 和 private dashboard URL；
- raw logs/traces/metrics 中的 tenant、host、network、container 或 credential material；
- 可逆 credential fingerprint、Secret value hash 或能关联私有环境的标识。

公开报告只能保存脱敏后的聚合结论和不可逆 artifact digest。执行前后都必须运行 publication/secret scan；失败原始证据留在 private evidence root，不复制到 Git。

## 3. Preconditions

开始 server mutation 前确认：

1. `PROJECT_STATE.yaml` 中仅 `I-0009` 为 active Iteration。
2. 使用 I-0007 建立的 accepted host pin、project SSH identity 和 repository 外 encrypted secret store。
3. I-0008 的 K3s service、Helm、namespaces、RuntimeClass 和 storage capability 可用；不得以删除现有 Docker workload 解决冲突。
4. candidate 只包含 I-0009 冻结范围内的 implementation、tests、deploy assets 和文档。
5. 六个 external Secret references `fw-postgres-env`、`fw-redis-env`、`fw-qdrant-env`、`fw-minio-env`、`fw-keycloak-env` 和 `fw-grafana-env` 已由 operator 在 Helm 外创建；chart 不拥有或输出其值。
6. 所有 image reference 都是 digest-pinned；所有 PVC、requests/limits、retention 和 quota 都有显式值。

在 owner host 记录候选：

```powershell
$candidateSha = git rev-parse HEAD
git status --short
uv run python -m faultwitness_dev verify-fast
uv run python -m faultwitness_dev eval-changed
```

任何 dirty worktree、short SHA、host-pin failure、missing secret 或 floating image 都必须 fail closed。

## 4. Deployment order and convergence

部署必须使用 `deploy/charts/faultwitness-platform` 中 repository-owned、digest-pinned 的 Helm chart 和 `deploy/environments/private-server/values.yaml` 中的私有环境配置；不得在 live cluster 手工修补后把现场状态当作源代码。固定 release 名为 `fw-platform`，服务分别位于 `fw-system`、`fw-data` 和 `fw-observability`，且只允许 `ClusterIP`，无 Ingress、NodePort 或 LoadBalancer。

首选从 owner host 使用 candidate-bound CLI 执行幂等 reconcile：

```powershell
uv run python -m faultwitness_dev deploy-platform --candidate-sha $candidateSha
uv run python -m faultwitness_dev inspect-platform --candidate-sha $candidateSha --stability-seconds 900
```

CLI 默认读取上面的 chart 和 private-server values；需要显式审计路径时可传入：

```powershell
uv run python -m faultwitness_dev deploy-platform `
  --candidate-sha $candidateSha `
  --chart deploy/charts/faultwitness-platform `
  --values deploy/environments/private-server/values.yaml
```

candidate 必须是 40 位 lowercase hexadecimal SHA。deployment/inspection summary 只写入 repository 外的 private evidence root，且只允许 candidate SHA、bundle digest 与 allowlisted workload aggregate；禁止 raw Kubernetes object、Secret 或 environment locator。

底层等价 Helm reconcile 为：

```bash
helm upgrade --install fw-platform deploy/charts/faultwitness-platform \
  --namespace fw-system --create-namespace \
  -f deploy/environments/private-server/values.yaml \
  --atomic --timeout 15m
```

`--atomic` rollback 不等于 Eval 通过；失败 release 的 private diagnostics 必须保留。直接使用 Helm 不得绕过 candidate binding、15 分钟 inspection 或 publication checks。

固定拓扑和顺序：

1. 创建/校验 `fw-system`、`fw-data`、`fw-observability`、service accounts、external Secret references、NetworkPolicies、quotas 和 PVC。
2. 部署 PostgreSQL、Redis、Qdrant 和 MinIO，等待 health/readiness 收敛。
3. 部署 Keycloak 和 OPA；仅用 synthetic realm/identity 做控制验证。
4. 部署 OTel Collector、Prometheus、Loki、Tempo 和 Grafana。
5. 采集 rollout、PVC、resource bound、listener 和 image digest 的脱敏清单。
6. 所有 required workload 连续 Ready 15 分钟后才可开始 restart、isolation 和 restore Eval。

只读检查可使用：

```bash
kubectl get namespaces
kubectl get pods,statefulsets,deployments,pvc -A -o wide
kubectl get resourcequota,limitrange,networkpolicy,serviceaccount -A
kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{range .spec.containers[*]}{.image}{" "}{end}{"\n"}{end}'
kubectl get events -A --sort-by=.lastTimestamp
```

不得把这些命令的 raw output 直接提交；先删除 private locator、node、IP、Secret reference 和 environment-specific identity。

## 5. Health, persistence and controlled restart

readiness hold 必须覆盖全部 required workloads，并记录 monotonic start/end time、restart count 和不满足 Ready 的 interval。单次 `kubectl get` 不能证明 15 分钟稳定性。

controlled restart 逐个 service 执行，不能同时删除所有 stateful workloads。每次重启后验证：

- rollout 收敛且 PVC 仍绑定到原声明；
- synthetic control record/object/vector/identity/policy 仍可读取；
- telemetry control signals 重新出现并保持 correlation；
- 没有新的 public listener、CrashLoopBackOff、unbounded queue 或 disk-pressure silence。

任何 data loss、PVC replacement、unexpected listener 或 readiness timeout 都判定为 failure，保留失败 timeline 后修复并从新 candidate 重跑。

## 6. Isolation and denial matrix

每个 denial case 都必须配对一个 authorized control case，避免把网络故障误判成隔离成功。至少覆盖：

| Boundary | Authorized control | Required denial |
| --- | --- | --- |
| Network | allowlisted workload reaches its service port | unrelated namespace/service account cannot connect |
| Kubernetes Secret | owning service account can mount only declared Secret | unrelated workload cannot read or mount it |
| PostgreSQL | owner role can access its declared schema/control object | non-owner role cannot read, write or change search path into it |
| MinIO | owning synthetic identity can access its prefix | peer identity cannot list/read/write that prefix |
| Qdrant | authorized synthetic control request succeeds | unapproved identity/network path is rejected |
| Keycloak/OPA | synthetic authorized request returns expected decision | invalid role/token and unavailable dependency fail closed |
| Observability | private operator path can query synthetic signal | unrelated identity/network path cannot query dashboards or backends |

目标是 unauthorized success 为 `0`。denial 只有在服务健康且 authorized control 同时成功时才算有效证据。I-0009 只证明 platform boundary，不把 synthetic denial 扩大为完整 G06 multi-tenant certification。

## 7. PostgreSQL backup and restore

restore 必须进入 fresh target，禁止覆盖 source。测试数据应是 deterministic synthetic dataset，并在 dump 前按冻结 canonicalization 生成 digest。操作顺序：

1. 写入 deterministic dataset 并计算 source canonical digest。
2. 由 operator 生成带 candidate、tool version 和 timestamp metadata 的 encrypted/private backup；不部署 privileged in-cluster CronJob。
3. 创建 fresh restore target 和最小 restore identity。
4. restore 后重新计算 canonical digest。
5. 要求 source 与 restored digest byte-for-byte 相等。
6. 验证 non-owner 无法读取 fresh target，随后按 retention policy 清理 test target。

raw dump、connection string 和 database identifiers 不得进入仓库。公开证据只记录 candidate SHA、sanitized dataset ID、tool/version、两个相同 digest 和 pass/fail。若 restore 或 digest comparison 失败，保留 private backup，不执行 destructive retry，不写 pass report。

## 8. Operational telemetry control signals

向 OTel Collector 发送不含 Secret、PII、private reasoning 或真实 tenant 的 synthetic metric、log 和 trace。验证 Prometheus、Loki、Tempo 都接收相应 signal，Grafana 私有查询路径可关联同一 public-safe correlation ID。

检查 retention、requests/limits、PVC usage 和 disk-pressure alert。label/attribute 不得包含 raw prompt、token、host/IP、credential、object body 或 unbounded high-cardinality value。LangSmith 在此 Eval 中不发送 Agent trace；其完整 trace path 由后续 Iteration 和完整 G01 candidate 证明。

## 9. Supply-chain checks

候选必须证明：

- deployed image 与 repository lock/manifest 中的 digest 精确一致；
- floating tag 数为 `0`；
- 每个 deployed component 都出现在 SBOM/provenance 中；
- incompatible license 数为 `0`；
- scanner 无法解析 image、SBOM 缺项或 provenance mismatch 时 fail closed。

不得把“镜像能启动”当作 supply-chain pass，也不得通过删掉 scanner finding 或放宽 frozen policy 完成 Iteration。

## 10. Candidate-bound Eval

实现、tests、deploy assets 和本 Runbook 全部落盘后，对完整 SHA 执行：

```powershell
$candidateSha = git rev-parse HEAD
uv run python -m faultwitness_dev verify-fast
uv run python -m faultwitness_dev eval-changed
uv run python -m faultwitness_dev eval-iteration I-0009 --candidate-sha $candidateSha
```

EVAL-G01-003 只有在同一 candidate 上同时满足以下条件才可改为 `pass`：

- required workloads 连续 Ready 15 分钟并在 controlled restart 后恢复；
- PostgreSQL restore digest 精确一致；
- unauthorized network、Secret、schema、object-prefix 和 observability access 为 `0`；
- floating images、missing SBOM components 和 incompatible licenses 为 `0`；
- public evidence 通过 secret/publication scan，并绑定完整 candidate SHA。

当前实现和 private deployment 尚未完成，因此 `REPORT.md` 和 manifest 必须保持 `pending`。局部 smoke、现场观察或未绑定 SHA 的证据均不能关闭该 Eval。

## 11. Failure and recovery semantics

- Missing dependency/Secret/PVC：停止 deployment，不用 placeholder credential 或 ephemeral storage 继续。
- Readiness timeout：采集 private diagnostics；不通过扩大 timeout 隐藏 crash、probe 或 resource 问题。
- Keycloak/OPA unavailable：新授权和 policy-dependent path fail closed；不得 default allow。
- Telemetry backend unavailable：保留 bounded failure evidence；不得声称 control-signal correlation 成功。
- Isolation control case fails：该 denial result 无效，先恢复服务健康再重测。
- Unauthorized access succeeds：立即停止相关 Eval，保存私有证据，修复边界并生成新 candidate。
- Backup/restore mismatch：保留 source 和 backup，禁止覆盖 source 或编辑 digest。
- SBOM/license/provenance failure：保持 failure；禁止修改 frozen policy 或省略 deployed component。
- Secret/publication scan hit：不发布 raw evidence，清理公开资产并重新扫描；若进入 Git history，按 incident procedure 处理。

任何重试都必须绑定新的完整 candidate SHA（若 implementation/assets 改变），并保留先前失败事实。I-0009 通过也不得提前关闭 G01。
