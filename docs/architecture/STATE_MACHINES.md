# State Machines Architecture View

## 本阶段边界

本文件在 I-0004 冻结状态域、唯一写入者、权威存储和跨域协调边界。四套逐转换机器可读 YAML、Actor/Guard/Command/Event、可达性验证和由 YAML 校验的 Mermaid 图由 I-0005 提交；在此之前本文件不冒充转换表的单一事实源。

## 四层状态域

```mermaid
flowchart LR
    incident["Incident Lifecycle\nowner: Control API"]
    task["Runtime Task\nowner: Scheduler"]
    graph["Agent Graph State\nowner: Agent Worker"]
    action["ActionTransaction\nowner: Action Executor"]

    incident -->|"ScheduleTask command / TaskScheduled event"| task
    task -->|"leased execution / checkpoint event"| graph
    graph -->|"ActionProposal command"| action
    action -->|"ActionResult event"| graph
    graph -->|"InvestigationResult event"| incident
    task -->|"TaskTerminal event"| incident
```

| State domain | 唯一写入者 | 权威存储 | 并发控制 |
| --- | --- | --- | --- |
| Incident Lifecycle | Control API / Incident Service | PostgreSQL incident store | `state_version` |
| Runtime Task | Scheduler | PostgreSQL task store | lease `fencing_token` |
| Agent Graph State | Agent Worker | PostgreSQL checkpoint store | checkpoint `state_version` |
| ActionTransaction | Action Executor | PostgreSQL action store | `state_version` + action idempotency |

Trace/Eval 与 Artifact/Dataset 也是独立状态资产，分别由 Trace Instrumentation 和 Eval/Data Worker 以 append-only version 管理；它们不合并进四个运行状态机。

## 不变量

- 任何组件都不能以数据库共享、框架 callback 或补偿任务为理由修改其他 owner 的状态。
- Incident terminal state 不原地改写；后续反馈和审计追加为新事件。
- Worker 在 lease 丢失后不能提交 checkpoint、ToolResult 或 ActionProposal。
- Agent Graph 只能形成 ToolCall 和 ActionProposal，不能形成已执行 action。
- R2 没有匹配 tenant、environment、resource version 和 digest 的有效 ApprovalGrant 时不能进入执行。
- `UNCERTAIN` 只能 reconciliation 或人工处置，禁止自动重复外部动作。
- cancel 是请求，在安全点生效；已经可能产生副作用时先验证或升级。

## I-0005 固定入口

I-0005 必须在上述所有权不变的前提下增加四个状态机 YAML、OpenAPI/AsyncAPI、核心类型目录和 conformance validator。若发现所有权或信任边界必须改变，先写新 ADR 并重新运行 EVAL-G00-004，不能在接口实现中静默漂移。

## 关联视图

- [System Context](SYSTEM_CONTEXT.md)
- [Container Architecture](CONTAINER_ARCHITECTURE.md)
- [Data and Control Flow](DATA_AND_CONTROL_FLOW.md)
- [Deployment and Trust Boundaries](DEPLOYMENT_AND_TRUST_BOUNDARIES.md)
