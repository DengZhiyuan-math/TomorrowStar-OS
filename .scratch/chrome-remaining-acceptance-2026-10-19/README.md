# 26 号票剩余验收 — 2026-10-20

## 结论与验收边界

注册服务预检已接入实际 PDF 导出和共享主界面。独立安装候选通过整包验收及三次原生冷启动 / 实际 PDF。原主 App 与连接配置保持，真实申请暂停；未执行真实模型、ATS、上传、提交或 commit/push。

[26 号票](../single-job-application-flow-2026-10-16/issues/26-native-chrome-startup-crash.md)保持 open。原完整受限沙箱同条件 PDF GREEN 仍阻塞；最终文案在原生 WKWebView 的固定注入失败路径已补验通过，见文末后继；原完整沙箱 GREEN 仍未通过。安全停止、共享浏览器 UI、获准原生宿主成功各自单列，不替代上述门槛。

## 修复与直接证据

- `chrome_registration.py` 提取唯一 LaunchServices 查询：1100 为拒绝，其余不确定状态为 unknown；正确释放端口，不切换宿主或扩大权限。
- `application_resume.export_pdf` 在启动 Playwright 前复用查询，以两个明确错误返回。Store 保留已知未启动语义。内建导出配置绑定该模块源码 hash，不缓存当前服务访问状态。
- 共享主界面在失败、恢复和导出区显示固定安全停止原因，不暴露 stderr / 路径 / argv；刷新不会自动重试。
- `macos/verify.py` 从自身源码树或包内明确位置加载共享查询，避免 editable checkout 回退。

初始核心红测 5 失败 → 20 通过，扩展 68 通过。独立审查发现版本绑定和跨平台模拟缺口，修正后 112 通过；详见[审查](review.json)。

实际原生旧流程进一步发现：生成与导出合并时尚无审阅草稿，因此 generic 错误不能宣称草稿和审阅已保存或仅重试 PDF。最终两处生产文件只改四个错误文本常量，另加此路径回归。最终提示为：

> PDF 导出已停止：当前执行环境拒绝浏览器注册所需的系统服务。不会自动重试；请先核对执行环境。

已有材料保留语义仍由具体流程状态保证，不由通用错误臆测。相关回归 [155 通过、2 排除](wording-core-green.log)，最终浏览器 [7 通过](wording-ui-final.log)，包括拒绝/未知、刷新不重试、明确重试及旧合并流程。见[最终共享 UI 截图](final-shared-ui-failure.png)。

## 原完整受限沙箱

[实际查询](original-sandbox-probe.json)拒绝；[最终源码实际 export_pdf](wording-final/original-sandbox-export.json)返回 `resume_chrome_registration_denied`，无 PDF。当前服务限制来自执行底座，仓库补丁不能移除继承限制。没有变更系统/工具全局策略，也未重复制造已知 abort。

功能基线后端 PID90568 在原完整沙箱执行实际查询，通过 IAB 仅展示共享主界面：[回执](frozen-restricted-ui-result.json)、[源码绑定](frozen-restricted-ui-backend.json)、[截图](frozen-restricted-ui.jpg)。一次导出、无 PDF/worker、原有草稿及审阅保留、刷新不重试；后端和页面已退出。该轮早于最终中性文案，不能声称最终文本字节也在此实际后端重跑。最终文本字节有上述独立真实查询及七项 UI 回归。

早期绑定记录保留，[纠正说明](restricted-to-frozen-binding-corrected.json)明确不能用运行后 checkout 文件追认历史进程字节。历史 PID90954/74201 的直接 argv 缺口仍保留。

## 最终独立安装候选

安装位置 `/Users/zhdeng/Applications/TomorrowStar Chrome PDF Verified.app`，ID `dev.tomorrowstar.chrome-pdf-verified`。上一个安装版与本轮首版分别保全到 `build/chrome-main-failure-previous-installed` 和 `build/chrome-main-failure-pre-wording-installed`，原主 App 未替换。

功能基线来自上一轮冻结源，覆盖七个明确文件；未带入其他会话的 PDF-reuse 配置增量，原 checkout 该增量保留。最终 successor 为 `build/chrome-main-failure-wording-source`，与功能基线只有上述文案和回归差异；[差异范围](post-suite-wording-delta.json)留存。

