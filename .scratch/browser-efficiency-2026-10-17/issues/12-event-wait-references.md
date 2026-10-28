# 研究事件等待与 CDP 控制的可复用机制

Type: research
Label: wayfinder:research
Status: closed
Priority: P1
Interaction: AFK
Assignee: 01a14a28/event_wait_research
Created: 2026-10-17
Parent: [交付 DOM 优先的受控浏览器效率改进](../map.md)
Blocked by: [定位浏览器控制的分段耗时与重复调用](01-browser-performance-baseline.md)

## Question

go-rod/rod、chromedp/chromedp、ultrafunkamsterdam/nodriver、cdpdriver/zendriver、webdriverio/webdriverio、getgauge/taiko；复核既有Playwright事件等待。哪些机制能改善现有pump调度而无需替换runtime？

## Research contract

- 仅公开一手来源，核实canonical仓库、固定commit、许可证原文及源码定位；README性能声明不能当作本地基准。
- 每项给出reuse/adapt/inspired-by/reject建议、适用任务及本地差异；调研不等于安装、抄代码或引入依赖。
- 复用[已有43项清单](../../../research/open-source-job-application-browser-tools-2026-10-17.md)与[源码复用分析](../../../research/tomorrowstar-open-source-reuse-analysis-2026-10-17.md)，新增与复核分开计数。
- 产物是research目录单份Markdown报告；不启动浏览器、模型、ATS或读取个人状态；不得绕反爬或登录限制。

## Context and ownership

- 研究分支：`D_m/research/browser-event-waits-20261017`；隔离目录：`/private/tmp/tomorrowstar-browser-event-waits-20261017`。
- 主工作区只读上下文：当前地图、基线报告、现有研究。研究代理只拥有该隔离目录的报告，不修改主工作区或票。
- 领取人见Assignee。代理并非独占代码库；不得覆盖其他人的更改。主代理负责依赖和规划整合。

## Acceptance criteria

- [x] 每个候选有固定版本、许可证与一手源码链接；访问缺失或未知明确列出。
- [x] 结论落到现有工程问题，列出不能移植或尚未验证的部分。
- [x] 报告保存在研究分支并回传commit；本地tracker再追加resolution。

## Resolution comment

2026-10-17：由领取的研究代理完成公开一手源码核验。先订阅后触发、总deadline与清理可借鉴；保留已装Playwright公共API，不引入新runtime。

- 报告：[研究事件等待与 CDP 控制的可复用机制](../../../research/browser-event-waits-2026-10-17.md)。
- 研究分支：`D_m/research/browser-event-waits-20261017`；commit：`242f92cafb2f8726a5c27ca6e6f95a07461aaa4b`。仅单报告提交；主工作区分支未切换。
- 当前research副本与该commit报告字节一致；未复制上游实现代码、未安装／运行候选框架。
- 结论已纳入相关现有任务；研究完成不代表优化、原生Cua、安装或真实ATS验收。
