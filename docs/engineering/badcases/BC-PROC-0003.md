# BC-PROC-0003: Repeated Fifteen-Minute Stability Window

Status: recorded; prevention accepted; tooling pending

## 现象

G01 对相同验证目标执行了两个独立的 15 分钟 readiness observation。两轮都在窗口
结束后遇到非特化 transport error，第二轮没有增加新的 workload-stability 证据。

## 可独立复现

让稳定检查在 900 秒内持续返回 Ready，并在最后一次证据传输时失败。若 runner 没有
持久化“窗口本体已通过”的阶段结果，重新执行完整 Gate Eval 会再次等待 900 秒。

## 根因

稳定窗口没有独立、可寻址的 phase result，也没有以 candidate artifact digest、环境
指纹和检查实现版本定义复用键；窗口本体与收尾传输错误混为一个全有或全无调用。

## 当时的错误处置

重复整轮窗口并增加基于 wall time 的 operator adjudication，而不是先区分 observation
结果、证据持久化和传输 channel。

## 正确处置

窗口通过后原子写入带采样范围、artifact/config digest、environment fingerprint 和
checker version 的结果。后续非相关步骤消费该结果；只有这些绑定项或窗口实现变化时
才重跑。

## 防复发规则

- GR-06：不变 artifact/environment 的稳定窗口只运行一次。
- 稳定 phase 与 evidence transport phase 使用不同错误类型和独立结果。
- 完整 Gate retry 必须跳过已通过且仍满足绑定条件的稳定 phase。
