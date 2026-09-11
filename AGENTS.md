本文件是经验记录,不是契约。发现某条规则错了或过时了,直接改它,不要为了"遵守"而绕路。
这里刻意不用"冻结/不得/零容忍"这类词——真正需要那种强度的约束在各 Gate Plan 里,
在这里重复一遍只会制造两个真相来源。

## 1. 安全不变量

- Incident, Runtime Task, Agent Graph, and ActionTransaction remain separate state machines.<br>Tenant identity comes only from authenticated context; request bodies cannot override it.
- The Agent cannot execute arbitrary shell commands or write directly to Kubernetes.<br>Action Executor is the sole write boundary and enforces policy, approval, idempotency, postconditions, and compensation. R2 requires a valid immutable approval digest.
- At-least-once delivery pairs with idempotent actions; UNCERTAIN outcomes never blind-retry.<br>Ground Truth and locked tests are inaccessible to Agent runtime.
- Never store private chain of thought, credentials, decrypted secrets, or restricted source bodies.<br>Public CI receives no privileged cluster, provider, or production-like secret.
- Privileged infrastructure, chaos, and live-model work requires explicit user authorization. Once granted for the active task, do not ask repeatedly for the same authority.

Changes to these invariants require an ADR, migration/replay analysis, and targeted tests.

## 2. 工作方式

- 每轮开始:读 `PLAN.md` + `git log --oneline -10`
- 每轮只做 PLAN.md 里一个未完成项,完成即 commit 并退出; 每轮结束:勾掉完成项;本轮踩到的坑追加到 PLAN.md 的「已知坑」<br>**完成一个工作单元就 commit,不要攒。**单次超过 30 个文件说明单元切太大; 每轮完成即 push main
- 连续两次纯治理动作而没有新的运行时观测 = 死锁,绕过非语义阻塞点继续; G00–G02 资产不可变,复现走 `gate/G##-v#` tag<br>**治理检查不阻塞代码变更。**`verify-docs` 手动跑;CI 只跑 ruff + pytest + eval 证据检查; **eval 产物必须入 git。**运行产生的 artifact 不入库 = 证据不存在

## 3. 文档政策

判据一句话:**能从 git diff 或代码里读出来的,不要写;只存在于人脑里的,必须写。**

### 不要写(git 已经无损记着了)

- 每个工作单元的生命周期记录、状态字段、完成时间、候选 SHA
- "本次改了哪些文件"、"实现了什么功能"这类复述 diff 的内容
- Gate 尝试记录、activation record、corrective record、closure 镜像
- 任何需要和另一份文档保持同步才成立的文档

### 必须写(写在 PLAN.md 或 docs/engineering/)

- **为什么**:试过哪条路、为什么放弃。git 里只留下"没有那次提交",读不出来
- **下一步**:总目标里还剩什么
- **踩过的坑**:环境陷阱、检查方法本身的缺陷、被证伪的假设。不写下次会原地再踩
- **代价**:一个错误花了多少轮、多少版本、多少作废运行。没有数字的教训不会被当真

### 必须入 git(不是文档,是证据)

- 每次 eval run 的机器可读产物。产物不入库 = 这次运行没发生过
- 结论引用的每个数值,都要能指到产生它的那个已入库文件

### 怎么写

- 每条教训带上具体代价和发生时间,不写成抽象规则
- 按可操作性排序,不按主题分类
- 假设被证伪就明确记下来——留着一个错误假设比承认它更贵
- 不要为了让标签好看去改判据或谓词;记录实际落在哪个分类即可
- 结论先行,证据跟上,不要把执行日志当成汇报
- 明确区分**实测**、推断、**未验证**三种断言

### 新建文档前先问

这份文档,三个月后一个没参与过的人打开它,会得到 git log 给不了的信息吗?
答案是否,就不要建。

## 4. 验证

- 快速检查: `uv run ruff check src tests`、`uv run pytest -q`、`git diff --check`; 完整目标: `make verify-fast`; 文档检查: `make verify-docs` 手动运行; CI 只运行 ruff、pytest 与 eval 证据检查。
