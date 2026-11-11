# 确定接入验收与实施交接条件

Type: grilling
Label: wayfinder:grilling
Status: closed
Priority: P1
Interaction: HITL
Assignee: Codex /root
Created: 2026-10-25
Parent: [简历与 Cover Letter 同岗并发生成接入规划](../map.md)
Blocked by: [确定人工修改与已有文稿的复用](04-human-reuse.md)、[确定页面需求识别与申请就绪规则](06-page-readiness.md)
Triage: resolved

## Question

怎样判定后续实施满足全部已确认要求，并交接一条最小、可分步验证的落地路线，
而不是把静态模板、离线测试或两个串行模型调用当作完整交付？

本票只整合前置决策，不补做它们的选择。需要明确：

- 列出后续实施的最小变更顺序、文件所有权与共享文件协调范围，分别引用各票
  resolution；不重新建立另一份需求或重复调度器。
- 验证矩阵覆盖：实际同岗重叠写作、共享固定输入、成功分支保留、局部失败、未知
  回执、pause／skip／重启、人工修改、旧任务与新页面复用。
- 内容样例覆盖：动机与技术证据连贯、一个／两个完整经历、责任与结果不增造、
  无机械总结、准确术语；引用结构检查不能冒充语义正确。
- 交付矩阵覆盖：必填／可选／无入口／未核实、文本优先、仅文件、切换方式、
  一页溢出、长文本限制、非 PDF／未支持 ATS、上传与回读分别核验。
- 分开说明静态源码与离线回归、实际作者、Prism 构建、安装版、真实表单及人工
  内容质量的证据。确定哪类交接可先完成，哪些真实阶段需另行获得执行授权。
- 规划完成、源码完成、安装同步与真实交付的结论如何分别记录；完整离线／浏览器
  回归范围按实际改动决定，不把旧绿色结果继承为本功能已通过。

完成时形成有顺序的实施交接与证据清单，每项归属明确、能够被独立核验。
本轮不写实现、不跑真实模型或 ATS，不更新 App；最终 Submit 不属于验收自动动作。

## Source locators

- [application_pipeline.py](../../../src/career_evidence_graph/application_pipeline.py)：现有单岗主流程。
- [application_flow.py](../../../src/career_evidence_graph/application_flow.py)：恢复与材料采用。
- [application_materials.py](../../../src/career_evidence_graph/application_materials.py)：附稿 Interface。
- [application_worker_browser.py](../../../src/career_evidence_graph/application_worker_browser.py)：实际交付回读。

## Comments

尚未领取或解决。本轮只建图；新决定记录为 resolution，不能把问题中的候选行为当作已实现。

### Resolution — 2026-10-25 源码实施与验证交接

实施顺序为内容契约与固定输入、独立实际作者、版本对终审、人工后继版本、
文本/按需 LaTeX、页面分类/交付/就绪、最后完整回归与交叉审查。
各 Module 所有权、恢复动作、配置和最终证据统一见 [实施记录](../implementation.md)。
验证矩阵包含实际 scoped runner 同步屏障、完整固定来源、成功分支保留、局部失败、
未知回执、取消/skip/重启、人工修改/TeX 接回、旧稿和新页面、文本优先、
可选/必需/无入口/未核实、一页/长度/格式、构建前已知失败与构建结果未知、readback。
引用/结构测试不等于真实语义质量；合成作者 runner 不等于远程作者。
源码、默认离线测试、隔离浏览器、Swift 类型检查、真实作者、实际 Prism、安装版、真实 ATS
各自记录。最终校验结果以实施记录的完成段为准，不继承历史绿色结果。
本轮不安装、不运行真实作者或 ATS，不自动 Submit。

最终验收：完整默认离线 6,786 passed / 2 skipped；相关隔离浏览器 48 passed；
Ruff、格式、diff、JavaScript 语法、Swift 类型检查通过。两组测试期间源码哈希一致。
结论为源码及合成验证完成，不代表安装版或真实模型/ATS 已验收。
