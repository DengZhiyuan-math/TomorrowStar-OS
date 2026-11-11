# 按实际原因显示资料准备状态

Type: task
Label: wayfinder:task
Status: closed
Closure reason: completed
Completion: source-readiness-reason-messages-verified
Triage: done
Priority: P1
Interaction: AFK
Assignee: 01a14fd0/root
Created: 2026-10-18
Updated: 2026-10-18
Parent: [交付 Gmail 岗位筛选与专用简历稳定版](../map.md)
Blocked by: [核验既有资料覆盖与单岗选择依据](17-source-coverage-and-job-selection.md)

## Question

结构化个人资料有效、仅有文档无法读取时，怎样准确显示读取缺口，而不再提示用户补齐已经存在的个人资料？

## Observed defect

`preparation_checks` 将profile缺失与任意不可读文档合并为同一句“职业资料不完整；请补齐个人资料并检查无法读取的文档”。有效profile加一项不可读历史文档即可复现，见[纯合成复现](../../source-coverage-execution-2026-10-18/readiness-reproduction.json)。这不是用户事实缺失或能力不足的证据。

## Scope and acceptance

- [x] 复用现有 `sources.profile`、`profile_issue` 和coverage错误，不增加另一份来源目录、事实库或后台扫描。
- [x] 区分没有可用取材、profile缺失／无效、文档读取失败和全部可读；profile有效时不要求补齐profile。
- [x] 不可读文档保留原因与未读范围；消息不得将超过读取上限、未下载或读取失败改写为个人事实缺失。
- [x] 对缺profile、有效profile但部分文档不可读、无可用item及完整来源做有意义的合成回归；保持当前状态守卫和隐私边界。
- [x] 不修改读取上限、不静默忽略未读文档，不自动导入旧CV或提升清单身份为个人能力／资格／材料接受，也不改变评分、生成或申请授权。
- [x] 更新候选整链验收所需证据；本票只解决状态解释，不宣称资料、事实或全流程已接受。

## Ownership and boundaries

最小责任范围为 `application_preparation.py` 的现有source状态说明及相关测试；必要时适配既有页面显示，不重做扫描器。先核对前置、唯一领取人和当前checkout；遵守开发约定与TDD，保留其他会话改动。真实资料保持只读，真实申请继续暂停。

## Resolution comment

2026-10-18 — 本票源码修复与合成回归完成。

仅在 `application_preparation.py` 按既有profile、profile_issue及文档error_code生成说明：无可用经历条目、个人资料缺失／无效／不可读、文档超限／UTF-8格式问题／暂不可读及全部可读分别提示。有效profile不再要求补齐；组合问题同时说明；文案不含私人字段值、路径或异常正文。

原source_status及模块原有其余逻辑与修改前AST一致；读取上限、扫描器、评分、资格判断、事实审核、材料确认和worker守卫均未改。未导入旧CV、提升清单身份或迁移批准。

TDD先经真实HTTP状态接口复现，再逐项修复；相关139项回归及独立准备入口17项通过。完整默认离线回归通过，Ruff及全仓格式通过。数字、命令、候选身份、精确差异、独立复核和范围检查见[按实际原因显示资料准备状态：源码验证](../../source-readiness-reasons-2026-10-18/README.md)。原失败现象、原始复现和改前文件均保留。

关闭范围仅为本提示修复。实际安装版未更新；当前候选冻结／组合／安装仍由[核对当前安装候选的完整材料准备链](19-current-candidate-journey.md)持有，完整CV契约及所有人工材料／版本接受仍独立。本轮未读取或改写私人资料，未刷新邮箱、调用真实模型、生成真实材料、填写、上传、Submit或恢复真实worker；真实申请继续暂停。

### 2026-10-18 — Claim

用户明确授权执行本票，前置「核验既有资料覆盖与单岗选择依据」已closed；本票由 `01a14fd0/root` 领取。只修改现有准备状态原因显示并补合成回归，保持读取限制、全部状态守卫和事实／材料审核门槛；真实申请继续暂停。本轮不改私人记录、不更新安装版、不调用邮箱／模型／ATS。
