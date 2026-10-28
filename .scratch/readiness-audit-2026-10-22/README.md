# 当前可用性审计 — 2026-10-22

结论：申请产品主线已有实现，适合进入有限真实试用前的候选整合；尚不能宣称已达到稳定日常自动申请。当前真实申请和App维护暂停保持。本轮未修改生产代码、工单状态、事实库或App。

## 本轮核对

- 实时tracker：128张，94 closed、17 resolved、11 open、6 claimed。关闭比例不是产品完成率。
- 最新完整默认离线结果：4803 passed、2 skipped、572 deselected，0 failures/errors。读取既有ticket36-two-mainlines记录；本轮重新计算其860份冻结输入，全部一致。没有重跑完整套件。
- 本轮实际回归：source_retry、education_library_correction、pipeline_continuity、ashby_bootstrap，48 passed、1 deselected，19.47秒；默认marker保持。Ruff及git diff --check通过。
- 现装唯一主App的包内Python与checkout只读比较：69份相同，9份不同。不同模块为application_flow、application_full_latex、application_group_review、application_match、application_pipeline、application_resume、application_source_reuse、career_portal、loaded_code。此比较仅包含两边存在的career_evidence_graph Python文件，不是完整包清单或实际进程加载证明。

## 已完成且不应重复列待做

邮件持续入队、单岗顺序处理、匹配分流、完整材料与必要附稿主线、字段/附件执行、一次Continue、skip/return、人工Submit限制及结果观察均已有实现。39/40/41与42已按各自源码范围关闭；30/27/28/37有适用既有安装/恢复证据。

今天旧审计的明确JD失败重试及无绑定资格继承两问题已有后继修复。36两条指定主线已核对：本次人工稿与两库隔离；明确学历更正及旧接受绑定误拦截修复。不要继续追加内部新分组协议、PDF缓存、JD维护作为36门槛。

## 开始使用的实际差距

1. 将最新已验证修复整合进同一主App，并仅对变化做安装回归；保留原身份与回滚。
2. 验证真实邮箱保存后标签/归档、去重、账号隔离与unknown核对；35尚未有完整真实接受。
3. 在支持的真实岗位验证最新材料、字段/附件、人工修改后一次继续及当前邮箱回读；25/11/23持有相应范围。
4. 用户自然手动Submit后验证明确结果及续下一岗；34剩余真实闭环，不能为测试强迫投递。

## 功能边界

- Workable必要附稿发送仍明确unsupported；普通resume已有隔离传输证据，不能外推真实Workable验收。见application_worker_browser.py的unsupported_attachment_transport分支及20号票。
- 通用ATS完整reload、跨路径/跨源导航、未识别登录/草稿协议和SSO/MFA/CAPTCHA组合覆盖有限；18号票按准确可复现场景推进。
- Ashby公开初始化已有源码及固定安装场景；真实网站组合仍待验，33不是“未实现初始化”。
- 完整LaTeX输入超过128000 UTF-8字节会停止，错误resume_latex_context_too_large；这是现存取材规模限制，见application_full_latex.py:32和1099附近。旧有界证据出现486355字节并在模型前停止；不据此声称所有实际申请都会超限。
- 历史Chrome冷启动/后台附着问题仍留票；没有新复现不能宣称根因已解决，也不必把所有历史归因关闭作为有限试用门槛。

独立职业图研究仍需后继inventory研究接受、个人Grill-Me评审及三份真实JD效用验证。研究25%不是申请产品完成率，不阻普通申请。

## 证据导航

- [当前开发顺序](../../docs/development-plan.md)
- [最新36两主线及完整回归](../ticket36-two-mainlines-2026-10-22/README.md)
- [现有主App安装场景及限度](../main-app-maintenance-2026-10-21/README.md)
- [17项未关闭清单：36下一步以最新开发计划替代旧条目](../work-audit-2026-10-22/remaining-tickets.md)

本轮为有界审计，不等于全部代码无缺陷证明。不据测试数量给出可靠性百分比或无依据工期。
