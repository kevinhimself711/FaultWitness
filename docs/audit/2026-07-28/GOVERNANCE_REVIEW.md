---
document_id: FW-AUDIT-2026-07-28-GOVERNANCE
audit_date: 2026-07-28
authoritative: false
question: 当前治理系统是否彻底解决了 G02 的治理过载问题
---

# 治理系统审查

## 结论

**是。热路径已经干净。** 一次 eval 失败后完成 debug→重新提交闭环，现在需要的强制治理产物编辑数为 **0**，
阻塞性 CI job 数为 **0**，审批动作数为 **0**。

剩余残留都不在热路径上。其中唯一的真实回退（`audit.py` 失去前门）
已于 2026-07-28 修复，见残留 1。

## 一、G02 的治理成本，用数字确认

用户点名的 corrective iteration / candidate binding / schema / 过度复杂 CI 与 ruleset，
在 G02 证据里可以逐项量化。

### 46 个 Eval 的去向

| 类别 | 数量 | 占比 |
|---|---:|---:|
| 真正测量 Gate 主体（故障实验室 / 基线） | 12 | 26% |
| 被治理、binding、preflight、transport、seam 机械消耗 | 26 | 56.5% |
| 到达 scenario matrix 但未完成的 Gate attempt | 7 | 15% |
| 退役标识符，零执行（EVAL-021/022） | 2 | 4% |

**46 个 Eval 中只有 2 个真正调用过模型**：EVAL-G02-004（4 次 smoke）与 EVAL-G02-046（192 trials）。
其余全部为 0 次模型调用。

最极端的单点证据是 EVAL-G02-012：`preflight-candidate-binding` 因 LF→CRLF 转换 blocked，
**十四个 Gate phase 中没有任何一个进入其 runner**（`docs/evals/EVAL-G02-012/REPORT.md:3-5`）。
一次换行符问题吃掉了一整个 Eval 编号。

### 12 次 Gate attempt 的失败位置

A-G02-001 → A-G02-011 全部失败，A-G02-012 通过。失败位置分布：

- 死在 preflight / binding / access / trace 管道：EVAL-005, 008, 010, 012, 014, 016, 018, 020, 024, 026, 028, 044
- 死在 scenario matrix（真实实验室测量）：EVAL-030, 032, 034, 036, 038, 040, 042

即 **12 次 attempt 死于治理与传输管道，7 次死于真实被测对象**。前者是纯粹的浪费。

失败原因清单本身就是判决：`mc stat` 多要了一个 ListBucket 权限、Windows `CreateProcess` WinError 206、
Python 3.8 没有 `datetime.UTC`、`index.docker.io` 与 `docker.io` 别名不一致、
pinned `minio/mc` 镜像 ImagePullBackOff、LF→CRLF。这些都是环境与传输缺陷，
但每一个都必须走完整的 corrective iteration + 新 Eval 编号 + 新 candidate binding 才能重试。

### C-/A- 双命名空间的机械开销

`governance/policies/iteration-lifecycle-v1.yaml:10-11` 把 `corrective` 与 `gate_attempt`
声明为可直接激活的类型，并强制 `corrective_link_direction: lower_iteration_id`。
后果是 EVAL-023 之后出现完美的奇偶结构：**奇数号 = C- seam 证明（pass），偶数号 = A- Gate attempt（fail）**。
24 个 work item（12 C- + 12 A-）产生 24 个 YAML + 24 个 Markdown + 24 个 Eval 目录，
而其中 C- 被禁止运行 Gate（`gate_l2_execution: 0`），A- 被禁止修改 `src/`。

一次修复被强制拆成两个不能互相验证的记录。这是 G02 时长的结构性来源，不是执行者的问题。

### 历史单点成本

- **access-58**：一个 +12/−7 的运行时修复，最终变成 7 commits / 59 文件改动 / +1,593 行。
- **C-G02-012**：真实 seam 27 秒通过，fix→close 全程约 6 小时。

## 二、简化的成效

### 代码与配置

`git diff --stat`：**80 files changed, 1580 insertions(+), 9333 deletions(-)**。
删除量精确落在用户点名的机制上：

| 文件 | 删除行 |
|---|---:|
| `src/faultwitness_dev/evals.py` | −1801 |
| `src/faultwitness_dev/g02_eval.py` | −1005 |
| `src/faultwitness_dev/checks.py` | −667 |
| `tests/governance/test_governance.py` | −607 |
| `src/faultwitness_dev/g01_eval.py` | −453 |
| `tests/g02/test_g02_eval_protocol.py` | −332 |
| `src/faultwitness_dev/cli.py` | −317 |
| `src/faultwitness_dev/model_eval.py` | −259 |
| `src/faultwitness_dev/changes.py` | −201 |

### CI 与 ruleset

- 2 jobs / 3 required checks → 1 个 advisory matrix job，只跑 `verify-fast`
- `fetch-depth: 0` → `1`
- `.github/rulesets/main.json` 已删除。其 `strict_required_status_checks_policy: true` 是最大阻塞源：
  它要求 PR 必须与 main 保持 up-to-date，于是每次 main 前进都强制 rebase，
  而 rebase 产生新 SHA，新 SHA 又使 candidate binding 失效——一个自激循环。
- 远端 `main` 现在只保护 branch deletion 与 non-fast-forward/force-push
  （`docs/governance/GOVERNANCE_V2.md:69-71`）

`verify_fast` 现在是 11 行（`src/faultwitness_dev/checks.py:49-59`）：UTF-8、Markdown、本地链接、
active schema、current state、ruff、pytest、markdownlint、`git diff --check`。
不再运行 `eval-changed`、G00 audit、历史生命周期扫描、changed-path 授权、Gate Eval 或 live 服务。

