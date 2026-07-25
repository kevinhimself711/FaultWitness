---
active_gate: G02
active_gate_status: in_progress
active_iteration: null
next_iteration: C-G02-003
last_closed_gate: G01
---

# FaultWitness

FaultWitness 是一个面向微服务事故调查、受控修复与持续优化的多租户 Agent Runtime 项目。

当前状态：G00、G01 已关闭；G02 正在执行。I-0020、I-0023、I-0025 与 I-0027 均已因
确定性失败终态关闭且负面证据完整；I-0024 与 I-0026 已完成前两轮 runner/transport
纠错。I-0028 已用真实 Windows child process 证明 byte-exact transport 并关闭；I-0029 因
远端 Python 3.8 compatibility 缺陷终态失败。I-0030 已用实际受管 Python 3.8.20 完成
兼容性纠错并关闭；I-0031 因固定 probe 镜像未离线导入而终态失败。I-0032 已将两个固定
probe 镜像纳入离线 staging/import inventory 并关闭；I-0033 因 containerd import alias
解析缺陷终态失败。I-0034 已完成精确 alias corrective 并关闭；I-0035 随后证明对象读取
probe 错用隐含 `ListBucket` 的 `mc stat`，现已终态失败。未实施的 I-0036/I-0037 已按新
命名治理退役；C-G02-001 已以真实 GetObject 对照证据关闭。A-G02-001 的真实访问矩阵在
LangSmith canonical-owner cell 确定性失败并终态关闭；C-G02-002 已用真实 credential read
seam 完成单根因修复。A-G02-002 在 expected-allow baseline-agent egress seam 无进展后终态
失败；C-G02-003 是下一单根因 corrective，A-G02-003 是与其分离的计划 Gate attempt。
任何终态记录都不会重开。

## 权威资产

- [最终项目规划](docs/blueprint/FINAL_PLAN.md)
- [G01 Gate Report](docs/gates/G01/REPORT.md)
- [G02 Master Plan](docs/gates/G02/PLAN.md)
- [阶段索引](docs/roadmap/PHASES.md)
- [项目状态](PROJECT_STATE.yaml)
- [协作规则](AGENTS.md)
- [AI 开发与复盘日志](docs/engineering/AI_DEVELOPMENT_LOG.md)

## 当前边界

- 不把 G01 平台地基包装为已经完成的 Agent 产品。
- 不提交原始 JD、面经、密钥、私有 Trace 或受限数据。
- I-0018 已交付 locked-test/ground-truth 隔离、160 行预登记和三个验证接口；I-0024
  已前向补齐并单测 EVAL-G02-008 证明缺失的 candidate-bound provisioner/collector。
- EVAL-G02-012 在 candidate-binding 准备时证明 Windows text-mode 将 LF 改写为 CRLF；
  十四个 Gate phase、matrix cell、破坏性实验和模型调用均为 0。EVAL-G02-013 已通过 4/4
  本地 byte-exact cases。EVAL-G02-014 随后证明 `gate_probe.py` 与远端 Python 3.8 不兼容；
  访问 cell、破坏性实验和模型调用仍为 0。EVAL-G02-015 已通过真实 Python 3.8 import 与
  UTC-aware timestamp 两个本地 cases。EVAL-G02-016 随后证明固定 `minio/mc` probe 镜像
  未进入 K3s 且节点 Docker Hub pull 超时；访问 cell、破坏性实验和模型调用仍为 0。
  EVAL-G02-017 已通过 3/3 本地 staging cases，保持 30-image SUT digest 不变；I-0033 才可
  再次编排冻结 phase。EVAL-G02-018 的四个 preflight 通过，但 `minio/mc` import 只产生
  `index.docker.io` source alias，冻结 verifier 查找 `docker.io` source 时确定性失败；后续
  matrix、破坏性实验和模型调用均为 0。
  EVAL-G02-019 已通过 3/3 本地 alias-resolution cases，wrong-digest alias 保持 fail closed。
  EVAL-G02-020 的四个 preflight 与 deployment 通过，前 24 个 database access cells 通过；
  第一个对象读取 cell 因 `mc stat` 隐含需要未授权的 `ListBucket` 而确定性失败。后续 phase
  与模型调用为 0；C-G02-001 已将读取修正为精确 `GetObject` probe，3/3 本地分支与真实
  `minio/mc` allow/deny 对照均通过。

代码、API、Schema 和标识符使用英文；设计、评测和复盘文档以中文为主。
