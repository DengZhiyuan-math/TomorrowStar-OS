# 修正并验证全量只读票据查询

Type: task
Label: wayfinder:task
Status: closed
Triage: done
Closure reason: completed
Completion: read-only-full-tracker-query-verified
Priority: P2
Interaction: AFK
Assignee: 01a15491/root
Created: 2026-10-19
Updated: 2026-10-19
Parent: [交付 Gmail 岗位筛选与专用简历稳定版](../map.md)
Blocked by: none

## Problem

[旧查询](../../open-ticket-audit-2026-10-18/README.md#查询与检查)只枚举有map.md的目录，且不识别粗体元数据，漏掉README持有的稳定性票。[当前审计](../../work-audit-2026-10-19/README.md)已手动补全快照，但旧查询仍未修复。本票作为材料地图下的跨图维护后继，不另建产品地图，不阻塞材料25或任一人工接受票。

## What to build

最小修正并验证现有只读查询，使其输出完整的正式子票、元数据未知项、依赖错误及机械前沿。复用旧命令；确需抽取时只用最小标准库脚本，不新增依赖、持久化状态库或票据框架。

## Acceptance criteria

- [x] 从规范顶层 `.scratch/*/issues/*.md` 枚举全部正式实体票，包含无map.md而由README导航的稳定性目录；排除嵌套before、history、baseline、candidate、payload和测试夹具／旧审计副本。路径身份去重，父地图与导航本身不算子票。
- [x] 正确读取普通与粗体Markdown元数据，包括Status、Assignee、Triage、Interaction／Type、Claim state和Blocked by。缺失、空或无法解析的领取记录保留未知；不得归一化为none。坏元数据提供明确诊断，不静默漏票或放行。
- [x] 依赖按票据所在目录解析跨图相对链接。缺失或集合外依赖、环及活动票依赖行政superseded均明确报错；none／无前置可读。closed／resolved是关闭状态，superseded须单列，不能当作工程完成或已完成前置。
- [x] 机械前沿仅满足open、明确Assignee=none且所有直接前置实际完成；另行显示HITL／needs-info、暂停路线及归属未知，绝不由机械就绪推导真实执行许可或人工接受。
- [x] 同时给出全量、七地图子集、既有正式23票及当前交付线的清楚口径；从当前路径／既有发布身份推导，不硬编码107、109等时点总数，不把新增后继伪装成原23票。保留原发布身份及研究／行政票排除口径。
- [x] 用最小临时合成目录覆盖map与README目录、普通／粗体、缺Assignee、已关闭／行政票、跨图依赖、缺失依赖、循环和嵌套历史排除；再只读核对执行时真实tracker。对有效／无效输入给出可重复的输出或失败状态。
- [x] 重复查询对票据、领取、历史证据及元数据无写入；不读取私人配置／职业正文，不调用App、浏览器、邮箱、模型或网络。不得通过修票掩盖诊断结果。
- [x] 更新活动导航为已验证命令，旧命令和原输出按历史保留；静态数据快照明确标日期，不冒充实时状态。记录本切片有效验证；若仅修改文档查询，做命令、结果和链接核对，不增加无关测试框架。

## Ownership and boundary

最小责任为旧开放票审计页的查询块、总导航／材料导航的查询入口，以及确有必要的最小只读帮助脚本及定向测试。不得修改业务引擎、既有票Status／Assignee、接受结论或任何私人运行记录。共享文件修改须协调，不回退其他人的改动。

2026-10-19：用户批准正式新增。本票无技术前置，open／ready-for-agent／none；本次发布不领取或实施查询修复。真实申请继续暂停，执行本票也不授予外部动作许可。

## Claim — 2026-10-19

用户明确要求执行本票。核对open／none及无前置后，由01a15491/root领取；仅修正只读查询、定向合成验证及导航，不读取私人职业正文或调用App／浏览器／邮箱／模型，不恢复真实申请。其他票的状态、领取及全部历史证据保持。

## Resolution — 2026-10-19

已完成标准库只读[查询脚本](../../../scripts/query_tickets.py)和[CLI回归](../../../tests/test_ticket_query.py)，32项定向测试及独立13组合成复核通过。支持README目录、两种粗体与普通元数据、裸数字／跨图依赖、未知领取、环／集合外／行政票错误及按原发布身份推导口径；未知字段只诊断，不修票，不授权真实执行。

原查询和导航字节、RED、首次现场兼容失败与后继结果保留在[执行记录](../../complete-tracker-query-2026-10-19/README.md)。闭票后全量109／19未结案，地图99／17，原正式23／2，当前交付33／3。重复查询输出一致，输入字节和mtime不变；其他108张原票、原领取与历史证据保持。本票保留执行者01a15491/root，按只读查询范围结案；材料25、人审、研究与真实申请暂停不受影响。
