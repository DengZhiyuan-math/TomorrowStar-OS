# 核验通用控件与草稿传输契约的复用边界

Type: research
Label: wayfinder:research
Status: closed
Interaction: AFK
Assignee: worker_form_research
Parent: [申请 worker 下一阶段：稳定性、普适性与效率决策地图](../map.md)
Blocked by: none

## Question

哪些标准控件、可访问标签和浏览器事件可以跨企业直接复用？哪些岗位身份、字段值映射、自动保存与附件传输必须按站点契约核验？怎样以表单能力分层提高覆盖，而不把“支持一个平台”误认为“支持该平台所有表单”？

## Evidence and assets

- [现有通用控件](../../../src/career_evidence_graph/hosted_ats.py)
- [已核验 Ashby 草稿契约](../../../src/career_evidence_graph/ashby_drafts.py)
- [通用流程](../../../docs/generic-application-worker.md)
- [历史平台评估](../../../docs/worker-platform-assessment-2026-10-10.md)

## Resolution requirements

先领取。使用 research 技能，核验 HTML / ARIA / Playwright 规范及 Lever、Greenhouse、Ashby 官方文档。只读源码，不寻找或填写新的真实岗位。
明确公开岗位数据、雇主申请 API 与候选人原生浏览器流程的区别；不得推荐借用雇主权限。
报告给出直接复用 / 最小契约 / 人工处理的矩阵，覆盖文本、选项、自定义组合框、动态必填、附件、多步和 iframe。
只有新增具体需求才建议新增依赖。不得放宽到域名级或 operationName 级许可，不承诺“隐藏 Submit 就不会发送资料”。
研究报告记录分支、revision 和当前未提交实现的哈希上下文。以 resolution comment 记录事实；通用支持范围留给 HITL 决策票。

## Resolution comment

2026-10-11，worker_form_research：完成[单一研究报告](../../../research/application-worker-form-contracts-2026-10-11.md)。
报告覆盖文本、选项、自定义组合框、动态必填、附件、多步和 iframe 的直接复用／最小契约／人工处理矩阵。
HTML／ARIA／Playwright 标准提供控件语义与操作；岗位身份、答案含义、服务端值、条件字段、自动保存与附件发送仍需按表单核验。
公开岗位读取、雇主申请写入 API 和候选人原生浏览器流程分别记录；不索取雇主凭据，不放宽到域名级或 operationName 级 mutation 许可。
隐藏 Submit 不能证明资料未发送。原生控件支持也不能证明平台所有企业表单均受支持。

源码来自当前未提交主 checkout。清单中 17 个源码／测试 SHA256 均匹配 [source-hashes.json](../../../validation/application-automation/2026-10-11/workflow-consolidation/source-hashes.json)。
清单 SHA256：`3093bec7ec614af6685cfe551a16af3bd441c4752d677f08ef2394c241595e88`。
研究分支：`D_m/research/application-worker-form-contracts-20261011`。
起点 revision：`e4a26d0c24311d014d478f7f92e58a88e6709b4b`。
单报告 commit：`16d409dd96571a05e02a3310ba9deecec9852a25`。
隔离 worktree：`/private/tmp/tomorrowstar-form-contracts-research-20261011`。
主 checkout 副本与提交报告逐字节相同；报告 SHA256：`55b4e4a502130617eff15bd92a2e332069f21fefa0ce5615a67b39c2b8905670`。

核验仅包含官方文档、源码哈希、报告本地链接和 Git 空白检查。未运行 worker／新行为测试，未寻找或访问新真实岗位，未读取个人数据，未上传、提交或调用模型。
候选扩展只在具体样本阻塞后考虑；本轮未证明需要新依赖。通用支持范围、跨企业样本和真实验收留给 HITL 决策票，未由研究关闭。
