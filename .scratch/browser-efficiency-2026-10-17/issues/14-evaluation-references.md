# 研究浏览器评测与独立结果校验机制

Type: research
Label: wayfinder:research
Status: closed
Priority: P1
Interaction: AFK
Assignee: 01a14a28/evaluation_reference_research
Created: 2026-10-17
Parent: [交付 DOM 优先的受控浏览器效率改进](../map.md)
Blocked by: [定位浏览器控制的分段耗时与重复调用](01-browser-performance-baseline.md)

## Question

ServiceNow/AgentLab、ServiceNow/WorkArena、web-arena-x/webarena、ServiceNow/webarena-verified、xlang-ai/OSWorld；对照既有BrowserGym。如何借鉴重放、独立validator、失败分类和成本记录，验证合成优化且不把公开榜单等同本地性能？

## Research contract

- 仅公开一手来源，核实canonical仓库、固定commit、许可证原文及源码定位；README性能声明不能当作本地基准。
- 每项给出reuse/adapt/inspired-by/reject建议、适用任务及本地差异；调研不等于安装、抄代码或引入依赖。
- 复用[已有43项清单](../../../research/open-source-job-application-browser-tools-2026-10-17.md)与[源码复用分析](../../../research/tomorrowstar-open-source-reuse-analysis-2026-10-17.md)，新增与复核分开计数。
- 产物是research目录单份Markdown报告；不启动浏览器、模型、ATS或读取个人状态；不得绕反爬或登录限制。

## Context and ownership

- 研究分支：`D_m/research/browser-evaluation-references-20261017`；隔离目录：`/private/tmp/tomorrowstar-browser-evaluation-references-20261017`。
- 主工作区只读上下文：当前地图、基线报告、现有研究。研究代理只拥有该隔离目录的报告，不修改主工作区或票。
- 领取人见Assignee。代理并非独占代码库；不得覆盖其他人的更改。主代理负责依赖和规划整合。

## Acceptance criteria

- [x] 每个候选有固定版本、许可证与一手源码链接；访问缺失或未知明确列出。
- [x] 结论落到现有工程问题，列出不能移植或尚未验证的部分。
- [x] 报告保存在研究分支并回传commit；本地tracker再追加resolution。

## Resolution comment

2026-10-17：由领取的研究代理完成公开一手源码核验。借鉴独立validator、版本与成本记录；拒绝会改变原页的现场验证／回放。

- 报告：[研究浏览器评测与独立结果校验机制](../../../research/browser-evaluation-references-2026-10-17.md)。
- 研究分支：`D_m/research/browser-evaluation-references-20261017`；commit：`da4fb2b51ea7215f6c0515e85379cf35a9fdacee`。仅单报告提交；主工作区分支未切换。
- 当前research副本与该commit报告字节一致；未复制上游实现代码、未安装／运行候选框架。
- 结论已纳入相关现有任务；研究完成不代表优化、原生Cua、安装或真实ATS验收。
