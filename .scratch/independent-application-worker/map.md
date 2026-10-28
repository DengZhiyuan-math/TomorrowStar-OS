# 独立申请 worker 开发决策地图

Label: wayfinder:map
Status: resolved
Created: 2026-10-09
Resolved: 2026-10-10

## Destination

形成可交给开发执行的首版规格与验收顺序：独立本地 worker 批量填写已选定的
Lever / Greenhouse 岗位，复用已确认答案，遇到未知问题等待用户补充并记入信息库，
最终由用户复核并提交。

## Notes

- 本次产出是开发决策地图。实际实现、安装运行时和真实岗位测试属于后续执行。
- 用户已确认首版为独立本地 worker，批量填表，最终人工 Submit。
- 用户在 2026-10-09 明确要求：“对于未知问题，应该经过我补充后，也补充信息库中，避免一次一次重复问我”。补充并复用答案是首版要求，不再重复询问是否需要该功能。
- 本地图中的“信息库”指申请答案库。它保存申请事实和确认答案，不产生 Career Evidence Graph 的 Skill 评分。
- 开发基线以已解决的运行时与执行边界决策为准；研究和规格不构成已实现架构。
- 优先复用现有 Job Apply 存储 helper、岗位识别、revision 检查和原记录写回能力。只有明确缺口才新增代码或依赖。
- 每次 HITL 决策使用 [grilling](/Volumes/Codex-Workspace/live/home/zhdeng/.codex/skills/grilling/SKILL.md) 与 [domain-modeling](/Volumes/Codex-Workspace/live/home/zhdeng/.codex/skills/domain-modeling/SKILL.md)；按一个问题一次交流。先读相关事实，再询问用户。
- 研究票使用 research 技能。研究采用固定 revision、许可证和合成输入。研究分支采用仓库规定的 `D_m/research/<name>` 前缀。
- 现有原申请记录仍是申请状态来源。个人答案、附件、认证状态和原始 trace 留在显式私人目录。公共规格只含合成示例。
- 申请答案的保存与复用规则以已解决子票为准；不把推测内容标记为用户确认。
- 保留现有未提交修改。此地图不变更当前职业图验证里程碑。

现有事实入口：

- [独立后台投递程序可行性评估](../../research/independent-application-runner-feasibility-2026-10-09.md)
- [框架版本、许可证与数据路径](../../research/application-automation-framework-sources-2026-10-09.md)
- [当前 Codex 填表接入](../../docs/application-automation.md)
- [现有三轮合成浏览器测试](../../validation/application-automation/2026-10-09/three-rounds-01/README.md)
- [个人数据边界](../../docs/data-boundaries.md)

## Decisions so far

<!-- 只索引已解决票。问题详情和答案保存在子票中。 -->

- [核验现有答案库能否支持补充后复用与任务恢复](issues/01-answer-store-reuse.md)：复用现有 helper；调用方补齐适用范围核对、答案版本失效和统一串行写入。
- [确定申请答案库的复用范围与更新规则](issues/02-answer-library-contract.md)：系统提出范围、自动判断同义；已确认答案默认保存并在原范围内复用，支持“仅本次”例外。
- [确定批次输入与原申请记录写回边界](issues/03-batch-input-writeback.md)：勾选已有记录，逐岗位选简历；自动同步待办，真实投递状态按对应确认更新。
- [确定独立运行时与浏览器生命周期](issues/04-runtime-browser-lifecycle.md)：接入现有 Web 后端；专用可见浏览器，关闭控制界面暂停并保留有效页面。
- [确定任务暂停、恢复、取消与去重语义](issues/05-recovery-cancellation.md)：未知问题仅暂停该岗位；补充后自动恢复符合条件的岗位，整批暂停仍须用户继续。
- [确定 ATS 适配、上传与人工提交的执行边界](issues/06-ats-execution-boundary.md)：允许 Codex 等工具判断同义；固定适配器填表与上传，最终由用户接管真实页面。
- [确定未知问题补充与最终复核的交接方式](issues/07-input-review-handoff.md)：采用 A，集中补充同范围问题；逐岗位展示简历、进度和真实复核入口。
- [确定首版验收条件与开发顺序](issues/08-acceptance-build-order.md)：先验收 Lever 完整闭环并提供可用预览，再接 Greenhouse；双平台通过才完成首版。

## Not yet specified

没有待解决的开发前决策。真实公司定制表单仍可能出现未覆盖情况，按
[确定 ATS 适配、上传与人工提交的执行边界](issues/06-ats-execution-boundary.md)停止该岗位，
并按[确定首版验收条件与开发顺序](issues/08-acceptance-build-order.md)记录验证边界。
若实际样本要求扩大支持范围，再形成新的决策，不在本地图预先建设未知能力。

## Closeout

2026-10-10：全部子票已解决，已形成开发规格与逐步验收入口。
本地图的规划目标已完成；worker 实现、运行及真实申请验证仍属于后续执行。

## Out of scope

- 本轮编写或启动 worker、安装 Playwright、执行真实申请、上传私人附件。
- 自动最终提交、绕过 CAPTCHA/MFA、复制 Codex 或日常浏览器认证资料。
- LinkedIn、Workday、Oracle 等新增平台，以及跨平台全天无人值守承诺。
- 自动寻找岗位、自动推断个人事实、自动生成或改写简历、通用 LLM 浏览器代理。
- 多 worker、分布式队列、云浏览器、云部署和额外数据库；受限模型判断按已解决执行边界使用。
- 改动职业经历接受、Grill-Me、Skill 评分或当前里程碑的验收语义。
