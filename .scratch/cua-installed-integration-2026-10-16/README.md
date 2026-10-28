# 修复版 CuaDriver 接入已安装 TomorrowStar

2026-10-16，Europe/Zurich。已将固定修复版作为 TomorrowStar 的包内辅助程序接入，
保留官方 CuaDriver.app 的厂商签名与原字节。仅替换两个引擎文件并添加辅助程序及 MIT 许可证；
完整目录差异共七条，见[差异](staged-delta-02.json)。未启动应用窗口或重启现有运行。

## 安装、签名与回退

- 安装：`/Users/zhdeng/Applications/TomorrowStar.app`。
- [安装收据](installation.json)记录原包完整备份、实际安装清单、签名及保护检查。
  备份为 `/Users/zhdeng/Applications/.TomorrowStar-backups/2026-10-16-053853Z-ffb8b9b7/TomorrowStar.app`。
  原包 1421 个文件/链接的字节、目标和模式逐项一致，严格签名有效。
- 安装前、暂存、临时安装位置、安装后及备份均作 `codesign --verify --deep --strict`。
  TomorrowStar 延续本机 ad-hoc 签名，未宣称 Developer ID 或 Apple 公证。
  官方 CuaDriver 的 Team ID、厂商签名及原回退包保持，没有用本地签名冒充厂商身份。
- [回退程序](rollback.py)先核对备份全树和现有进程，再保留失败新包、恢复原包。
  安装程序在替换或立即回读失败时会自动回退。本轮未停止进程或启动 GUI。
- Python、Playwright、pyee、greenlet 及其他现有依赖保持。53 个引擎文件均回读；
  只有 `cua_driver.py` 与 `application_worker_browser.py` 更新，加入此前已验证的关闭、
  无窗口启动、scope 保留、完整快照及未知结果保护。

## 默认路径和来源

包内模块根据自身 `.app/Contents/Resources` 位置选择 `cua-driver/cua-driver`。
缺失或哈希不符会停止，不回退到外部驱动；没有写入全局环境变量或切换原有实例。
checkout 的默认外部路径仍阻断原版 0.35.2/0.35.4。

最终辅助程序 SHA-256：`f73a152949447fde0a85b8e7f1ce5e6e56cf4f6f98b1f560875a1a5d1a91132f`。
上游 `trycua/cua`，固定 base `c6cb386cf371fed3580ea1c5a238940ce4911641`，MIT。
[候选记录](candidate-cleanup.json)、[完整补丁](upstream-full.patch)、[新增清理补丁](upstream-cleanup.patch)
和[源码绑定](source-changes.json)保持可审阅。Cargo.lock 和依赖不变，未推送或发布。
这是本机固定构建，不能把同为 0.35.4 的其他字节视为该修复。

构建器新增显式 `--cua-driver` 输入，核验固定哈希并保留辅助程序原签名字节，
将许可证和来源写入包与 manifest；[checkout 补丁](checkout-code.patch)另含三项默认路径回归。

## 权限边界

安装前只读 `permissions status` 返回 unknown：没有以官方驱动自身负责身份运行的 daemon。
没有为取得结果启动它、请求授权或打开系统设置。

实际暂存/安装辅助程序的 `check_permissions(prompt=false)` 已返回 Accessibility 与
Screen Recording 为 true，且 `direct_capture_status=not_checked`；其 source 明确为
embedded 的调用宿主。**这些值属于本轮调用链，不能当作 TomorrowStar GUI 的独立 TCC 授权。**
本轮不启动 GUI，也不改写 TCC。未来 GUI 宿主缺少权限时仍须按原守卫停止；不请求前台 fallback。
原始权限响应保存于各合成 case 的私有目录。

## 暂存验收捕获的额外退出竞态

首次暂存运行完成后台附着和 scope 刷新，原 Page/同一 File 保持，但退出后 profile
只被部分删除，Python 正确报告 `cua_cleanup_unknown`。原失败 runtime 的 closed=false 保留。
独立检查确认主进程与 daemon 已退出，残留 41 个文件/链接归档为私有证据，没有补写成功。

实际删除函数忽略一次 `remove_dir_all` 错误。只在新私有 daemon 的目录删除入口注入一次
`ENOTEMPTY`，准确复现同一清理拒绝；这验证该错误路径，不能唯一断言首次自然失败的 errno。
修复限于已确认退出后的本地 profile 删除：最多八次 25 ms 等待，只重试 DirectoryNotEmpty，
每次重查原所有权标记。其他错误、标记缺失/变化及未确认退出都保持拒绝。
没有重发 MCP、浏览器动作或未知 intent，没有延长原 3 秒/2 秒/15 秒业务期限。

