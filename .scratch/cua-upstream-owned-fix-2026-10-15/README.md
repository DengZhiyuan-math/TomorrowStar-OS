# CuaDriver：无窗口后台启动与 scope 保留

上游最小补丁已在本地实现。冻结候选三次独立原生复验全部通过：
零启动页面、后台精确附着、scope 重建保留原 CDP target 和同一附件 `File` 对象。
这是隔离合成验收；checkout worker 尚未接入，已安装应用未更新。

## 来源与交付

- 上游：[trycua/cua](https://github.com/trycua/cua/tree/c6cb386cf371fed3580ea1c5a238940ce4911641)，固定提交 `c6cb386cf371fed3580ea1c5a238940ce4911641`。
- 本地分支 `D_m/cua-owned-windowless`；未提交、推送或发布。
- [最小补丁](upstream-minimal.patch)，11 个文件；[MIT 许可证](upstream-LICENSE.md)。没有新增依赖或更改锁文件。
- [来源、逐文件哈希和冻结二进制](candidate.json)。使用已有 Rust/Cargo 1.98.1；上游固定 1.97.1，本轮未安装或切换工具链。
- [原始诊断逐文件绑定](private-raw-binding.json)：持久私有目录，权限 `0700`。

原始 RPC、WindowServer/Space 采样、启动身份、编译及测试日志保持私有。
源码 checkout 与 Cargo 缓存不算封存诊断；源码由固定提交及补丁绑定。
精确测试二进制单独冻结于该私有目录的 `candidate/cua-driver`，没有替换安装程序。

## 最小实现

`browser_prepare` 新增可选输入，原默认行为保持：

```json
{"allow_launch":true,"profile":{"mode":"isolated_new","windowless":true}}
```

macOS 复用 NSWorkspace 请求隐藏新实例，不发送启动 URL 或 `oapp`，
Chrome 使用 `--no-startup-window`。返回 PID 必须匹配新分配的 profile 参数；
清理核对 launch date，不对 LaunchServices 实例使用负进程组信号。
前台投递、named profile 及不支持此能力的平台明确拒绝。

没有新增 lifetime 参数。准备调用省略 `session`，复用 transport 的隐式 owner；
绑定及操作使用独立 named scope。结束 named scope 使其句柄失效，
原浏览器、页面和附件仍由隐式 owner 持有。新 scope 必须重绑并取得新 ref。
隐式 owner 保持原 300 秒 idle TTL，期限内普通 unnamed 只读调用用于保活。
owner 结束、过期或 transport 断开仍清理浏览器及临时 profile。

bounded manifest 仅声明 `isolated_new`、精确来源及工具。窗口授权同时核验可信
transport 所有权、新鲜进程 fingerprint 及原生窗口身份。未批准整个 Chrome、
桌面、全局 existing-profile 或额外来源；公开参数不能制造 transport 身份。

## 根因和保留的失败

全部结果见 [native-cohorts.json](native-cohorts.json)，失败不计入通过。

| 轮次 | 观察与处理 |
| --- | --- |
| native-01 | 合成 manifest 的 profile 形状错误；修正测试输入 |
| native-02、03 | 缺少 AppKit 循环，且启动返回早于隐藏状态收敛；使用无窗口 accessory 循环及有界只读核验 |
| native-04、05 | 新 PID/window 无桌面预授权；公开参数又已清洗 transport 身份；使用可信上下文中的原生所有权证明 |
| native-06 | 合成 HTML 缺少 UTF-8 声明；修正输入，保留中文 ref 的精确断言 |
| native-07 | 完整流程首次通过 |
| native-08 | 独立采样显示已隐藏，启动线程仍读到 `hidden=false`；原期限内拒绝并清理 |
| native-09～11 | 改为主队列读取新鲜状态后连续三次通过 |
| native-12～14 | 对独立冻结二进制再验三次，全部通过 |

native-08 的快照差异符合 [Apple 关于 NSRunningApplication 主运行循环刷新规则的说明](https://developer.apple.com/documentation/appkit/nsrunningapplication)。
修复只调整状态读取，保留原 3 秒期限，没有 hide、activate、前台恢复或失败重试。

单元红测保留了 windowless 参数缺失、owned-window 未批准，以及被放弃的新 lifetime 参数方案。
首轮关闭 core 默认 feature 导致 manifest 测试失败；正常默认 feature 下通过。
稀疏 checkout 缺少静态资源及 compat fixtures 的编译失败也保留。

Cargo 后续构建更换过输出字节。捕获哈希不一致时，没有沿用原生通过结论：
重新冻结候选，再执行 native-12～14；原捕获和处理记录保留于私有目录。

## 验证

| 检查 | 通过 | 跳过或未选入 |
| --- | ---: | ---: |
| 最终 core 代码的默认 feature 回归 | 983 | 1 ignored |
| 最终 macOS 库回归 | 568 | 6 ignored |
| CLI/MCP 全集，最后一次状态读取修正前 | 419 | 20 ignored |
| 状态修正后的协议 schema、真实代理恢复 | 4 | 1 ignored |
| 现有 Python MCP 关闭、未知结果不重发 | 10 | 26 deselected |
| 冻结候选独立原生合成复验 | 3 | 0 |

各阶段见 [test-results.json](test-results.json)。真实桌面输入 opt-in 套件未运行。
[最终原生结果](native-verification.json)证明：

- 零启动页面，精确绑定，完整未过滤 `semantic_v2` 快照；中文、emoji ref 保持。
- 每轮真实 MCP 转发两次合成点击，scope 更新前后保留同一 CDP target 和 `File` 对象。
- 另一 transport、旧 scope 句柄、未批准来源均拒绝；拒绝后 DOM 和附件保持。
- Space 固定；采样中的自有 Chrome 激活、窗口上屏、后端激活均为零。
- 关闭 owner transport 后浏览器退出，临时 profile 删除。

状态采样不能证明逐帧绝对零闪现；最长间隙见 verification JSON。
原生 mutation 回执丢失本轮未注入，未知结果不重发仅计上述现有离线回归。

## 保全和边界

[最终保全回读](preservation.json)：原有 worker、页面/附件记录、设置及进程身份保持；
历史 3833 个文件、此前持久私有原始诊断 74 个文件保持；主项目 122 个 Python/Swift
文件、TomorrowStar.app 的 1419 个文件、已安装 CuaDriver 0.35.2 及 rollback 二进制保持。

上游协议测试留下的四个私有 daemon 使首次保全检查失败。逐项核对本轮二进制路径、
socket、PID 和启动时间后，仅 SIGTERM 这些进程；保留失败与清理回执。
最终无本轮 Cua/Chrome 残留，自有 profile 全部删除。

真实 ATS、模型、网络上传、最终 Submit、已安装应用更新均为零。
合成附件仅在隔离页面本地选择，没有发送请求。

scope 更新限于同一存活、未过期 owner 和同一批准来源上限。
没有验证跨 daemon 保留或 owner/manifest 到期后续权，没有延长原 TTL。
尚未接入 checkout worker 的实际 scope 更新流程，原版 0.35.2/0.35.4 准入阻断保持。
[调查 CuaDriver 0.35 后台浏览器附着拒绝](../application-worker-stability/issues/10-cua-035-background-attach.md)
保留 open，分别记录本地候选已通过与运行时接入仍待完成。
