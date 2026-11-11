# checkout worker 接入修复版 CuaDriver

checkout 已接入固定的本地修复候选。完整 worker 合成表单、310 秒真实暂停后的
scope 刷新、真实已完成点击的回执丢失均复验通过。已安装应用和既有运行未更新。

## 交付与准入

- [checkout 变更](checkout-change.patch)，四个现有代码文件、一个新增回归文件和验证命令文档；[源码与文档哈希](source-changes.json)。
- [冻结候选](candidate.json)为上一轮本地上游修复，SHA-256 `0fe29ea79abd68a1b4acc2f732fa9b90d05ec688913baf36c4d8a25a9e9bcb8a`。
- 候选由 `TS_CUA_DRIVER_BINARY` 显式选择，执行前核对固定 SHA；不接受任意自报哈希或符号链接。
- 未配置时仍使用原版准入规则，0.35.2/0.35.4 的旧后台路径继续拒绝。
- 没有全局设置该变量，没有安装、推送或发布；原始诊断保存在权限 `0700` 的持久私有目录，见 [逐文件绑定](private-raw-binding.json)。

## 生命周期与 scope

driver 在本次私有目录创建独立 profile，私有 daemon 始终 bounded。
先核验宿主 OS 权限、实际 daemon PID、准备回执、Chrome PID/launch date、profile
锁与 loopback 监听者，再连接 CDP。启动页面目标须为零；前置原生窗口读取保持私有。
不启动 TCC 提示，不采用安装应用作为候选的启动 fallback。

隐式 transport owner 持有浏览器；named scope 只持有绑定与 ref。
刷新结束旧 named scope，保留同一 client、transport、daemon、浏览器、context 和 Page。
刷新后重新绑定，旧 ref 不复用。manifest 的来源、TTL 和批准上限不变，新增来源直接拒绝。

worker 原有 tick 循环执行定期只读 owner 观察，没有新增心跳线程。
owner 仍为原 300 秒 idle TTL，保活间隔最多 60 秒；named scope 在其期限内更新。
这不延长 manifest 的 24 小时上限，也不支持跨 daemon 或过期授权的透明续权。

未知结果继续设置原 client 的 failed 状态。后续 tick 不再发送 Cua 请求，强制 scope
刷新也拒绝；原 intent 保留。没有重新打开浏览器、重选文件或重放未知动作。
失败 transport 不再保活，仍受原 owner 过期/断开清理规则约束；本轮不证明未知后跨
idle 到期仍能保留页面。

## 隐藏窗口动画修复

接入过程中捕获隐藏窗口动画。两页最小对照确认：创建新标签会把已最小化的 Chrome
窗口还原，动画早于再次最小化；跳过重复最小化没有解决这个触发链。
候选路径现在保持窗口 normal 且应用 hidden，省去最小化/还原循环。
创建页面前后仍严格核验 hidden、未激活、零上屏；没有忽略 alpha=0 的采样，也没有
增加 hide、foreground 或重试。原版窗口路径保持。

[最小对照](probe_page_creation.py)的 native-07 为红，native-08 为绿；原始 CDP
状态及 WindowServer 时间线均保留。新增两页回归覆盖该实际触发模式。

## 验证结果

| 检查 | 通过 | 跳过或未选入 |
| --- | ---: | ---: |
| 完整离线回归 | 945 | 119 deselected |
| 最终受影响回归 | 28 | 12 deselected |
| 合成 headless worker browser | 7 | 5 skipped、15 deselected |
| 活动代码 lint / format | 通过 | 122 个文件 |
| 排除 `.scratch`、禁用缓存的全目录 lint / format | 通过 | 168 个文件 |
| 最终完整 worker 短程复验 native-14 | 1 | 0 |
| 310 秒暂停与自动 scope 刷新 native-13 | 1 | 0 |
| 丢弃已完成点击回执 native-12 | 1 | 0 |

三个原生场景均使用真实冻结 CuaDriver、实际 checkout `ApplicationRunner` 和独立
合成存储。不是对现有 worker 的操作，也不代表已安装应用或真实 ATS 验收。

- native-13 保持暂停 310 秒，通过原 worker tick 的只读保活跨过 300 秒期限；
  原 CDP target 和同一 `File` 对象保持，刷新使用同一 daemon 和 transport。
- native-12 使用单线程 relay。在实际第二次选项点击完成后，仅丢弃对应回执，保留
  原生连接；DOM 选择发生一次。后续五次 tick 和强制 scope 刷新都未发出新请求。
  原 intent、Page、预选合成附件均保持。点击请求共两次，prepare 一次，无重启。
- native-14 确认零启动页面、真实窗口前置读取、精确后台转发、旧绑定退休、来源
  上限不扩张，以及原页/文件保持。
- 固定 Space。各通过场景自有 Chrome 激活和窗口上屏采样均为零；仅属状态采样，
  不能证明逐帧绝对零闪现。
- 正常及未知结果停止后的自有 profile、socket 和进程清理经过回读。

细节见 [验证汇总](verification.json)、各 `native-*-result.json` 和私有原始绑定。
真实 ATS、模型、网络上传、最终 Submit 均为零。附件选择均为合成本地状态。

## 保留的失败与边界

native-01 复现旧入口仍选择安装版并阻断；native-02 为 CFArray 桥接错误；
native-03 为原生标题尚未发布；修复后沿用原两秒发现期限。
native-04/05 通过功能断言但被上屏采样拒绝；native-07 的最小对照定位还原动画。
这些结果没有改写为通过，native-04 的失败保存在原日志而非事后伪造运行结果。

native-06 保留一轮上游启动身份读取拒绝；native-10 保留一轮完整快照超时，
均安全停止且没有自动重试。它们的底层原因尚未确认，不能宣称候选启动或快照始终可用。
native-11 的故障输入过早缩短期限，实际在快照阶段停止，没有丢到点击回执；
因此 native-12 保持原 MCP 15 秒期限，用真实完成的点击帧核验。

headless 首轮在命令沙箱中启动失败；原样在获授权执行环境重跑后七项通过。
五份匹配本轮测试 PID 的系统 crash 报告已复制到私有目录，原件未改。
全目录样式检查包含历史封存快照（928 lint 错误、99 文件格式差异），保留失败原文；
活动源码与测试检查通过。后继命令排除 `.scratch` 并禁用缓存，完整检查 168 个文件通过。
这两项参数已写入 `CONVENTIONS.md`，避免校验修改历史缓存。

首次全目录 Ruff 检查误刷新了历史输入中的 8 个缓存，并新增 3 个缓存。
第一次保全校验因此失败，原日志保留。依据执行前 SHA-256 和 Ruff 0.16 缓存结构，
恢复缓存的原时间戳与标志；8 个恢复文件均与各自原始 SHA-256 完全一致后才写回。
误刷新的字节及新增缓存移存本轮持久私有目录，未改原始 seal 或期望哈希。
随后历史全树 3881 个文件的路径和哈希全部与执行前一致，见 [事故与恢复记录](cache-incident.json)。

本票仍保持 open，记录候选可用性中的上述拒绝及后续发布边界；checkout 接入和本轮
限定合成验收已经完成，不表示默认安装版已恢复。

## 保全

[最终回读](preservation.json)分别绑定现有运行、历史 3881 个文件、此前持久私有原始
诊断 257 个文件、已安装应用和冻结候选。个人运行内容没有复制到公开报告。
所有测试使用新的 worker、profile、页面与附件；没有前台切换或守卫放宽。
