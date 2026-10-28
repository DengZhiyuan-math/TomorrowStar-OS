# 研究语义视觉代理与替代浏览器的适用边界

Type: research
Label: wayfinder:research
Status: closed
Priority: P1
Interaction: AFK
Assignee: 01a14a28/hybrid_reference_research
Created: 2026-10-17
Parent: [交付 DOM 优先的受控浏览器效率改进](../map.md)
Blocked by: [定位浏览器控制的分段耗时与重复调用](01-browser-performance-baseline.md)

## Question

magnitudedev/browser-agent、lightpanda-io/browser、bytebot-ai/bytebot、simular-ai/Agent-S；对照现有browser-use、Stagehand。哪些机制适合现有DOM/Cua路线，哪些会增加模型轮次、数据外发或运行时复杂度？

## Research contract

- 仅公开一手来源，核实canonical仓库、固定commit、许可证原文及源码定位；README性能声明不能当作本地基准。
- 每项给出reuse/adapt/inspired-by/reject建议、适用任务及本地差异；调研不等于安装、抄代码或引入依赖。
- 复用[已有43项清单](../../../research/open-source-job-application-browser-tools-2026-10-17.md)与[源码复用分析](../../../research/tomorrowstar-open-source-reuse-analysis-2026-10-17.md)，新增与复核分开计数。
- 产物是research目录单份Markdown报告；不启动浏览器、模型、ATS或读取个人状态；不得绕反爬或登录限制。

## Context and ownership

- 研究分支：`D_m/research/browser-hybrid-references-20261017`；隔离目录：`/private/tmp/tomorrowstar-browser-hybrid-references-20261017`。
- 主工作区只读上下文：当前地图、基线报告、现有研究。研究代理只拥有该隔离目录的报告，不修改主工作区或票。
- 领取人见Assignee。代理并非独占代码库；不得覆盖其他人的更改。主代理负责依赖和规划整合。

## Acceptance criteria

- [x] 每个候选有固定版本、许可证与一手源码链接；访问缺失或未知明确列出。
- [x] 结论落到现有工程问题，列出不能移植或尚未验证的部分。
- [x] 报告保存在研究分支并回传commit；本地tracker再追加resolution。

## Resolution comment

2026-10-17：由领取的研究代理完成公开一手源码核验。参考document generation与观察分段；新增视觉框架／引擎不进入本轮执行链。

- 报告：[研究语义视觉代理与替代浏览器的适用边界](../../../research/browser-hybrid-references-2026-10-17.md)。
- 研究分支：`D_m/research/browser-hybrid-references-20261017`；commit：`33869144dc83f6e9c3096120b3eb74e1aa4eded6`。仅单报告提交；主工作区分支未切换。
- 当前research副本与该commit报告字节一致；未复制上游实现代码、未安装／运行候选框架。
- 结论已纳入相关现有任务；研究完成不代表优化、原生Cua、安装或真实ATS验收。
