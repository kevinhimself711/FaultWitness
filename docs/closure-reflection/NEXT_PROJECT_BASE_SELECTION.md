---
doc_id: NEXT_PROJECT_BASE_SELECTION
title: 下一个项目的基座与 Benchmark 选型调研
status: research
authoritative: false
date: 2026-09-13
supersedes_stance: proposals/*.md §2.4（"不 fork 任何 AI SRE Agent"）
related: docs/engineering/PROJECT_POSTMORTEM.md
---

# 下一个项目的基座与 Benchmark 选型调研

## 0. 这份文档要回答的三个问题

1. **不冲突吗**：harness engineering（agent 开发 + 后端开发）作基本盘、Agentic RL 作拔高，
   两者对 benchmark 的要求是否互斥。
2. **会不会为了 RL 牺牲后端厚度**：如果为了"RL 收益可证"而选 bench，是否被迫放弃后端深度。
   同时列出"RL 不可证但后端与 harness 很扎实"的低风险路线。
3. **多给选项**：适配性 A/B/C 只是档位期待，在能证实的前提下多找多推荐。

**一条前置声明**：三份 proposal 的 §2.4 明文写着"不 fork 任何 AI SRE Agent"，
并列了整节禁令。那条禁令是 `PROJECT_POSTMORTEM.md` L1 的直接根源
（从 JD 反推需求 → 一切自己造 → 57 条需求只有 21 条有面试价值）。
**本文档显式作废那条禁令。** 下一个项目的起点是别人的 CI 是绿的，不是我的 docs 是齐的。

所有数字均为 2026-09-13 实测（GitHub API / raw 文件直读），标注了实测与推断的区别。

---

## 1. 结论先行

**推荐主线：HolmesGPT（基座）+ 它自带的 274 case（B 档起步）→ SREGym（A 档扩展）→ RL（第三步）。**

| 档位 | 组合 | 适配成本 | 后端厚度 | harness 收益可证 | RL 可证 |
|---|---|---|---|---|---|
| **B** | HolmesGPT + 自带 274 case | 零（原生） | 高 | 是（上游有历史基线） | 否 |
| **A** | HolmesGPT + SREGym | 一个 driver（~10KB 量级） | 高 | 是（公开 leaderboard） | **是** |
| C | HolmesGPT + AIOpsLab | 需自写 adapter | 高 | 弱 | 弱 |
| — | HolmesGPT + ITBench | 无 adapter 契约 | 高 | 否 | 否 |

**答案摘要**：

- **A 不冲突。** 两条线落在同一套设施的不同层：改 agent 代码用 case 与 leaderboard 证明，
  做 RL 用 oracle 与 generator。改 agent 不动 bench，做 RL 不改 agent 代码，归因不交叉。
- **B 不需要牺牲。** 后端厚度来自基座（HolmesGPT 的真实 issue），
  RL 可证性来自 bench（SREGym 的 57 个 oracle + 三轴 generator）。两者的来源不同，不争夺同一预算。
- **C 给出 5 个可行组合**，其中 2 个 RL 可证、3 个纯后端低风险。

---

## 2. 候选清单（实测，2026-09-13）

### 2.1 产品基座（可二次开发的成品 agent）

| repo | 星 | fork | 语言 | 最后推送 | 许可 | 判定 |
|---|---|---|---|---|---|---|
| [Tracer-Cloud/opensre](https://github.com/Tracer-Cloud/opensre) | 11,047 | 1,610 | Python | 09-13 | Apache-2.0 | 排除，见 §2.4 |
| [k8sgpt](https://github.com/k8sgpt-ai/k8sgpt) | 8,175 | 1,053 | Go | 09-11 | Apache-2.0 | 非 agent（单轮 analyzer） |
| [kubectl-ai](https://github.com/GoogleCloudPlatform/kubectl-ai) | 7,566 | 718 | Go | **07-15** | Apache-2.0 | 两个月未动 |
| [kagent](https://github.com/kagent-dev/kagent) | 3,713 | 759 | Go | 09-11 | Apache-2.0 | 框架而非成品 |
| **[HolmesGPT](https://github.com/HolmesGPT/holmesgpt)** | **3,286** | **482** | **Python** | **09-13** | **Apache-2.0** | **推荐** |
| [robusta](https://github.com/robusta-dev/robusta) | 3,094 | 323 | Python | 09-13 | MIT | HolmesGPT 的上游平台，可选配 |
| [keep](https://github.com/keephq/keep) | 12,314 | 1,506 | Python | 09-13 | NOASSERTION | 告警管理非诊断；许可不明 |

### 2.2 Benchmark / 评测基座

| repo / 论文 | 规模 | agent 契约 | 打分 | 判定 |
|---|---|---|---|---|
| **[SREGym](https://github.com/SREGym/SREGym)** 277★ MIT 09-13 | **90 题**（Lite 21 题） | **`agents.yaml` 一行 + 一个 driver** | 57 个 oracle + LLM judge | **推荐（A 档）** |
| [AIOpsLab](https://github.com/microsoft/AIOpsLab) 982★ MIT | 60+ 题 | 两个 Python 方法 | 自带 grader | 见 §2.5 的否决理由 |
| [ITBench](https://github.com/itbench-hub/ITBench) 505★ | 开源 6 个 SRE 场景 | **无文档化 adapter** | 自跑自交 | 仅作最后对标 |
| [Cloud-OpsBench](https://www.alphaxiv.org/abs/2603.00468)（arXiv 2603.00468） | 754 case / 57 故障 | 未公开仓库 | JRA + ECR | 作 reward 设计参考 |
| [RCAEval](https://github.com/phamquiluan/RCAEval) 222★ MIT | 数据集 + 基线库 | Python 包 | 离线指标 | 数据集类，非 agent 环境 |
| [OpenRCA](https://github.com/microsoft/OpenRCA) 419★ MIT | 数据集 | — | 离线 | 同上 |
| [k8s-ai-agent-benchmark](https://github.com/henrikrexed/k8s-ai-agent-benchmark) | 14 场景 | 手工 | 人工 0–3 分 | **强制依赖 Dynatrace 商业服务** |

### 2.3 为什么选 HolmesGPT

- **唯一真 agentic loop**：自己决定取什么数据、迭代假设。k8sgpt 是一轮 analyzer + `--explain`；
  kubectl-ai 介于两者之间且两个月未推送。
- **CNCF Sandbox**，0.41.0 发布于 2026-09-08，**今天仍有提交**（`pushed_at` 2026-09-13）。
- **Python**，与上个项目的技术栈一致，5,819 行产品代码里的契约/网关经验可直接读懂它。
- **自带完整 harness**：`tests/llm/fixtures/test_ask_holmes/` 下 **274 个 case**。
- **~40 个内置 toolset** + 文档化的自定义 toolset 扩展点 + 通用 REST toolset。
- 已实现上个项目从零造的机制：审批门、bash 工具沙箱、token 预算、大结果外置
  （`tests/` 下有 `test_approval_*`、`test_bash_toolset_validation`、`test_compaction`）。

### 2.4 为什么排除 OpenSRE（尽管它 11,047★）

星数最高，但三条硬伤（均来自其 README/文档实读）：

1. **`opensre setup` 要求注册/登录 Tracer 账号**，shell 只在账号激活后打开。
   默认路径走 Tracer 托管模型，遥测默认开启（需 `OPENSRE_NO_TELEMETRY=1` 关闭）。开源但不自足。
2. **public alpha，自述 API 与集成仍会变动**，且刚删除了 graph/chain 框架层——
   基底正在重构中，二次开发会一路撞 breaking change。
3. **无打包好的 harness**：只有 `tests/e2e`；"scaled to thousands of failure scenarios
   的开放 RL 环境"是它自己标注的 aspiration，不是可跑的东西。

**成熟度不看星数，看 clone 下来能不能跑绿。**

### 2.5 为什么 AIOpsLab 只能是 C 档（修正此前的推荐）

此前曾把 HolmesGPT + AIOpsLab 并列推荐，**那个组合是错的**。实读 `clients/registry.py`：

```python
self.AGENT_REGISTRY = {
    "gpt": GPTAgent, "qwen": QwenAgent, "deepseek": DeepSeekAgent,
    "vllm": vLLMAgent, "openrouter": OpenRouterAgent, "generic": GenericOpenAIAgent,
}
```

**六个条目全是模型客户端，没有任何产品级 agent。** `clients/README.md` 逐条自述：
"A **naive** GPT series LLM agent with **only shell access**"、naive DeepSeek、naive Qwen、
naive ReAct、naive FLASH。

**从未有产品级 agent 被 onboard 过**，意味着接 HolmesGPT 要自己写 adapter，
而那个 adapter 就是新仪器——`PROJECT_POSTMORTEM.md` L8（仪器在测量自己）会原地复发：
分数低时无法分辨是 adapter 的问题还是 agent 的问题。

---

## 3. SREGym：本轮最重要的发现

[`SREGym/SREGym`](https://github.com/SREGym/SREGym)，277★，MIT，2026-09-13 有推送，
arXiv [2605.07161](https://arxiv.org/html/2605.07161v3)（UIUC + Toronto），
有[公开 leaderboard](https://sregym.com/leaderboard)。

### 3.1 它是 AIOpsLab 与 ITBench 的超集

90 个问题涵盖两者全部，另加 OS 层故障、亚稳态故障、并发故障。
**SREGym-Lite 是 21 题精选集，8 vCPU / 16 GB 即可跑。**
故障取自真实 postmortem：Cloudflare WAF CPU 耗尽、conntrack 表耗尽、GKE IP 耗尽、
cert-manager webhook TLS 不匹配、Kafka poison pill、Reddit Pi-Day。

### 3.2 已 onboard 10 个 agent，注册契约极轻

`agents.yaml` 实读，在册：`stratus`、`codex`、`claudecode`、`gemini`、`opencode`、
`copilot`、`cursor`、`tierzero`、`autosubmit`、`debug`。

```yaml
- name: claudecode
  kickoff_command: python -m clients.claudecode.driver
  install_script: install-claudecode.sh
  container_isolation: true
```

`sregym/agent_registry.py` 的 `AgentRegistration` 只有 7 个字段。
driver 本身是**一个 HTTP 客户端**——从 conductor API（`/get_app`）取题、agent 自己跑、submit 回去。
`clients/claudecode/driver.py` 10,294 字节；`clients/harness/` 总共三个文件（194 + 1,278 + 2,768 字节）。

**所以接 HolmesGPT 是 A 档而不是 C 档**：adapter 就是一个 driver，
信号转换只有"取题 → 跑 → 提交"三步，不重新定义任何指标，不引入仪器噪声。

### 3.3 防泄漏是硬隔离（上个项目最该有的东西）

agent 在隔离 Docker 容器内运行，**读不到问题定义与打分逻辑**。
网络默认过滤（`--internet-access open` 才放开），容器除 `DAC_OVERRIDE` 外丢弃全部 capability，
仅 `/logs` 与 `/workspace` 从宿主 bind-mount。

对照 `PROJECT_POSTMORTEM.md` L8：上个项目三代 metric 泄漏
（v1 无条件 `working_set` 键、v2 六证据组存在性签名、v3 去泄漏后任务饱和），
全都是因为**仪器与被测对象在同一进程空间里**。这里从架构上不可能发生。

### 3.4 两个 README 未提、但决定 RL 可行性的目录

这是本轮调研的关键发现，README 完全没有记载，由 GitHub API 直读目录得到。

**`sregym/generators/` —— 程序化环境生成，三个正交轴**

```
fault/     base.py  helpers.py  custom/
           inject_app.py 31,632   inject_hw.py 16,157    inject_kafka.py 21,517
           inject_kernel.py 16,246  inject_operator.py 14,494  inject_os.py 2,641
           inject_otel.py 5,227   inject_remote_os.py 21,902  inject_tt.py 7,847
           inject_virtual.py 153,567   script/
noise/     catalog.py 2,433   manager.py 13,526   impl/
workload/  locust.py 7,574   wrk2.py 12,010   trainticket_locust.py 5,255
           blueprint_hotel_work.py 21,562   hotel_search.py 10,399   stream.py
```

`inject_virtual.py` 单文件 153KB，`fault/custom/` 留了自定义入口，
noise 与 workload 是独立的 manager 与生成器。**故障 × 噪声 × 负载三轴可程序化组合**，
RL 需要的场景多样性有来源，不必只在 90 个手写问题上循环。

**`sregym/conductor/oracles/` —— 57 个独立 oracle**

每类故障一个 mitigation oracle（`conntrack_mitigation.py`、`cpu_throttling_mitigation.py`、
`dns_resolution_mitigation.py`、`hpa_control_plane_mitigation.py`、
`secret_rotation_stale_env_mitigation.py` 17,214 字节、`stale_hostaliases_mitigation.py` 22,754 字节 …），
外加 `diagnosis_oracle.py`（25,866 字节）、`detection.py`、`compound.py`、
`alert_oracle.py`、`network_policy_oracle.py`、`llm_as_a_judge/` 子目录。

**这是 process-level reward 的现成来源。** 见 §5.2 为什么这一条是 RL 的关键。

### 3.5 SREGym 的三条风险（必须先知道）

1. **偏好自管 Kubernetes，需要 SSH + root**（要做 OS 层集群配置），
   明确排除托管 K8s。kind 可跑但"并非所有问题都支持"。
   → 现有 K3s 宿主条件成立，**但那台机器有硬件级 kernel panic 史
   （ADR-0016/0017，散落 RIP、崩溃重启循环）。`PROJECT_POSTMORTEM.md` L10 会在此复发，
   且 RL 需要成百上千 episode，代价远高于 r1–r9 的九轮。**
2. **`--profile svelte` 改变 agent 可观测内容，README 明确警告其分数与 `full` 不可比。**
   这与 L7 的 disclosure asymmetry 是同一个坑——不要把 profile 当作环境轴。
3. **没有 Gym 式 `step()`/`reset()` API**（尽管名字叫 Gym）。
   实际是两阶段 episode（diagnosis → mitigation），结果是分类型的
   （`complete` / `inconclusive`），**没有 scalar reward、没有 partial credit、没有 per-step 打分**。
   reward function 与 step API 要自己写。

---

## 4. 回答 A：两条线不冲突，落在同一套设施的不同层

**理论上它们可能冲突**：harness engineering 要求 bench 对 agent 内部改动敏感；
RL 要求 bench 提供 process-level 信号。多数 bench 只满足一个。

SREGym 的实际结构同时满足两个，分工如下：

| 你改什么 | 在哪证明 | 属于哪条线 | 是否动 bench |
|---|---|---|---|
| memory 层、上下文压缩、工具调度、超时与取消、缓存 | 274 case + SREGym 21/90 题 | harness engineering + 后端 | **不动** |
| reward function、场景采样、训练循环 | SREGym oracles + generators | agentic RL | **不改 agent 代码** |

**归因不交叉**：改 agent 时 bench 是常量，做 RL 时 agent 代码是常量。
这正是上个项目做不到的事——那时仪器与被测对象同时在变
（3 个 metric 版本 × 7 份修正案 × 8 个失效运行）。

**一条硬边界（来自 L7/L8 的代价）**：

- **加 case 安全**：case 是纯数据（两个 YAML），加 case 只是扩大测试集。
- **改 agent 代码安全**：harness 不变、case 不变，分数变化就是你的贡献。
- **改打分器破坏可比性**：一旦动 `classifiers.py`、autoevals 配置或 `expected_output` 判定方式，
  你的分数与上游 CI、与别人 PR 的分数就不可比。
  上个项目已经付过这个代价两次（ADR-0017 换宿主使全部 readiness 证据不可比；
  ADR-0018 撤回 margin 使锚定读数作废）。

> **配对关系的正确形式：HolmesGPT 的 agent 代码 = 你改的东西；
> `tests/llm/` 与 SREGym 的 oracle = 你不改的东西。**

---

## 5. 回答 B：不需要为 RL 牺牲后端厚度

### 5.1 两者的来源不同，不争夺同一预算

- **后端厚度来自基座**：HolmesGPT 的真实 open issue（§6.2），与 bench 选择无关。
- **RL 可证性来自 bench**：SREGym 的 57 个 oracle + 三轴 generator，与 agent 代码无关。

换 bench 不会减少后端可做的事；不做 RL 也不会减少 harness 可证的收益。
**唯一真实的约束是时间**，而这由 §7 的顺序解决：前两步不依赖 SREGym，
即使 SREGym 环境搭不起来或宿主再崩，已交付的东西不受影响。

### 5.2 RL 的真实天花板（选 bench 时最该谨慎的地方）

**目前不存在成熟的 SRE agentic RL 环境。** 检索到的 `revanth2605/sre-incident-gym`（0★）、
`pratik0620/incident-response-triage-openenv`（1★）都是个人仓库，**未验证能否运行**，
只能当线索不能当选项。

真实形状：**环境层（故障注入 + oracle）可复用，reward function 与 step API 要自己写。**
这既是工作量也是机会——把一个 live benchmark 包成 RL 环境本身就是可讲的贡献。

**reward 设计的关键教训**，来自 Cloud-OpsBench（arXiv 2603.00468，CUHK + 中山大学，2026-08-22，
754 case / 57 故障 / OnlineBoutique + TrainTicket，快照-回放保证可比）：

| 应用 | Joint RCA Accuracy | Evidence Closure Rate |
|---|---|---|
| OnlineBoutique | 0.76 | **0.38** |
| TrainTicket | 0.68 | **0.15** |

论文结论：**agent 答对了根因，却没有做支撑那个答案的调查**，
"final-answer correctness alone substantially overestimates agents' ability to perform
evidence-grounded diagnosis"。

**对 RL 的直接含义：只奖励最终答案正确，会把这个 gap 训得更宽。**
SREGym 的 per-stage oracle（`diagnosis_oracle.py` 与 57 个 mitigation oracle 分离）
正好提供 process-level 信号——不需要自己定义证据图谱。
**这是 SREGym 相对其他 bench 在 RL 维度上的决定性优势。**

另一条参考数字：[ITBench-AA](https://huggingface.co/blog/ibm-research/itbench-aa)
的 59 个 SRE 任务上**所有被评模型都低于 50%**；
SREGym 论文报告 diagnosis 成功率 38.1–72.6%、mitigation 40.4–78.5%，
故障下沉到应用层以下时**下降最多 40 个百分点**。提升空间是公开证据，不是自我声称。

### 5.3 低风险纯后端路线（RL 不可证也不影响）

按可交付性排序。**这三条都不需要 SREGym，不需要 RL，各自独立可讲。**

**L-1. 在 HolmesGPT 自带 274 case 上做 harness engineering（推荐作为第一步）**

运行门槛实测很低：`poetry install --with=dev` 即可，braintrust **可选**
（配了 `BRAINTRUST_API_KEY` 才自动上报）。

```bash
RUN_LIVE=true MODEL=gpt-4.1 poetry run pytest -m 'llm and easy' --no-cov
# 或 ./run_benchmarks_local.py --models ... --markers ... --iterations ... --filter ... --parallel
```

- 子集选择：marker（`easy`/`medium`/`logs`/`kubernetes`/`regression`/`benchmark`）、
  `-k` 单例、`--skip-setup`/`--skip-cleanup`/`--only-setup` 迭代调试。
- 打分：LLM-as-judge（`CLASSIFIER_MODEL`）。
  **注意：测 Anthropic 模型时 `CLASSIFIER_MODEL` 必须设为 OpenAI 或 Azure 模型**，
  classifier 只支持这两家。
- 多模型跑会输出 Model Comparison Table（通过率、执行时间、P90、成本对比）。
  文档建议 **10 次迭代**才有可靠数字（LLM 非确定性）。
- 上游有[公开的历史 eval 结果归档](https://holmesgpt.dev/dev/development/evaluations/)
  （2026-01 至 05 多份），**你的改动有真实基线可比**。

**关键设施**：`tests/llm/utils/env_config.py` 支持并列对照实验：

```
ENV_CONFIGS='config1:VAR1=val1;VAR2=val2|config2:VAR1=val3'
```

同一套 case、多组环境变量、并列对比。**这就是"改了 memory 层之后收益多少"的现成实验框架**，
不需要自建。对照 `PROJECT_POSTMORTEM.md` L11：上个项目 19,254 行工装的大部分理由在这里被消掉。

**L-2. 修 HolmesGPT 的后端 issue（PR 被 merge = 外部验证）**

**L-3. robusta 平台侧**（[robusta-dev/robusta](https://github.com/robusta-dev/robusta)，
3,094★，MIT，09-13 有推送）：HolmesGPT 的上游平台，做告警路由/webhook/sink 侧的后端工作。
作为 L-1/L-2 的备选，不建议作主线（离 agent 核心较远，面试叙事弱一档）。

**为什么这条路线低风险**：不依赖自管 K8s（`before_test` 里的 kubectl 可打到 kind）、
不依赖宿主稳定性、不依赖 RL 生态成熟度。**三个上个项目致命的外部依赖全部消除。**

---

## 6. 回答 C：五个可行组合（宁缺勿滥，每条都给可证性证据）

只列接口适配已证实、且收益可证的组合。**未证实的一律不进这张表。**

### 组合 1（A 档，推荐主线）HolmesGPT + SREGym

| 项 | 证据 |
|---|---|
| 接口适配 | `agents.yaml` 一行 + 一个 driver（10KB 量级）；已有 10 个 agent 在册 |
| harness 收益可证 | 公开 leaderboard；90 题 / Lite 21 题两档；改 agent 后重跑同一套题 |
| RL 收益可证 | **57 个 oracle + `diagnosis_oracle.py` 分阶段打分 + 三轴 generator** |
| 后端厚度 | HolmesGPT 的 issue（§6.2）不受 bench 影响 |
| 风险 | 需自管 K8s + SSH/root；宿主有 panic 史；无 scalar reward 需自写 |

### 组合 2（B 档，最稳，建议第一步）HolmesGPT + 自带 274 case

| 项 | 证据 |
|---|---|
| 接口适配 | **零成本，原生** |
| harness 收益可证 | 上游有公开历史 eval 归档；`ENV_CONFIGS` 并列对照设施 |
| RL 收益可证 | **否**（LLM-judge 通过率，无 process 信号） |
| 后端厚度 | 高，见 §6.2 |
| 风险 | `RUN_LIVE=false` 离线回放**未证实**；`#2424` 报告 macOS 有 4 个 blocker，Windows 可能更多 |

### 组合 3（A 档备选）SREGym + 自写轻量 agent

不用 HolmesGPT，直接在 SREGym 上写自己的 agent（参照 `clients/stratus/`）。

| 项 | 证据 |
|---|---|
| 接口适配 | 原生 |
| harness 收益可证 | 是，leaderboard |
| RL 收益可证 | 是 |
| 后端厚度 | **低——等于又要自己造 agent，是 L11 的复发路径** |

**不推荐**，仅在"想完全掌控 agent 架构"且接受 L11 风险时考虑。

### 组合 4（C 档，仅作泛化证据）HolmesGPT + AIOpsLab

需自写 adapter（AIOpsLab 无产品 agent 先例）。**只在组合 1 或 2 已完成、
需要证明"泛化到第二个环境"时才做**，此时你有一个已验证的改动，adapter 出问题能分辨。

### 组合 5（纯后端低风险）HolmesGPT issue 驱动 + 274 case 回归

即 §5.3 的 L-1 + L-2。**放弃 RL 与 leaderboard，只做 agent 后端 + harness**。
适合"完全放弃算法岗的低风险找实习路线"。

**明确排除的组合**：
- ITBench 作开发环境（无 adapter 契约、开源仅 6 场景）
- k8s-ai-agent-benchmark（**强制依赖 Dynatrace 商业服务**，三个 agent 共享其 MCP，
  测的是"工具 + 商业遥测后端"而非工具本身）
- OpenSRE 作基座（§2.4）
- kagent 作基座（框架非成品，等于自己写 agent）

### 6.2 后端 issue 清单（实测 open，2026-09-13）

性能/超时/缓存相关 open issue 共 **36 个**。挑出与后端能力叙事最直接的：

| # | 标题要点 | 后端能力 |
|---|---|---|
| **2365** | script-based toolset 的 `subprocess.run()` **无 timeout，会永久挂死** | 超时、取消传播、进程组清理、并发隔离 |
| **2107** | toolset context bloat，需 Anthropic Tool Search 削减 | 上下文预算、工具 schema 裁剪 |
| 2332 | `cachePoint` 参数在 AWS nova-pro 上不被接受 | prompt caching 的 provider 差异 |
| 2185 | 模型收尾 turn 为空时最终答案丢失 | 流式响应边界条件 |
| 2424 | 本地跑 evals 在 macOS 上有 4 个 blocker | 跨平台工程 |
| **2426** | `101_loki` fixture 在日志摄取超时时仍删 pod，**把基础设施故障变成假阴性** | 与本项目 L8 同形 |

`#2365` 建议作为第一个 PR：纯后端、边界清晰、有真实用户价值、不需要 K8s 集群就能写测试。

HolmesGPT 已有的可讲工程机制（不必自己造，但要读懂）：server-side filtering、
JSON tree traversal、output transformer、per-tool memory limit、大结果 spill 到磁盘避免 OOM。

---

## 6.5 适配性结论（已逐组走完两侧接口，此处只写结论）

各组合的接口适配已按端点逐项核对完毕，核对过程不入库；下表只给结论。

| 组合 | 适配形态 | 适配性结论 | 档位 | 阻塞项 |
|---|---|---|---|---|
| **2** HolmesGPT + 自带 274 case | 原生，无 adapter | **已证实**：case 契约、判分器、历史基线全在仓内 | B | 仅 V1 |
| **1** HolmesGPT + SREGym | 一个 driver + `agents.yaml` 一行 | **接口已证实**；driver 规模与现有先例同级，adapter 不参与判分 | A | V1 + V4 |
| **3** SREGym + 自写轻量 agent | 原生 | 已证实，但等于重走 L11（harness 大于产品） | A | V4 |
| **4** HolmesGPT + AIOpsLab | 需自写 adapter，且无成品 agent 先例 | **未证实**：adapter 会成为新仪器（L8 复发） | C | 高 |
| **5** HolmesGPT issue 驱动 + 274 case 回归 | 不涉及外部 bench | **已证实** | — | 仅 V1 |
| — HolmesGPT + ITBench | 无文档化 adapter 契约 | 不成立 | — | — |

**三条关键结论**：

1. **组合 2 与组合 5 的适配性已完全证实**，只剩一个环境问题（V1）。
   它们是唯一"接口与收益都已证实、只差装一次依赖"的选项——**路线必须从这里起步**。
2. **组合 1 的接口适配已证实，运行前提未证实**（V4：SREGym 能否在 kind 上跑 Lite 21 题）。
   接口这一侧不会破产；会破产的是集群前提，而那是成本问题不是方向问题。
3. **组合 1 的 adapter 不参与判分**：分数由 SREGym 的 57 个 oracle 产出，driver 只搬运字符串。
   这是"低噪声"的确切含义，也是与 `PROJECT_POSTMORTEM.md` L8 的分界——
   上个项目的仪器同时观测与判分，所以能骗过自己；这里两者物理分离。
   组合 4 之所以只有 C 档，正因为它的 adapter 必须自己承担信号转换。

**破产风险清单（写 driver 之前逐项验证，任一不成立则组合 1 降级为组合 2）**：

| # | 未证实项 | 若不成立 |
|---|---|---|
| V1 | HolmesGPT 在本机能否装上并跑绿非 llm 测试 | **硬阻塞**，全部方案破产，需换基座 |
| V2 | eval 能否在 Windows 跑（上游 issue 报过 4 个 macOS 阻塞） | 需 WSL2 / Linux 宿主，不影响选型 |
| V3 | `RUN_LIVE=false` 离线回放是否真可用 | 每次 eval 都需活集群，迭代变贵 |
| V4 | SREGym 能否在 kind 上跑 Lite 21 题 | 组合 1 需自管 K8s，宿主 panic 风险回归（L10） |
| V5 | HolmesGPT 容器内能否 POST 到宿主 conductor | driver 加网络配置，非阻塞 |

V1 是唯一硬阻塞项；V2–V5 影响成本与档位，不影响方向。

---

## 7. 建议路线与硬性约束

**B → A → RL 三段，每段独立可交付。**

1. **第一步（B 档）**：HolmesGPT 跑绿自带 274 case，修 1–2 个后端 issue，
   用同一套 case + `ENV_CONFIGS` 证明改动收益。
   *交付物：merged PR + before/after 通过率表。*
2. **第二步（A 档）**：写 SREGym driver 接入，拿 SREGym-Lite 21 题分数。
   *交付物：leaderboard 成绩 + "泛化到未见环境"的证据。*
3. **第三步（RL）**：在 SREGym per-stage oracle 上做 reward，
   用 Cloud-OpsBench 的 outcome-process gap 论证为何不能只奖励最终答案。
   *交付物：RL 环境封装 + 训练曲线。*

### 硬性约束（直接来自 PROJECT_POSTMORTEM 的教训）

| 约束 | 对应教训 |
|---|---|
| 第一步没跑绿，不进第二步；第二步没有分数，不进第三步 | L2（速率与计划差一个数量级） |
| **工装代码 ≤ 产品/贡献代码的 50%**，写进 CI | L11（工装 3.3 倍，agent 从未存在） |
| 不改打分器、不改 `expected_output` 判定、不用 `--profile svelte` 作环境轴 | L7 / L8 |
| 每轮实验摘要入库（样本数、model、通过率、置信区间、是否作废） | L9（44 天空洞） |
| 开工第一天写 15 分钟面试演示脚本，每周核对"今天能讲什么" | L3（目标被代理指标取代） |
| 需求总量 ≤ 15 条，每条带放弃条件 | L5（57 条从未收敛） |
| SREGym 若需自管 K8s，**先准备第二套可运行环境**（kind + Lite） | L10（宿主报废使证据不可比） |

### 开工前必须先证伪的一件事

**HolmesGPT 的 eval 能否在本机跑起来。** 未验证项：

- Windows 上能否跑（`#2424` 说 macOS 有 4 个 blocker）
- `RUN_LIVE=false` 的离线/录制回放是否真可用（文档每个示例都显式开 live）
- 现有 K3s 能否作为 eval 目标集群，或需要 kind

**这一步不成立，本文档其余部分都是纸上的。**
上个项目最贵的教训之一就是环境问题拖到最贵的时刻才暴露。

---

## 8. 引用

**基座**：[HolmesGPT](https://github.com/HolmesGPT/holmesgpt) ·
[running-evals.md](https://github.com/HolmesGPT/holmesgpt/blob/master/docs/development/evaluations/running-evals.md) ·
[eval 历史](https://holmesgpt.dev/dev/development/evaluations/) ·
[robusta](https://github.com/robusta-dev/robusta) ·
[OpenSRE](https://github.com/Tracer-Cloud/opensre) ·
[k8sgpt](https://github.com/k8sgpt-ai/k8sgpt) ·
[kagent](https://github.com/kagent-dev/kagent) ·
[kubectl-ai](https://github.com/GoogleCloudPlatform/kubectl-ai)

**Benchmark**：[SREGym](https://github.com/SREGym/SREGym) ·
[SREGym arXiv 2605.07161](https://arxiv.org/html/2605.07161v3) ·
[SREGym leaderboard](https://sregym.com/leaderboard) ·
[AIOpsLab](https://github.com/microsoft/AIOpsLab) ·
[ITBench](https://github.com/itbench-hub/ITBench) ·
[ITBench-AA](https://huggingface.co/blog/ibm-research/itbench-aa) ·
[Cloud-OpsBench arXiv 2603.00468](https://www.alphaxiv.org/abs/2603.00468) ·
[RCAEval](https://github.com/phamquiluan/RCAEval) ·
[OpenRCA](https://github.com/microsoft/OpenRCA) ·
[k8s-ai-agent-benchmark](https://github.com/henrikrexed/k8s-ai-agent-benchmark)