| 原生对照 | 结果 |
| --- | --- |
| 旧候选 + 一次 ENOTEMPTY | 保留 `cua_cleanup_unknown`，故障 receipt 指向本轮 daemon。 |
| 修复候选 + 同一故障 | [通过](staged-cleanup-green-result.json)，原页/附件和清理均确认。 |
| 修复候选 + 持续 ENOTEMPTY | [预期拒绝通过](staged-cleanup-persistent-verification.json)，九次尝试后仍保留目录。 |
| 修复候选 + 所有权标记变化 | [预期拒绝通过](staged-cleanup-marker-verification.json)，不再次删除。 |
| 修复暂存包，无注入 | [通过](staged02-scope-result.json)，原页/附件、来源上限、旧绑定失效均确认。 |

持续拒绝对照第一次归档时仍观察到退出中的 Chrome helper，控制器立即停止归档。
原失败保留。后继仅只读等待 helper 退出后归档，没有发信号或修改业务时限。
所有失败 profile 和控制器回执均独立保存。

## 验证记录

- 默认包内选择的三项新增回归保留 red/green；helper 缺失或不符不得执行或回退。
- Python 完整默认离线：[951 passed，119 deselected](offline-final.log)。该轮执行时为前一固定 SHA；
  后继只换辅助程序 SHA，最终实际包内专项、真实原生对照与 core/macOS 回归另行绑定。
- 暂存最终专项：[60 passed，30 deselected](staged-tests-final.log)；实际安装专项：
  [60 passed，30 deselected](installed-tests.log)。显式 loader 证明生产模块来自相应 App。
- core 986 passed、1 ignored；macOS 570 passed、6 ignored。桌面交互 ignored 项保持跳过。
- [暂存搬移验收](staged02-bundle-acceptance.json)和[实际安装搬移验收](installed-bundle-acceptance.json)
  均通过：内置 Python/Playwright、默认配置、Host/CSRF 和父 EOF 关闭；worker 不自动启动。
- 最终实际原生结果、权限归属和新进程清理见[验证汇总](verification.json)；
  [安装后验收](post-install-acceptance.json)确认安装字节及备份签名仍有效。

| 实际安装路径的原生场景 | 结果 |
| --- | --- |
| 310 秒真实暂停后 scope 自动刷新 | [通过](installed-long-scope-result.json)，原 Page/同一 File、原 transport/daemon、来源上限保持，旧绑定失效。 |
| 点击完成后丢失回执 | [通过](installed-unknown-result.json)，实际选择一次；原 15 秒期限，未知 intent 保留，后续五次 tick 与强制刷新没有再派发。 |
| 完整 semantic_v2 快照 | [12 次通过](installed-snapshots-result.json)，约 65–175 ms；原 Page/同一 File 保持。 |

上述三项使用实际安装包自己的 Python、依赖、引擎及默认辅助程序路径，没有
`TS_CUA_DRIVER_BINARY` 覆盖或固定哈希 monkeypatch。生产模块路径和哈希分别保存在
各 `installed-*-execution-source.json`。Space 均固定为 1，未采到自有激活或上屏；
长暂停最大采样间隙约 875 ms，不能声称逐帧零闪现。

[最终保全](preservation.json)：4157 个历史文件、2192 个此前私有原件、原候选源码/二进制及
官方 Cua/rollback 均保持；原包 1421 项在备份中一致，安装包 1423 项与已验收暂存包一致。
现有进程身份及私人记录/PDF/附件/设置摘要保持。九个混合诊断/对照 cohort 均已结束，
新增进程、活跃 profile 与 socket 为零，四份失败 profile 独立归档。
这些不同输入不能合并为成功率。没有重新读取真实 ATS DOM 或把历史 page_open 当成 live DOM。

[844 个本轮私有原件的哈希绑定](private-raw-binding.json)保留完整日志与失败字节。
所属票保持 open，保留 GUI 宿主本身的独立 TCC 验收项；本轮安装与隔离合成交付已完成。

初次包内专项三项失败来自测试仍假设外部驱动默认；外部路径测试现明确该测试上下文，
新包内默认路径另由新增回归和真实包内执行验证，没有放宽断言。所有原失败保留。
一次跨卷 rename 未执行成功，原红测随后按字节复制进私有目录；没有丢失失败记录。

原始诊断目录：`/Users/zhdeng/Library/Application Support/TomorrowStar/diagnostics/cua-installed-integration-20261016-01a1360f`，0700。
本轮真实 ATS、模型、网络上传及最终 Submit 为零。未启用桌面代理、自动授权、前台投递或未知结果重发。
跨 daemon/owner 到期保页、GUI 首次启动的 TCC、逐帧绝对零闪现与真实 ATS 不新增保证。
