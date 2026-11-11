# driver-owned 后台生命周期：上游准入复核

2026-10-15，Europe/Zurich；执行人 root。
对应[调查 CuaDriver 0.35 后台浏览器附着拒绝](../application-worker-stability/issues/10-cua-035-background-attach.md)。

**完整后台附着未恢复。** 官方稳定0.35.4与本轮固定主分支没有提供满足要求的
无窗口后台 driver-owned 启动入口。另发现会话结束会清理 driver-owned 浏览器，
不能直接代替当前刷新 Cua scope 时保留 Page/附件的生命周期。
没有执行无法证明安全的浏览器启动；票保持 open。

## 核对范围与实际版本

本机安装仍为0.35.2，没有升级或替换安装目录。
本轮将官方0.35.4应用包暂存在独立持久私有目录，未启动其 daemon。

| 输入 | 固定身份 |
| --- | --- |
| 官方稳定发布 | [0.35.4](https://github.com/trycua/cua/releases/tag/cua-driver-rs-v0.35.4)，提交 `d74a9cab3fb2e80ab7f0cef47025ec828586ea75` |
| 本轮主分支快照 | `dd6e146792951ba41ac7169d5531860595d06742`，2026-10-15T20:24:41Z |
| 官方 universal archive | SHA-256 `97d5ea2fd446331947c717c433d4cf5aae063f4824e1ba24303c4696184ec52e`，与官方 SHA256SUMS 和发布记录一致 |
| 候选原生可执行文件 | SHA-256 `d0fff7f17a79ddf862ae187fa828f83c77de43c078d4964470e9ad93f5f1e88f` |
| 签名 | Developer ID Cua AI Inc，Team ID `YCK386LBJ7`，bundle ID `com.trycua.driver`；严格验签并满足原安装的 designated requirement |

[候选验证记录](candidate.json)、[实际 CLI schema](browser-prepare-schema.txt)、
[源码与准入审计](eligibility.json)和[执行输入摘要](execution-inputs.json)分别保留。
上游源码副本未修改，MIT [license](upstream/v0354/LICENSE.md)随副本保存。

## 准入结果

1. **首次后台启动没有受支持的控制参数。** 实际 `browser_prepare` profile 字段只有
   `mode`、`name`，`delivery_mode` 明确只用于 existing-profile。
   [稳定版启动实现](https://github.com/trycua/cua/blob/d74a9cab3fb2e80ab7f0cef47025ec828586ea75/libs/cua-driver/rust/crates/cua-driver-core/src/browser/prepare.rs#L473)
   配置普通 Chromium 命令并打开 `about:blank`，不含 `--no-startup-window` 或 headless。
   主分支的该函数与稳定版逐字节相同；macOS没有覆盖默认 `Command.spawn()`。
   这些事实不足以保证不激活或显示窗口，因此未运行该启动分支。
2. **连接复用不解决首次准入。** [跨会话连接复用修复](https://github.com/trycua/cua/pull/5115)
   复用已有批准的连接，每个会话仍须自身授权。它没有提供无首次批准、无前台副作用的
   冷启动路径，也不能把外部 worker 创建的 profile 变成 driver-owned。
3. **driver-owned 生命周期与当前刷新语义不兼容。**
   [会话清理钩子](https://github.com/trycua/cua/blob/d74a9cab3fb2e80ab7f0cef47025ec828586ea75/libs/cua-driver/rust/crates/cua-driver-core/src/browser/engine.rs#L696)
   调用 `cleanup_prepared_session`；后者删除匹配 owner 的 `ManagedBrowser`。
   [其 Drop](https://github.com/trycua/cua/blob/d74a9cab3fb2e80ab7f0cef47025ec828586ea75/libs/cua-driver/rust/crates/cua-driver-core/src/browser/prepare.rs#L304)
   在 Unix 终止自有进程组、回收 child，并按策略删除 profile。
   当前 worker 的 scope 刷新会先关闭 Cua 会话。直接切换该模式会破坏同一 Page/附件的保留要求。
   这是源码分析结论，**没有通过真实杀浏览器实验冒充原生验证**。

上游相关[后台控制焦点问题](https://github.com/trycua/cua/issues/3331)仍开放；
本轮仅只读查询，没有发 issue、评论或 PR，也没有采用外部 OS 自动化绕过拒绝。

## 本轮交付与验证边界

checkout 将0.35.4加入已确认不兼容版本的启动前阻断，保留0.35.2阻断。
这修复后续升级会再次创建无效实例的准入缺口，**没有修复完整后台附着**。
没有把未核验版本自动当作兼容版本，没有更改上游权限、发送或前台守卫。

| 检查 | 结果 |
| --- | --- |
| 新回归 red | [1 failed / 1 passed](admission-red.log)：旧检查漏过0.35.4，测试在进入浏览器启动前截获，未实际启动浏览器。 |
| 相关回归 green | [24 passed / 12 deselected，3.12秒](affected-green.log)，保留关闭、帧传输和未知结果停止派发的软件回归。 |
| 已安装0.35.2真实 CLI | [0.119434秒](native-admission-0.35.2.json)返回准入阻断，资源创建0。 |
| 私有0.35.4真实 CLI | [0.118611秒](native-admission-0.35.4.json)返回准入阻断，资源创建0；仅在测试中将可执行文件路径绑定到候选，manifest调用未替换。 |
| lint / 格式 | [通过](lint.log)。 |
| 完整离线回归 | [941 passed / 119 deselected，119.55秒](offline-full.log)。未选入的原生浏览器场景不计通过。 |

两项真实 CLI 检查均禁止进入 TemporaryDirectory、Chrome或 daemon 创建函数。
它们验证真实二进制的启动准入，不是 MCP 附着、语义点击、附件保留或变更回执丢失验收。
本轮没有重跑那些依赖完整浏览器附着的原生场景。

暂存准备的第一轮在读取 `codesign` requirement 时只解析了 stderr，准备失败。
原脚本另存 `inputs/stage-first.py`，原始失败日志保留于私有目录；之后同时读取 stdout/stderr，
重新校验相同 archive 和签名才运行 CLI。该失败不是 Cua 生命周期故障。

## 保全与后续准入

[保全回读](preservation.json)核对现有运行身份、私人 worker/页面/附件/设置摘要、
全部前代3,779个封存文件、已存在的持久私有原始诊断和安装应用。
所有新原始诊断和候选原字节均在本轮独立0700持久私有目录，见[绑定清单](private-raw-binding.json)。
不覆盖或重造旧失败，临时目录不是证据存储位置。

恢复完整附着前必须同时验证：受支持的后台无窗口启动、精确自有进程/端点授权、
scope刷新时保持原浏览器和 Page/附件，以及后端退出/未知结果不重发。
当前上游尚不能满足后台启动和刷新保留这两个前提，不能在保持约束的同时完成恢复。
不以前台启动后隐藏、修改 Space、把外部 profile 冒充 driver-owned或放宽守卫替代。

已安装 TomorrowStar/CuaDriver 未更新；现有 worker、浏览器、页面、附件保持。
候选 daemon、Chrome、真实 ATS、模型、上传及 Submit 均启动或调用0次。
后继复跑须使用新的空白持久私有目录，不向本包追加。
