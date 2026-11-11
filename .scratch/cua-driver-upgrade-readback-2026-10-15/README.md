# CuaDriver 升级与隔离兼容性回读

客户端日期：2026-10-15，Europe/Zurich。用户明确要求“升级cua-driver”。

**安装版本已由 0.21.0 升级为 0.35.2。** 当前 CLI、应用 Info.plist、签名和发布包文件摘要一致。旧 0.21.0 的完整应用保留在 `/Applications/.CuaDriver-rollback-20261014-01a1360f.app`，当前 CLI symlink 仍指向 `/Applications/CuaDriver.app/Contents/MacOS/cua-driver`。

## 安装与签名

目标为[官方 0.35.2 发布](https://github.com/trycua/cua/releases/tag/cua-driver-rs-v0.35.2)。安装时下载 universal 应用包，SHA-256 为 `84c4cb9abd3f92324a34a191a77c58027881454168a6a84fc6d6767b3760de2f`，与官方 SHA256SUMS 一致。当前原生可执行文件 SHA-256 为 `20417e3c7168f3554bf97192e1f6d245844b4db694fb6d87c15b83f0609d94ad`。

官方脚本会停止旧 Cua daemon；为保留用户现有运行，本轮使用同一官方签名应用包，以 macOS `renamex_np / RENAME_SWAP` 原子交换目录。没有运行 daemon-stop、权限重置、卸载或浏览器关闭步骤。安装实现、发布包摘要和原安装输出保存在[升级原始记录](../cua-driver-upgrade-2026-10-14/installation-readback.json)与[安装代码](../cua-driver-upgrade-2026-10-14/install_verified_bundle.py)。

安装与回读都通过 `codesign --verify --deep --strict`，并验证新包满足旧包的 designated requirement；Team ID 保持 `YCK386LBJ7`、bundle ID 保持 `com.trycua.driver`。初次 requirement 比较漏了源码前缀 `=`，准备错误保留于原升级目录；修正后才安装。没有通过清空 TCC 记录处理这个错误。

[当前读回](readback.json)确认：新包与已验证发布包的7个文件一致；回退包与旧包7个文件一致；原签名要求仍满足。权限在真实新私有 daemon 的 `check_permissions` 响应中读回，Accessibility / Screen Recording 均为 true。

现有进程未重启；已运行的 daemon 不因磁盘替换自动变成新版本。后续新启动的实例使用 0.35.2。TomorrowStar 已安装应用的1,419个文件保持，没有更新它的代码或打包内容。

## 真实 MCP 复验及兼容性边界

[新版原生复验](../cua-mcp-native-verification-2026-10-15/README.md)完整保留失败与后继结果。

- 0.35.2 的传输专项4项通过：真实 MCP 后端先退出、保持输出写端时关闭、原样协议响应、丢失成功只读回执后不重复派发。
- 保持输出写端开放时 close 为0.099115秒，低于原2秒期限；读取线程和流均回收。
- 4个实际响应帧与原生输出逐字节匹配。只读回执丢失后，原生请求计数仍为1；再次调用与后续 `browser_click` 尝试均在客户端拒绝，原生点击派发0次。
- 浏览器集成预检遇到实际兼容性限制：`browser_prepare(existing_profile)` 因可能把 Chrome 带到前台而拒绝。没有切换 foreground delivery，没有点击、投递或授权 UI 操作。**新版完整后台浏览器接入与真实变更回执丢失尚未验收。**

这次升级不证明冷启动 Dock 上游来源已解决。原冷启动票保持开放；新版后台附着限制另由[调查 CuaDriver 0.35 后台浏览器附着拒绝](../application-worker-stability/issues/10-cua-035-background-attach.md)跟踪。

## 保全与原始诊断留存

本轮回读确认：现有 worker、Cua、浏览器进程身份和私人页面记录/附件/设置摘要保持；3,657个旧封存文件、127个执行源码输入、44个前代新增记录无变。详见[保全读回](readback.json)和[历史清单](history-readback.json)。

中断后，2026-10-14 的原始私有临时诊断目录已经不可读取。仓库内的失败日志、结构化结果、摘要和脚本仍保留；不能把现存摘要当成仍可回读的原始协议文件。安装发布包的临时下载件同样不在，但安装时的校验记录与当前已安装/回退包的字节、签名仍可复核。该留存缺口明确保留，不重新构造原始记录。

2026-10-15 的新原始协议、stderr、权限/进程快照与浏览器预检日志改存到独立持久私有诊断目录；公开包仅保留必要合成字段和摘要。原始诊断路径与摘要见[私有证据绑定](../cua-mcp-native-verification-2026-10-15/private-evidence-binding.json)。

当前本轮自有 PID/profile/socket 已全部退出；现有进程控制动作、真实 ATS、模型调用及最终 Submit 均为0。后续复跑应使用新的空白目录，不向本包写入。
