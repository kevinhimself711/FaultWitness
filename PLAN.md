# FaultWitness unblock plan

## 已知坑

G02-046 入库的机器产物记录的是 deterministic core_e2e=0.5、live 0.000。
这两个值经复盘确认分别源于规则表缺陷与标签格式 artifact。
而后续审计文档中引用的四个 baseline
(deterministic 0.8125 / no_rag 0.8750 / naive_react_single 0.8854 / naive_react 0.9167)
来自 metric-v3 的 r1–r9 运行,这批运行没有对应的 EVAL 目录,原始产物未入版本控制。
G03 重跑前必须先确认这四个数字的原始产物是否仍在 pci-2 上;
在还原之前,任何对外表述都应标注它们的来源运行与仪器版本。

## 已完成项

U1、U2、U3、U4、U5、U6、U7。

## 未完成项

治理测试已迁出 tests/governance，归入 tests/eval。

## 新问题

当前本机 Python 环境缺少项目锁定依赖，pytest 无法完成收集。
