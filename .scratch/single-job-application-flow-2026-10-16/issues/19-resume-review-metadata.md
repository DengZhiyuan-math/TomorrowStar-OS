# 修正简历导出的内部审核文字

Type: task
Label: wayfinder:task
Status: closed
Interaction: AFK
Assignee: 01a146b9/ats_controls
Created: 2026-10-17
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: [复用岗位分析生成并确认专用简历](05-tailored-resume.md)

## Question

当前导出将来源审阅状态打印为 Responsibility，能否保留 App 的核验记录并输出可供申请的简历？

## Work and reuse

- 仅修正渲染层把内部 editorial review 状态当作职责归属的显示，复用现有导出器。
- 保留结构化来源、原文、改写、归属和边界；真实的 User / team / Codex 责任区别不得丢失或转移。
- 不修改个人原资料或既有 PDF；后继材料须经 App 正常重生成并重新确认。
- 用合成数据先复现，再做最小修复；不扩为简历模板重做。

## Ownership

- src/career_evidence_graph/application_resume.py
- tests/test_application_resume.py

不是唯一执行者；保留他人编辑，不回退其他模块。

## Acceptance criteria

- [x] 合成输出不再包含内部 editorial review 状态行，来源清单仍保留该状态。
- [x] 混合责任与明确边界仍保留，不能转成个人实施事实。
- [x] 受影响测试、完整离线与后继安装版 PDF 分别验证；旧 PDF 保留。

## Verification and evidence

使用 tdd 与 checkout launcher。公开材料只含合成例；不得复制真实 PDF、个人字段或私有指纹。

## Resolution comment

2026-10-17：真实材料只读核验中观察到导出包含内部审阅状态文字，尚未批准或上传。建立最小渲染修复，旧版本保留。

源码及合成回归已冻结，独立审计结论与实际 RED/GREEN 见[源码验证](../assets/ats-controls-resume-source-verification-20261017.json)。第 18 票另修正两项审计发现的未知必填/跨组漏洞。完整离线与后继安装版仍待第 20 票冻结后执行；当前保持 open，不以源码结果代替真实链。

冻结源码完整默认离线 **1975 passed、188 deselected，245.94s**，Ruff/format/diff 通过。独立新包的搬移运行、签名、摘要、包内运行时、合成 PDF、Host/CSRF 和父管道退出均通过，见[统一离线与包验证](../assets/ats-fixes-offline-package-verification-20261017.json)。尚未以此关闭安装版/真实验收。

后继包已安装并核对全部字节、签名、当前状态与回退保留；两项权限对当前安装身份重新绑定后，实际原生宿主离线诊断通过，见[当前安装与宿主证据](../assets/native-ats-fixes-installed-host-20261017.json)。该诊断不含真实控件填写或 ATS 上传，真实业务仍待本票对应验收。

2026-10-17 关闭本票的精确渲染修复范围：后继安装版经原生窗口同步、生成、内嵌预览与全部页面视觉核对，导出不再打印该 editorial review 状态行；来源 metadata、真实责任及边界继续保留，旧 PDF 保留。独立私有核验确认事实、PDF/任务/当前配置绑定一致，见[原生 PDF 验收](../assets/native-resume-renderer-acceptance-20261017.json)。候选简历含完整设计记录边界，其呈现与具体发送仍待第 11 票中的用户材料审核；本票关闭不表示用户批准或真实上传。