### 生命周期资产

- 4 个 lifecycle 模板全部删除（`CLAIM` / `EVAL_MANIFEST` / `GATE` / `ITERATION`.example）
- `PROJECT_STATE.yaml` 19 字段 → 7 字段
- `governance/ASSETS.yaml` → `schema_version: 2.0.0`，仅 14 个 active 资产，9 类模式移除
- `validate_current_state`（`checks.py:33-46`）只做 3 次 `is_file()`：`active_plan`、`active_report`、
  `latest_release.evidence_manifest`

### 闭环成本对照

| 项目 | G02 时期 | 现在 |
|---|---:|---:|
| 强制治理产物编辑 | ~13–14 | **0** |
| 阻塞性 CI job | 3 | **0** |
| 审批 / thread resolution | 有 | **0** |
| strict up-to-date rebase | 强制 | 无 |
| candidate binding 自失效循环 | 存在 | 已取消 |

G02 时期那 13–14 项包括：两个 lifecycle YAML、manifest + candidate-binding、3 个状态字段、
3 份根文档 front-matter 同步、`eval-changed`、3 个 status check、strict up-to-date rebase、
thread resolution，以及一个自身产生新 SHA 从而使 binding 失效的 evidence-sync commit。

### 机制层面的关键改动

`src/faultwitness_dev/experiment.py` 用**语义缓存键**替换了全局 candidate SHA：

```python
def semantic_cache_key(checkpoint_values, required_checkpoints, *, input_digest,
                       dependency_artifacts=None) -> str:
    """Key one unit by semantic inputs, never by governance HEAD or producer SHA."""
```

失效范围由具名 checkpoint（`sut`、`identity_and_storage`、`trace_service`、`model_route`）
与真实依赖闭包决定（`experiment.py:43-63`），不再由一个全局 SHA 决定。
这是「文档 commit 不再使实验失效」的机制基础，而不只是一句政策声明。

`AGENTS.md:23-25` 另加了一条反死锁规则：连续两个只改治理、没有新 runtime observation 的动作
即判定为编排死锁，必须删除或绕过非语义阻塞项。这条规则如果在 G02 存在，
按上表 12 次管道死亡的模式，本应在第 2 次就触发。

## 三、残留项

### 残留 1：`audit.py` 失去前门（唯一真实回退）—— 已修复

`src/faultwitness_dev/audit.py` 的 `audit_repository`（374 行，含 SBOM、license、
GitHub Action SHA-pin、secret 扫描）曾**只能通过 `tests/audit/test_audit.py:78` 间接触发**：
`verify_fast` 不调用它，CLI 没有对应子命令。

这是简化唯一走过头的地方：secret 扫描与 Action SHA-pin 是安全检查，
不应只作为单元测试的副产品运行。G00 曾把它作为独立 CI job（`REPORT.md:29-33` 记录三个 job）。

**状态：已于 2026-07-28 修复。** `audit.py` 已接回 `verify-fast`，349 tests passed，
`test_verify_fast_invokes_only_active_local_checks` 按新的活跃检查集更新而非绕过。
治理侧至此**不再有真实安全回退**，只剩残留 2（孤儿 schema）与残留 4（operator 缺口）。

### 残留 2：7 个孤儿 schema 仍编码已删除的词汇

`schemas/governance/` 下 7 个 schema 不被任何 active 代码引用：
`carry-in-registry`、`claim-registry`、`eval-manifest`、`gate-walkthroughs`、`gate`、
`iteration`、`validation-registry`。

其中仍留有已废弃概念的字面定义：

- `iteration.schema.json`：`"iteration_type": {"enum": ["standard", "corrective", "gate_attempt"]}`
- `eval-manifest.schema.json`：仍 require `candidate_sha` / `evidence_head_sha`

不在热路径上，但它们是「治理已简化」这一事实的反证物，会误导后续读者。属可选清理。

### 残留 3：`_check_gate_walkthroughs` 死代码

`src/faultwitness_dev/schemas.py:270` 定义后从未被调用。属可选清理。

### 残留 4：没有 operator 入口（闭环的人机缺口）

这是与用户问题最直接相关的一项：**治理摩擦消失了，但「只重跑受影响单元」的操作人机界面没有接出来。**

- `cli.py` 有 **0 个** eval 子命令（已逐行确认：`verify-fast`、`validate`、`external-links`、
  bootstrap/secrets、infra、deploy/inspect/smoke、`compile-contracts`、`check-contracts`、diagnose）
- `Makefile` 只有 1 个 target（`verify-fast`）
- `run_gate_deterministic_matrix` / `run_gate_live_matrix` 只是库函数，
  仅从测试与 `tools/proofs/` 可达
- `experiment.py` 的 `affected_units()` 与 `semantic_cache_key()` 完全未暴露

更具体地说，operator 在 eval 失败后第一个会撞上的门是 `experiment.py:339-342`：

```python
if status in {"metric_fail", "blocked"}:
    raise GovernanceError(
        f"unit {unit.unit_id} cannot retry unchanged semantic inputs after {status}")
```

这条规则本身是正确的（防止不改语义就刷分），但它只说「不许」，不说「改哪个 checkpoint 才能合法重跑」。
配套建议见 [EVAL_HARNESS_REVIEW.md](EVAL_HARNESS_REVIEW.md) 的 operator CLI 项。

## 四、对本次审查自身的约束

本审查文档属于治理文档。按 `AGENTS.md:23` 与上述反死锁规则，
它不使任何 G00–G02 运行时或 Eval 证据失效，也不构成 Gate Plan 修订。

同时提醒一条来自 G02 的教训：**不要用新治理去修治理**。
残留 1 的修法是 11 行 `verify_fast` 里加一行调用，不是新建审计生命周期。
