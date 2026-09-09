本文件是经验记录,不是契约。发现某条规则错了或过时了,直接改它,不要为了"遵守"而绕路。
这里刻意不用"冻结/不得/零容忍"这类词——真正需要那种强度的约束在各 Gate Plan 里,
在这里重复一遍只会制造两个真相来源。
## 安全不变量
- Incident, Runtime Task, Agent Graph, and ActionTransaction remain separate state machines.
- Tenant identity comes only from authenticated context; request bodies cannot override it.
- The Agent cannot execute arbitrary shell commands or write directly to Kubernetes.
- Action Executor is the sole write boundary and enforces policy, approval, idempotency, postconditions, and compensation. R2 requires a valid immutable approval digest.
- At-least-once delivery pairs with idempotent actions; UNCERTAIN outcomes never blind-retry.
- Ground Truth and locked tests are inaccessible to Agent runtime.
- Never store private chain of thought, credentials, decrypted secrets, or restricted source bodies.
- Public CI receives no privileged cluster, provider, or production-like secret.
- Privileged infrastructure, chaos, and live-model work requires explicit user authorization. Once granted for the active task, do not ask repeatedly for the same authority.
Changes to these invariants require an ADR, migration/replay analysis, and targeted tests.
## 工作方式
- 每轮开始:读 `PLAN.md` + `git log --oneline -10`
- 每轮只做 PLAN.md 里一个未完成项,完成即 commit 并退出
- 每轮结束:勾掉完成项;本轮踩到的坑追加到 PLAN.md 的「已知坑」
- **完成一个工作单元就 commit,不要攒。**单次超过 30 个文件说明单元切太大
- 在语义分支工作,不直接推 main
- 连续两次纯治理动作而没有新的运行时观测 = 死锁,绕过非语义阻塞点继续
- G00–G02 资产不可变,复现走 `gate/G##-v#` tag
- **治理检查不阻塞代码变更。**`verify-docs` 手动跑;CI 只跑 ruff + pytest + eval 证据检查
- **eval 产物必须入 git。**运行产生的 artifact 不入库 = 证据不存在
## 文档政策
见本节 U6 的逐字政策。
## 验证
- 快速检查: `uv run ruff check src tests`、`uv run pytest -q`、`git diff --check`; 完整目标: `make verify-fast`。
- 文档检查: `make verify-docs` 手动运行; CI 只运行 ruff、pytest 与 eval 证据检查。
