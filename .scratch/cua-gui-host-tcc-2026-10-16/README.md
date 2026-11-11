# TomorrowStar GUI 宿主 TCC 独立核验

2026-10-16，Europe/Zurich。所属票：[调查 CuaDriver 0.35 后台浏览器附着拒绝](../application-worker-stability/issues/10-cua-035-background-attach.md)，领取人 root。

**身份独立核验完成；辅助功能和录屏均未授予。生产后台调用安全拒绝，完整浏览器验收仍受阻。**

## 实测结果

| 检查 | 结果与证据 |
| --- | --- |
| 实际原生宿主 | 安装路径由 LaunchServices 以 `-n -g -j` 启动；PID 32742，PPID 1，系统 responsible PID 32742 |
| Python | PID 32750，系统 responsible PID 32742 |
| 独立只读 MCP daemon / proxy | PID 32752 / 32760，系统 responsible PID 均为 32742；未设置 advisory host_bundle_id |
| 原生权限 | `AXIsProcessTrusted()` = false；`CGPreflightScreenCaptureAccess()` = false |
| 嵌入式 MCP 权限 | 两项均 false，来源 `host`，daemon PID 匹配；direct capture = `not_checked` |
| 实际生产后台入口 | 默认包内驱动、原 capability 和权限守卫，返回 `cua_permissions_required`，在 browser_prepare 前停止 |
| 原生窗口/激活 | 335 次独立采样，312 次观察到宿主；窗口数 0、激活 0、上屏 0，最大采样间隔 320 ms |
| Chrome / Space | 375 次采样；没有新自有 Chrome，Space 固定 1，最大采样间隔 188 ms |
| 普通后端 | 暂存最终包及实际安装包的隔离合成验收通过：内置运行时、协议、Host/CSRF、无 worker 自动启动、父管道 EOF 退出 |
| 回归 | 14 项相关测试通过；170 文件 Ruff 检查及格式检查通过；diff 空白检查通过 |

[原生 API 结果](native-tcc.json)、[后台调用结果](background-result.json)、
[独立采样](background-observation.json)、[安装后合成验收](installed-bundle-acceptance.json)。

## 最小改动与签名边界

普通 GUI 入口原先会创建并激活窗口，因此不能直接用于本轮后台核验。
新增 `--background-check gui-host-<唯一标记>` 分支，在创建 AppDelegate、窗口或读取私人配置之前
选择 `.prohibited` 激活策略。分支只运行固定随包 Python 脚本，不能选择任意脚本或命令。
输出只能进入 diagnostics 下新建、无符号链接的 0700 私有子目录；子脚本再次检查所有者、模式与路径。
诊断不调用 TCC 请求 API、不打开设置、不修改 TCC 数据库、不使用前台回退。

实际安装包只变化四个路径：原生可执行文件、固定诊断脚本、构建清单和资源签名。
全部引擎文件、已复验驱动、依赖及普通后端保持原字节。
驱动 SHA-256 仍为 `f73a152949447fde0a85b8e7f1ce5e6e56cf4f6f98b1f560875a1a5d1a91132f`。
当前安装清单 SHA-256 为 `55917895f99f9488aa6fc69fc8cec57d95a2d0dcfbf200801b90ca730dc009b3`。

安装包仍为 `dev.tomorrowstar.desktop` 的本地 ad-hoc 签名，无 Team ID、Developer ID 或公证，
严格深度签名核验通过。当前 CDHash/指定要求为 `481ada4de2bb03f0ee628abbbb585da750dd6bb0`。
本轮权限值只描述这个最终安装身份，不能据此推断历史签名的授权。
原生代码及资源变更会改变 ad-hoc 指定要求；本轮没有复制或迁移旧授权。
没有重签、替换官方 CuaDriver.app。

## 保全与回退

安装前完整备份的 1,423 个文件/链接保存在
`/Users/zhdeng/Applications/.TomorrowStar-backups/2026-10-16-082222Z-2f4b838f/TomorrowStar.app`。
本轮安装为 1,424 个文件/链接；先复制到同目录临时包，再原子替换，并在失败时回退。
[安装收据](installation.json)和 [rollback.py](rollback.py)保留精确路径、哈希与保护检查。
回退脚本只在没有活动 TomorrowStar 宿主/后端时恢复，不停止现有进程；失败后继包另存保留。
前一轮的 1,421 项原包备份也独立保留。

最终回读核对原 worker 私有记录/PDF/附件/设置及既有进程身份、4,273 个历史文件、
3,036 个此前私有原始文件、旧候选与源码、官方驱动及 rollback，均保持。
[终态保全收据](preservation.json)另核对本轮新进程、socket 和 profile 无遗留。
原生产 runtime 在权限拒绝时写入的 `closed=false` 原样保留；独立终态检查不改写该字段。

原始日志保存在两个新建的持久私有 0700 目录：

- `~/Library/Application Support/TomorrowStar/diagnostics/cua-gui-host-tcc-20261016-01a1360f`
- `~/Library/Application Support/TomorrowStar/diagnostics/gui-host-20261016-01a1360f-01`

其精确文件哈希分别绑定在本目录的 raw binding 收据中。
输出目录拒绝测试的首次 red、green、首次暂存包及格式更正后继均保留，没有覆盖原记录。

## 验收边界与下一步

本轮完成 GUI 宿主真实身份、只读权限和后台拒绝路径的独立核验。
由于两项 TCC 权限均未授予，没有进入浏览器创建，也没有本轮 GUI 链的 Page/File、scope
或未知回执故障验收。此前包内路径的合成通过仍有效保留，不把它重复计作 GUI 宿主通过。
后台诊断脚本的有权限浏览器分支本轮未执行，后续仍须实测。

用户要求不切前台且不放宽守卫，所以本轮没有弹出授权、打开系统设置或修改权限。
下一步须在用户授予当前 TomorrowStar 身份的辅助功能及录屏权限后，以相同后台入口复验。
在此之前 ticket 保持 open。真实 ATS、模型、上传、Submit 和现有进程重启均为零。

## 复验输入

使用 checkout 的 locked Python 3.13 启动器，离线、无依赖同步：
`uv --cache-dir /private/tmp/ts-fixed-space-uv run --locked --offline --no-sync python -B`。
测试限定 `tests/test_macos_portal.py tests/test_cua_mcp_lifecycle.py`，没有覆盖默认 marker 选择。
原生最终编译目标为 `arm64-apple-macos13.0`，使用 AppKit/WebKit 与原生只读 AX/CG API。
公开源、安装全树、备份全树及诊断输入的摘要见本目录各收据；不依赖当前 checkout 的可变文字来替代当次字节。
