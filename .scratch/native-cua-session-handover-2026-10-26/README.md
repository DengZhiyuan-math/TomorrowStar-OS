# CuaDriver 原生会话交接开发

2026-10-26，Europe/Zurich。用户已明确选择“扩展到底层原生会话交接”，
继续使用原生 computer-use 工具和原 Page。此授权不包含安装 App、更新现用 Driver、
真实模型、真实 ATS、最终 Submit 或远程发布。

源码位于 `source/`，来自 trycua/cua base `c6cb386cf371fed3580ea1c5a238940ce4911641`，
MIT。根许可证保留。原有 TomorrowStar 修复由 `inherited-upstream.patch` 与
`source-initial.json` 封存；不得修改原诊断源码或复写其编译输出。

## 采用的 native seam

复用 trusted_session begin/detach/resume/call。detach 关闭授权 context，但不调用
end_session；相同 daemon generation、public session 和 private transport 保留资源
namespace。无需复制 BrowserStore，也不新增自定义点击/输入执行器。

扩展为原 embedded host 显式授权一个活 accepted connection。connection_id 只是
定位，不能自己授予权限；host 验证专用 Codex proxy 的进程代次、可执行文件和直接父
进程，native 再比对 expected_peer_pid 与该 socket 的内核 peer PID。

接收者限原 target/tab、原 manifest 与绝对到期时间、原 application_ref_digest；
只调用已有 get_browser_state、browser_click、browser_type(insert_text)。原页交接
使用 native CDP target 与 Playwright retained Page 的 Target.getTargetInfo 精确对应，
不靠 URL/标题猜测。截图仅由原生工具按需提供，默认信息走 JSON。

先撤新增准入，handler 未返回时不能 drained。原生 call_id/参数摘要/结果证据保存在
同一 daemon 的原生交接记录中，unknown 不换 ID 重放。Driver 丢失仍由 Worker 保留
外层未知状态，不能声称跨 daemon 磁盘持久化。借用者 EOF 不执行浏览器生命周期清理。

## 当前实现与验证边界

Worker 已接入原生交接入口。它先从原 Page 读取无截图 JSON，核对 native target/tab
与原文档，再保存交接意图。每次原生写入前，它重新核对当前接管范围和相关已确认
答案，并保存原生调用元数据。Python 不执行页面点击或输入。

Adapter 已接入专用 native MCP 会话。模型的初始输入是一段 JSON；可用页面工具
仍是 Driver 原有的三个工具。原生权限撤销与实际 handler 排空分别核对，不能用
app-server 退出代替动作已结束。

Driver 的共享 RPC 装配和独立源码审查已完成。最终 native CLI 单元回归为
**350 passed**；浏览器核心为 **999 passed、1 ignored**。唯一忽略项需要一次人工
允许的真实 Chrome 调试连接，本轮未运行。首次核心回归中 13 项嵌套沙箱测试被
外层 Codex 沙箱阻止；最小命令复现 `sandbox_apply: Operation not permitted`。
自动审查允许原命令在外层沙箱之外重跑后，13 项全部通过。没有修改这些原有模块或
降低测试中的沙箱边界，证据见 `page-attestation/`。

候选二进制已构建，见 `candidate/manifest.json`；独立摘要已写入源码中的原生候选 pin，
原有 Driver pin 保留。候选随后仅用于隔离、无窗口的 MCP schema 检查：实际
`initialize` 与 `tools/list` **1 passed**，没有调用页面或输入工具，见
`candidate/schema-verification.json`。外层沙箱首次阻止 daemon socket 就绪；自动审查
允许原测试重跑后通过。构建清单中的未启动标志记录构建时点，后续只读启动独立留证。
候选未安装。最终 Python 整批回归与相关隔离浏览器检查均已通过。
默认和安装版不会自动开启该能力。
不得把这一阶段的替身测试当成真实 native 工具、模型或 ATS 验收。

本轮 Runner 的定向组合回归为 **39 passed**，包括交接前同 URL 重载、暂停、保存失败、
只读旧协议和候选二进制改变的拒绝，以及每次输入前答案/后端变化的拒绝。
日志与 JUnit 见 `runner/runner-scope.log`、`runner/runner-scope.xml`。
这组测试使用原页替身；最终隔离浏览器与完整离线回归另行记录。

## 最终批次与历史

| 范围 | 结果 | 证据 |
| --- | --- | --- |
| 完整默认离线 | 7,681 passed、2 skipped；零失败/错误 | `offline-final2/verification.json`，7,683 项完整 JUnit 覆盖 |
| 相关隔离浏览器 | 49 passed；零失败/错误 | `browser-final2/`；与离线不重叠，JUnit 完整匹配 |
| 原生 CLI 单元 | 350 passed | `ts-native-handoff-cli-final.log` |
| 原生核心单元 | 999 passed、1 ignored | `page-attestation/` |
| 实际候选 MCP schema | 1 passed | `candidate/schema-verification.json` |
| 静态检查 | Ruff、707 文件格式、diff 和受影响 Rust crate 格式通过 | `static-verification.json` |

最终离线批次冻结 663 个输入文件，运行前后完全相同。源码快照摘要：
`2115a95b1f2b0829a75ade6ae9d69d513da5119b86e698e5fd385da4c2a0b333`。
两个跳过项均为既有 PDF 性能/连接编译 opt-in。Native 核心忽略项和平台边界见上文。
浏览器在离线完成后执行，复用同一 663 文件快照，运行后无变更。1,118 个 native
源码文件及候选二进制摘要也在汇总时再次核对一致。机器汇总见
[verification.json](verification.json)。静态检查在启动兼容修正后重新通过。

第一轮 `offline-final/` 保留 7,679 passed、2 failed、2 skipped 的原记录。两项失败
定位到默认启动向旧调用传递了不必要的原生参数；只在启用原生模式时传递该参数后，
相关 31 项通过，再执行上述完整默认离线回归。
`browser-final/` 保留外层沙箱拒绝 Chromium Mach 端口而产生的启动失败；重跑没有
改生产源码、放宽发送守卫或开启 native/model opt-in。

独立审查与反例修正见[审查记录](review.md)。本票仍保留实际 native 原页输入的
验收条件；本记录不关闭该条件，也不证明 T07/T08/T09 或完整 ATS 流程已交付。

## 当前文件所有权

- native_handoff_server：native serve.rs、private trusted_handoff 模块、main.rs 装配。
- native_handoff_proxy：native proxy.rs、cli.rs。
- native_page_attestation：native browser/tools.rs 与 v2_tests.rs。
- native_host_client：Python cua_driver.py、worker_process_identity.py 与新测试。
- native_codex_adapter：application_codex_assist.py 与 native Adapter 测试。
- json_delivery：application_worker.py 的原生交接记录与事实预检。
- root：Browser/Runner 整合、证据与协调。

原生编译复用独立 APFS clone，见 `build-target-clone.json`；没有硬链接或写回原 target。
当前 JSON 源码验证见
[JSON 实现记录](../module-completion-2026-10-26/json-handoff-implementation/implementation.md)。
此文件记录源码、构建与合成验证；不代表实际 native 输入、活动模型或安装版验收。
