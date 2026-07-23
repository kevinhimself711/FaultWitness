# BC-PROC-0004: Generic Transport Error Without Stage Attribution

Status: corrected forward on 2026-07-23

## 现象

K3s restore 后的 fresh-session probe 返回 `exit=2`，上层只得到 generic
`remote_command_or_transport_failed`，无法区分 SSH 建连、权限通道、远程 shell、K3s
恢复还是 readiness inventory 阶段。

## 可独立复现

在恢复 probe 中使用未配置相同权限与身份的 SSH channel，同时让上层只保留统一 exit
category。probe 失败，但日志不能指出 channel 与 stage，容易被误判为传输抖动。

## 根因

fresh-session probe 使用了错误的 non-privileged channel。`df644f1` 将它切换到已验证
的 privileged SSH channel 后问题消失。全局连接次数不是根因。

## 当时的错误处置

`e324cad` 先增加全局 `ConnectionAttempts=3`；`8916098` 还允许在满 900 秒后把 generic
error 标记为 `operator_adjudicated_pass`。前者没有修复通道错误，后者掩盖了可定位的
失败。

## 正确处置

先以最小 probe 比较 stage/channel，保留结构化失败分类；修复 owning channel 后只重跑
K3s restore 与 fresh-session phase。generic transport error 保持阻塞，不按经过时间
推断成功。

## 防复发规则

- GR-12：已验证根因后必须移除人工裁定通过路径。
- 每个远程错误至少包含 operation、stage、channel class 和 sanitized exit category。
- 本次前向修正移除 `operator_adjudicated_pass`；G01 已关闭报告和历史提交保持不变。

## 裁定路径存在期间

该路径由 `8916098` 于 2026-07-23 06:33:46 -04:00 引入，在 `df644f1` 已证明通道根因
后失去适用场景，并由本复盘维护提交移除。没有当前仍未被根因修复覆盖的合法 pass
场景；未知 transport error 只能是阻塞失败。