最终结果均在 **wording-final/**：[整包验收](wording-final/package-acceptance.json)、[安装](wording-final/install-result.json)、[安装清单](wording-final/installed-bundle-inventory.json)、[最终读回](wording-final/installed-final-readback.json)。88 个 engine 文件、5 个 helper；strict/deep 签名、重定位、包内 Python、实际系统 Chrome PDF、合成流程及退出通过。浏览器本身为系统 Chrome。

| 次数 | Native PID | Python PID | Chrome PID | 耗时 | 回执 |
|---|---:|---:|---:|---:|---|
| 1 | 7263 | 7311 | 7328 | 7.634 s | [通过](wording-final/cold-start-01.json) |
| 2 | 7462 | 7463 | 7501 | 4.111 s | [通过](wording-final/cold-start-02.json) |
| 3 | 7604 | 7605 | 7613 | 2.729 s | [通过](wording-final/cold-start-03.json) |

三次通过 LaunchServices 启动实际 NSApp，独立 marker/profile，均小于 40 秒。每轮一页 PDF、文本匹配、0600、OS 责任链绑定原生 PID，自有进程及 profile 清理通过。[最终 PDF](wording-final/cold-start-03.pdf)。安装包测试后字节/签名不变，原主 App 的 engine/helper/身份/签名和连接配置保持。根目录旧三轮回执仅属本轮早期功能版本，不冒充最终版本。

## 原生主窗口剩余阻塞

首个签名故障副本启动被 LaunchServices -10810 / RBS5 / NSPOSIX1 拒绝；[日志](native-ui-launch-system.log)保留。该阻塞后来被可正常启动的固定合成根目录副本替代，不能继续声称没有原生窗口。

可启动副本仅在自身固定注入拒绝，绝不读取真实连接配置；注入不是实际 OS 拒绝。旧合并流程在真实 WKWebView 中暴露了上述错误文案，已修复并加入回归。旧合成任务缺少 URL，重开时被工作区准入拒绝，保留原件，不绕过产品校验。

最后使用有效固定合成 Lever URL 的新根目录：[fixture](native-ui-final-fixture.json)、[运行身份](native-ui-final-runtime.json)。Native PID8297、backend8312，生产 exporter/UI 字节与最终安装包一致，guard/固定根目录 Swift 为显式测试覆盖。单次合成分析最终 `match_model_timeout`，尚未进入导出；[AX](native-final-analysis-blocker-ax.txt)、[截图](native-final-analysis-blocker.jpg)保留。原因未定，未自动重试或开启真实模型，因此最终原生失败文本及其不重试整项仍不勾选。

通过正常 Quit 结束本轮原生副本，只读进程核对两 PID 均已退出，观察页关闭；临时签名 App、两个合成根目录和证据保留用于复现。[清理回执](native-final-cleanup.json)。

## 测试范围和下一项

功能基线完整默认离线 [3512 通过、307 排除、646.14 秒](offline-result.json)。最终 successor 在其后仅改生产错误文本：155 项相关测试及 7 项浏览器回归通过。**未将基线全套结果说成最终 successor 全套重跑。** 两个阶段各自 495 文件运行前后逐字节冻结；最终清单见 [before](wording-source-before.json) / [after](wording-source-after.json)。Ruff、格式及 diff 检查通过。

[阻塞表](blockers.json)分别记录原完整沙箱、原生最终失败路径、历史 argv。全 tracker 无机械可领取 frontier：未领取请求诊断仍依赖其他会话持有的原页观察，其他相关票已有执行者。本轮在同条件修复阻塞后已推进可独立的主界面错误处理工程；没有越过依赖或接管其他票。真实申请持续暂停。

## 后继：原生主窗口失败验收通过

前述分析超时记录保持为历史失败。只在临时 CLI 加 shell 入口记录后，通过原生界面明确同步合成配置并重试一次，分析和固定响应完成。随后实际 WKWebView 的生成按钮触发固定注册拒绝，显示最终中性停止提示。[结果](native-window-followup/result.json)、[AX](native-window-followup/failure-ax.txt)、[截图](native-window-followup/failure.png)留存。

exporter/UI 字节与最终独立安装候选相同；固定根目录 Swift、拒绝 guard 和 CLI 记录为明确测试覆盖。刷新后 flow 与 CLI 记录逐字节不变，无PDF/worker；进程树只有本次native/backend，无Chrome。正常Quit后两PID退出，[原生事件](native-window-followup/native-events.jsonl)与[后端EOF关闭](native-window-followup/backend-events.jsonl)留存。第5项现勾选；此前“最终主窗口未验完”描述已由本段后继替代。原完整受限沙箱同条件成功及历史argv仍阻塞，真实申请暂停。
