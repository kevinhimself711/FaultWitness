# I-0007 Secure Bootstrap Runbook

## 1. Purpose and boundary

本 Runbook 只用于 I-0007：把一次性 plaintext handoff 迁移到 repository 外的 SOPS + Age store，建立 project-specific SSH identity 和 out-of-band host pin，并生成不含 host locator、identity、Secret、container name 或 private path 的能力基线。

本流程不授权安装 K3s、改变 Docker workload、调用 Bailian 模型、调用 LangSmith API、修改防火墙或部署服务。任何失败都必须保留 handoff 和 staged encrypted recovery material，不得通过跳过验证完成 Iteration。

## 2. Private and public assets

Private owner-host assets：

- Age identity、encrypted SOPS store、bootstrap metadata。
- SSH private/public key、accepted `known_hosts` 和未接受的 host-key candidate。
- Raw operator/UI evidence 和 private Eval summary。

这些资产必须位于 repository 外，不得把绝对路径、值、suffix、host fingerprint 或可逆 credential hash 写入 Git。

Public repository assets：

- `.sops.yaml` 中的 Age public recipient。
- `config/secrets/schema.yaml`、无值 example 和 pinned toolchain lock。
- Bootstrap/probe code、测试、sanitized capability baseline、Eval manifest/report。

## 3. Install and verify pinned tools

在 Windows owner host 执行：

```powershell
.\deploy\bootstrap\install_tools.ps1
```

脚本只从冻结的官方 GitHub release URL 下载 SOPS 3.13.2 和 Age 1.3.1，并校验 `config/secrets/toolchain.lock.yaml` 中的 SHA-256。任何版本、URL、archive 或 executable hash 漂移都失败。

## 4. Create project identities

全新 owner host 执行：

```powershell
.\deploy\bootstrap\init_identities.ps1
```

脚本拒绝覆盖既有 identity。Age private identity 和 SSH private key 位于 repository 外；private ACL 必须禁止普通其他账户读取。SSH key 是本项目独享的 Ed25519 key，不得复用个人默认 key。

将 `age-keygen -y` 导出的 public recipient 写入 `.sops.yaml`。Public recipient 变化必须与新 identity、round-trip 和 recovery 验证一起提交，不能静默替换。

## 5. Encrypt the handoff without deleting it

```powershell
uv run python -m faultwitness_dev bootstrap-secrets
uv run python -m faultwitness_dev verify-bootstrap
```

实现要求：

- Parser 只接受声明的六个字段。
- Plaintext 通过 stdin 交给 SOPS，不创建 plaintext temporary file。
- Encrypted store 写入后立即在进程内 decrypt/validate，并与原值做内存比较。
- Public stdout 只报告字段数量和状态。
- 旧服务器密码即使弱也先安全收容，但 metadata 必须标记为需要轮换。
- 在所有后续验证完成前保留 `envs.txt`，防止半迁移锁死。

## 6. Verify and pin the SSH host out of band

先获取未信任 candidate：

```powershell
uv run python -m faultwitness_dev capture-host-key
```

通过云厂商 serial/web console 在服务器本机执行：

```text
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256
```

只有两个完整 SHA-256 fingerprint 完全一致时才执行：

```powershell
uv run python -m faultwitness_dev accept-host-key --fingerprint <OUT_OF_BAND_SHA256>
```

严禁 `StrictHostKeyChecking=no`、`accept-new` 或把 scan 本身当作独立验证。Host/IP/port/fingerprint 只保存在 private owner-host state 和操作会话中，不进入 Git。

## 7. Install and verify the project SSH key

```powershell
uv run python -m faultwitness_dev install-ssh-key
```

旧密码只存在于父进程和短生命周期 `SSH_ASKPASS` environment，不出现在 command arguments、stdout、stderr 或文件中。公钥安装后必须用 `BatchMode=yes`、password disabled 和 accepted `known_hosts` 验证；失败时保留旧登录方式和 handoff。

## 8. Rotate credentials

### Server password

```powershell
uv run python -m faultwitness_dev rotate-server-password
```

流程先产生符合策略的随机 replacement 并验证下一版 SOPS ciphertext，再通过 dedicated SSH key 执行受控 password change。只有新密码登录成功后才原子切换 encrypted store 并把 rotation 标记为 verified；失败时保留 staged ciphertext 供 reconciliation。

### Bailian and LangSmith

分别在官方 Provider UI 新建 replacement key、确认 active，并使用 UI 的 Copy 操作。不要粘贴到 terminal、文件或 Codex message。每次复制后立即运行：

```powershell
uv run python -m faultwitness_dev record-api-rotation --name bailian.api_key --from-clipboard --provider-ui-confirmed
uv run python -m faultwitness_dev record-api-rotation --name langsmith.api_key --from-clipboard --provider-ui-confirmed
```

命令直接从 clipboard 读取到进程内存，完成 SOPS round-trip 后原子替换 store。I-0007 不调用模型或 LangSmith API；Provider UI 的 creation/active 状态是本 Gate 的 rotation evidence，真正调用由 I-0013/I-0014 Eval 完成。

## 9. Capture the sanitized capability baseline

在 implementation candidate commit 后运行：

```powershell
uv run python -m faultwitness_dev probe-host `
  --candidate-sha <FULL_HEAD_SHA> `
  --output docs/evals/EVAL-G01-001/CAPABILITY_BASELINE.json
```

CLI 通过 accepted host pin 和 dedicated key 两次发送同一 allowlisted read-only probe。两个 normalized document 必须完全相同；任何 host/user/IP/container name/fingerprint/Secret field 都失败。公开 baseline 只包含硬件/OS/Runtime capability、聚合 Docker health、port occupancy boolean、CIDR conflict boolean、candidate SHA 和 normalized digest。

## 10. Finalize and evaluate

仅在三项 rotation、host pin、SSH key 和 repeated capability evidence 全部 verified 后：

```powershell
uv run python -m faultwitness_dev finalize-bootstrap
```

该命令普通删除 `envs.txt`，不声称 SSD secure erase。随后向 `.gitignore` 增加且只增加精确 `/envs.txt` 规则。

```powershell
.\tools\bin\make.cmd verify-fast
.\tools\bin\make.cmd eval-changed
uv run python -m faultwitness_dev eval-iteration I-0007 --candidate-sha <FULL_HEAD_SHA>
```

EVAL-G01-001 必须验证 tool hash、SOPS round-trip、rotation、host pin、SSH key、两次 probe、frozen server floor、publication boundary 和 private-material tracking 均通过。失败时回到对应步骤，不修改阈值或删除失败证据。

## 11. Recovery and failure semantics

- Tool/hash mismatch：停止，不执行 identity 或 Secret 操作。
- Encryption/round-trip failure：保留 handoff，不写通过状态。
- Host fingerprint mismatch：删除或隔离 candidate，不认证。
- SSH key verification failure：保留密码登录与 handoff。
- Password change 后验证失败：使用 dedicated SSH key 和 staged ciphertext reconciliation，禁止猜测/盲目重试。
- Provider replacement 未确认：rotation 保持 pending，禁止 finalize。
- Probe drift：保存 private failure summary，调查 Docker/host 状态变化后重跑两次。
- Publication scan hit：I-0007 失败；不得通过 ignore broad pattern 隐藏泄漏。
