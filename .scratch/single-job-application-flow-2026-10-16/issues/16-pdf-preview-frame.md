# 修复单岗位 PDF 的同源内嵌预览

Type: task
Label: wayfinder:task
Status: closed
Interaction: AFK
Assignee: 01a146b9/pdf_preview_fix
Created: 2026-10-17
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: [复用岗位分析生成并确认专用简历](05-tailored-resume.md), [把单岗位五阶段流程接入 App 界面](07-app-workspace.md)

## Question

安装版已生成 PDF，但内嵌预览被通用防嵌入响应头阻止，如何仅允许工作台同源预览批准前的当前材料？

## Work and ownership

- 只修改 `src/career_evidence_graph/career_portal.py` 与 `tests/test_career_portal_http.py`。
- 单岗位 PDF 路由显式允许同源 iframe；其他页面/API 保留禁止嵌入。继续使用原 PDF ID、私有存储、字节和来源校验。
- 不改变材料确认、发送批准、worker、邮件、最终 Submit 或私人原件。
- 执行者不独占代码库，不回退他人更改。先反例 RED，再做最小修复。

## Acceptance criteria

- [x] 单岗位已保存 PDF 的响应允许同源预览，拒绝外站嵌入。
- [x] 主页面、JSON/API 和其他非预览响应保留原防嵌入头；Host/CSRF 和输入门禁通过。
- [x] 相关 HTTP 与冻结源码回归通过。安装后的可见 PDF 内容另由第 10 票实测。

## Resolution comment

2026-10-17：第 10 票在真实安装版窗口复现空白 iframe；通用响应含 `X-Frame-Options: DENY` 与 `frame-ancestors 'none'`。已保留当前任务和已生成 PDF，尚未确认材料或启动 worker。

2026-10-17 关闭：先由现有 HTTP 生成/预览测试复现 DENY 的 RED，再给精确单岗位 PDF 成功响应增加服务端显式同源选项。该响应现在发送 SAMEORIGIN 与 frame-ancestors self；页面、API、静态资源、旧 PDF 成功响应及错误响应仍 DENY/none，请求头或 query 不能放宽。PDF 字节、来源、确认及发送门禁未改变。

HTTP 专项 **117 passed**；冻结源码完整离线回归 **1973 passed、151 deselected / 255.91s**，全仓 Ruff check/format 通过。`career_portal.py` SHA256 `701b89c7f5941335a5427a67512b75a6dd7611a6cb3de5bde9363a4e110838b4`，HTTP 专项 SHA256 `e3ba809736fb4ab3e905a8041eddfbea6bf996a2eff58821fb9cf48611d0d13e`。

新包签名、搬移及运行时验收通过，安装后原生窗口的同一合成任务与同一 PDF 已恢复，内嵌内容的文字与像素均可见，并核对了采用来源和改写。见[新包验收](../assets/native-preview-fix-package-acceptance.json)和[源码绑定及原生观察](../assets/native-preview-fix-source-binding.json)。本票修复完成；完整合成填写仍由第 10 票核验，不由本次 PDF 可见性代替。
