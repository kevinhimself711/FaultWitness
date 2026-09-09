# FaultWitness 轻量治理 v2

## 目标

治理只保留三类直接价值：保护产品与安全语义、让基础设施操作可复现、让 Eval 结果可归因。
它不得把文档顺序、Git HEAD、状态镜像或审批仪式变成实验前置条件。

## 活跃资产

| 资产 | 职责 | 更新频率 |
|---|---|---|
| `PROJECT_STATE.yaml` | 唯一当前 Gate 状态 | Gate 边界 |
| `docs/gates/G##/PLAN.md` | 范围、指标定义、工作包、外部 seam、失败语义 | 定义实施前冻结；数值参照物待首次有效测量 |
| trial/phase journal | 真实执行、checkpoint、输入输出、终态 | 每次真实执行原子写入 |
| `docs/gates/G##/REPORT.md` | 根因、复验、指标与结论汇总 | Gate 关闭一次 |
| release manifest | 一个 release SHA 与运行 subject/artifact digests | Gate 关闭一次 |

未来不创建 per-Iteration YAML、I/C/A、Eval 占位目录、activation/closure 记录、candidate-binding
JSON、evidence-head 或根文档状态镜像。

## 实施与调试

正常工作包直接来自 Gate Plan。runner 或实现失败后执行：

```text
failed journal
→ 一个可证伪根因
→ 现有 runner/实现的最小修复
→ targeted test + 必要时一次 real seam
→ 只复验受影响 trial 与真实依赖
→ 在同一 journal 续跑
→ Gate 关闭时汇总一次
```

若连续两个动作只修改治理/provenance 且没有新 runtime observation，编排已经死锁；下一步必须
删除/绕过阻塞项或运行真实受影响实验，不能继续补治理资产。

## Journal 协议

- `execution_attempt`：仅在真实工作重新执行时递增。
- `record_version`：同一 execution 的 `running → terminal` 等原子更新时递增。
- 语义修复开始新 execution 时，上一终态及最后的副作用/observation checkpoint 进入同一
  trial 的 `history`，不能被新 pass 覆盖。
- `producer_sha`：事实 provenance，不参与文档或治理身份判断。
- `checkpoints`：具名运行 subject，例如 `sut`、`identity_and_storage`、`trace_service`、
  `model_route`；每个 phase 声明自己依赖哪些 checkpoint。
- passed trial 只在其输入或依赖 checkpoint 改变时失效。全局 SHA、文档、REPORT、CLAIMS、
  状态文件和无关 evaluator 变化不会全局失效。

## Git 与 release provenance

Git SHA 的唯一必要职责是回答“哪份代码产生了结果”。执行 journal 记录实际 producer SHA；Gate
关闭时，一个 release commit 包含实现、测试和 Gate Report，Gate tag 指向它；随后至多一个状态/
manifest 文档 commit 记录已知 release SHA 与 image/config/dataset/model/locked-test/Ground-Truth/
environment/artifact digests。后继文档 commit 没有 evidence 身份，也不会使实验失效。取消：

- candidate/evidence/governance 三套身份；
- `HEAD == evidence_head_sha`；
- evidence-only changed-path allowlist；
- tracked binding 自引用；
- `evaluated_revision` 追逐包含自身的 commit；
- 全局 candidate/evaluator digest 导致所有 phase 失效。

## CI 与 GitHub ruleset

`verify-fast` 运行 active schema/contracts、ruff、pytest、Markdown/UTF-8/link、diff 与本地仓库
publication audit。后者覆盖 lockfile、Action SHA pin、license、CODEOWNERS、公开产物中的
secret/local-path 泄漏与 SBOM；它不是旧的 Gate 生命周期。Ubuntu/Windows CI 保留为跨平台反馈，
但不作为远端 ruleset 的 required status。CI 不运行 `eval-changed`、历史 Gate audit、
历史生命周期扫描、changed-path 授权、Gate Eval 或 live 服务。

远端 `main` ruleset 只保护 branch deletion 与 non-fast-forward/force-push。个人仓库不模拟组织级
PR 审批、thread resolution、strict up-to-date 或多状态组合。

## 冻结定义，不冻结未知数

指标**定义**（判据、谓词、失败语义、样本量口径、`diagnostic_only` 处理）实施前冻结，这部分不变。
但**引用某个实测量的数值目标**不在实施前冻结：Gate Plan 冻结目标的**形式与边际**
（例如 `best_baseline + 0.05`），参照物本身写作"待定，由首次通过仪器有效性检查的运行确定"。

理由是实测的：G03 的 `+5pp` 当初钉在 G02 实测的 `deterministic 0.500` 与 live `0.000` 上，
后来查明前者是规则表缺陷、后者是标签格式 artifact——门槛被钉在两个仪器故障读数上。
一旦"已冻结，只能提高"生效，修正仪器就只能走修正案，而修正案越贵，把结果解读成通过的动力越大。
代价可数：3 个 metric 版本、7 份修正案、8 个 `-invalidated-*` 运行目录、r1–r9 中 3 轮作废。

由此产生三条硬性程序：

1. **先证伪仪器，再花模型预算**，顺序为泄漏探针 → 分化度 → 披露对称性 → 才买 trial。
   零模型成本的单特征分类器就能证伪"baseline 太强"，它应当跑在第一轮之前。
2. **披露对称性是阻塞检查项。** 任何评分规则必须对所有被比较的臂同等披露；
   若对照臂按构造直接获得答案而被测臂必须自行推断，该比较无效，
   且其失效方式是**让门通过**而不是让门失败。
3. **冻结目标变成数学上不可达是设计缺陷信号。** 停下并连同产出它的测量一起上报，
   提出任务形态或范围变更；不得封顶目标、剔除领先对照臂、下调 floor 或为标签好看而改谓词。

重新推导参照物不等于弱化：前提是指认出具体的仪器缺陷，且目标的形式与边际保持不变。

## 不降低严谨性的边界

本迁移不改变任何 Eval N、质量/性能阈值、health oracle、权限、Ground Truth、locked test、
模型 route、token/费用上限或失败语义。被删除的是证明路径周围的重复治理，不是实验本身。

验证仍遵循 L1/L2/L3、零容忍 runner/negative fixture/artifact 三件套、逐 trial 持久化、失败续跑、
真实 external seam 和 destructive/soak 一次性语义。

## 三大工程素养映射

| 素养 | 保留的直接证明 | 删除的无关负担 |
|---|---|---|
| 应用 | tenant 身份、幂等/冲突、状态与 API tests | lifecycle 状态镜像、commit 仪式 |
| Infra | Linux/Windows、byte transport、真实 K3s seam、image/config/environment digest | HEAD 等式、candidate ConfigMap 作为前置 |
| 算法/Eval | scorer 负例、trial journal/resume、cluster bootstrap、artifact digest | Eval 占位目录、全局 SHA cache、重复矩阵 |

机器证明见 `tests/governance/test_governance_v2.py`，执行结果见
`GOVERNANCE_V2_PROOF.md`；历史对照与迁移结论见
`docs/engineering/G02_GOVERNANCE_RETROSPECTIVE.md`。
