本文件是经验记录,不是契约。发现某条规则错了或过时了,直接改它,不要为了"遵守"而绕路。
这里刻意不用"冻结/不得/零容忍"这类词——真正需要那种强度的约束在各 Gate Plan 里,
在这里重复一遍只会制造两个真相来源。

## 安全不变量


- Incident, Runtime Task, Agent Graph, and ActionTransaction remain separate state machines.
- Tenant identity comes only from authenticated context; request bodies cannot override it.
- The Agent cannot execute arbitrary shell commands or write directly to Kubernetes.
- Action Executor is the sole write boundary and enforces policy, approval, idempotency,
  postconditions, and compensation. R2 requires a valid immutable approval digest.
- At-least-once delivery pairs with idempotent actions; UNCERTAIN outcomes never blind-retry.
- Ground Truth and locked tests are inaccessible to Agent runtime.
- Never store private chain of thought, credentials, decrypted secrets, or restricted source bodies.
- Public CI receives no privileged cluster, provider, or production-like secret.
- Privileged infrastructure, chaos, and live-model work requires explicit user authorization. Once
  granted for the active task, do not ask repeatedly for the same authority.

Changes to these invariants require an ADR, migration/replay analysis, and targeted tests.

## Active verification

The canonical local command is:

    uv run python -m faultwitness_dev verify-fast

It checks active schemas and contracts, lint, tests, Markdown, UTF-8, links, clean diffs, and the
local repository publication audit (lockfiles, pinned Actions, licenses, ownership, secret/path
leaks, and SBOM). It does not scan historical lifecycle transitions, infer changed-path
authorization, bind evidence to HEAD, or rerun Gate Evals. Ubuntu and Windows CI are advisory
cross-platform signals; they are not remote branch-merge prerequisites.

## 工作方式
- 每轮开始读 PLAN.md 与 git log --oneline -10。
- 每轮只做一个未完成项，完成即 commit。
- 每轮结束更新 PLAN.md 的已知坑。
- 在语义分支工作，不直接推 main。
- 治理检查不阻塞代码变更；verify-docs 手动运行。
- eval artifact 必须入 git。

## 文档政策

判据一句话:**能从 git diff 或代码里读出来的,不要写;只存在于人脑里的,必须写。**

## 验证
`ruff check src tests`、`pytest -q`、`make verify-fast`；文档检查使用 `make verify-docs`。
