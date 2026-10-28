# 34号票：复用安装证据后的逐项核对

2026-10-21，Europe/Zurich。按票首当前9项精简验收核对。**1—7及9按适用源码、模拟组合和安装证据记录满足；8部分满足。** 34保持claimed，原负责人`01a15926/root`及依赖不变，Triage改为`awaiting-real-acceptance`。没有发现需要补代码或重跑模拟矩阵的具体缺口。

本轮只读取已有记录、XML及文件指纹，并更新本报告、34当前勾选和导航。没有运行测试、旧证明矩阵、App、浏览器、worker、权限探针、模型、邮箱或真实申请；没有修改产品源码、正式配置、unknown结果、fill intent、原材料或接受记录。

## 当前9项

| 项 | 结论 | 适用证据及准确范围 |
| --- | --- | --- |
| 1 全局未处理记录、持续增量、无整轮限额 | 满足 | 既有推荐队列/连续性回归；G1实际分页、重开、归档丢回包后inspect及等待时收录。兼容的旧有限批次入口不是当前队列总限额；没有声称实际邮箱已长期运行。 |
| 2 低分、普通、精准三路 | 满足 | 现有默认XML中matching_routes的20项通过，普通无主观批准、低路由记因、精准完整稿后等待均有据；完整材料及附稿消费专业模块，不新增数值阈值。真实三路材料质量不由合成PDF推断。 |
| 3 重要事实/冲突/未知停当前岗，入库后继续 | 满足 | capture、邮件组合、国家Continue及既有信息库/语言回归；G1缺国家等待仍只收录，一次Continue复用已完成阶段。当前问题先查已有事实，答案保存到相应库；没有汇总未来问题或以未知结果推进。 |
| 4 共享材料、保留人工修改、一次继续、Submit结果消费 | 满足，工程/模拟范围 | 40共享完整LaTeX、编译/导出、人工底稿及复用；39/41指定岗接口和一次继续。真实Flow/Worker/Runner的认证HTTP组合消费模拟success/rejected/unknown，只有success选下一来源，无例行提交声明。G3实际字段/单次上传/SHA/邮箱更正不重传支持执行接口；G3本身是兼容HTML/PDF路线，不声称原生自动完整LaTeX整链。真实闭环留第8项。 |
| 5 阶段/材料复用、skip返回、重开、页状态派生 | 满足 | 39最终已删除Flow页面status副本写入及据副本恢复，GET只读投影；该实现已随包安装。G1返回原task/PDF，G3同runtime/page/document/附件重开；公开恢复/材料更新回归补足故障与影响范围。活旧worker跨版本执行不是本轮新测。 |
| 6 候选追加去重不等于激活 | 满足 | 公开capture/background-poll和真实Flow组合覆盖等待事实、未知结果、暂停时仅收录；原执行岗、page/PDF/intent/history保持，后岗不分析/生成/填写。G1实际等待只收录；非空unknown intent沿用源码组合，未在安装版新注入。 |
| 7 明确完成续岗、skip续岗和返回 | 满足，模拟组合范围 | 邮件整合11项包含success/rejected/unknown及跨第二来源skip/return；只有明确success或显式skip离开当前岗，return恢复原task/page/PDF/unknown intent。G1实际skip/return。结果组合只证明下一来源被选择，不声称第二worker已完成填传。 |
| 8 旧追加失败保留、模拟与真实分层 | 部分满足 | 原batch_exists失败、旧矛盾断言及修订说明均保留；后继分别覆盖收录/去重/等待不切岗/成功/skip/return，不取消原批次或删除保护。源码组合和安装证据已分层；**真实用户Submit→系统明确结果→下一岗仍实际未验**，不能据“已标未验”将整票关闭。 |
| 9 仅持有编排/路由，不重建模块 | 满足 | 下方调用清单消费现有Pipeline/Flow/Worker/材料/Intake；39/40/41已完成对应源码收尾。不新增主控、状态库、框架或日常批准。 |

“满足”采用分层证据，不表示9项在一个原生进程逐场景重演。实际安装G0—G3与30后继worker的范围分别保留，不合成为未发生的真实闭环。

## 真正未覆盖的边界

34仅剩真实接受：**用户恢复真实申请后，以适用真实岗位取得自然人工Submit→系统读取可归属的明确结果→下一岗的实际证据，并记录对应材料、字段、附件和原页范围。** 当前真实申请继续暂停；不为验收强迫投递，不要求现在解除暂停，不新增例行草稿/PDF确认。

依据[产品规范](../../docs/single-job-flow.md)“实现与验收”和[既有归属复核](../usable-first-wayfinder-audit-2026-10-21/reorganization-review.md)末节：取消真实接受反向阻塞仅适用于30的安装合成票，34后台流程仍保留其原真实范围。第4、7项已验证的工程行为与第8项未发生的真实接受分别记录。

以下是现有证据的限度，不新增为工程前置：长时间真实邮箱运行、三路真实材料质量、原生完整LaTeX单进程整链、第二worker完整填传未在本次窗口逐项新演；活旧worker跨版本和非空unknown intent安装恢复未新测。仅承诺已支持线路，不能推导任意ATS/SSO/跨源流程覆盖。

## 30及安装证据适用性

- [30实际worker结案回执](../ticket30-worker-loaded-mapping-2026-10-21/installed-verification.json)：同一主App、原固定签名，实际PID/run及worker完整角色映射匹配；安装manifest SHA为`1e7ca91bd194cedfe98d77eac77b70b2093115d202f69aa6a889b73213f3f462`。该worker范围是固定Ashby岗位/组织读取、缺答案等待及暂停原页观察，字段/上传/Submit均0。它补齐加载证据，没有重做G3上传。
- `worker.package_mapping=verified`；总体readiness及旧compatibility仍unknown，can_fill诊断false。不将其写成全绿，也不恢复已退役的日常证明门槛。旧null回执、首次夹具失败、实际回滚、旧unknown/fill intent保全记录原样保留。
- [同一主App的G0—G3逐项证据](../main-app-maintenance-2026-10-21/acceptance.md)、[后继源码结果](../main-app-maintenance-2026-10-21/successor-source-readback.json)：默认4661通过/2跳过、受影响221、浏览器86是既有运行，集合不相加；本轮没有重新执行。
- [本次指纹适用性](source-applicability.json)：原820输入仅开发计划与worker CLI启动导入有差异；worker差异由30既有48项及实际安装worker覆盖，7项后继输入仍匹配。未将820全部冒称当前字节相同。
- [读取现有XML得到的节点](reused-default-nodes.json)：13个适用模块249个通过节点，无执行。历史22项Submit接收端的适用性采用[已有对照](../ticket30-installed-reconciliation-2026-10-21/historical-submit-applicability.json)；它们不属于v3的86项重新运行。30后继仅CLI启动导入变化，未修改Submit业务方法。
- [共享材料/入口清单](../ticket39-41-source-2026-10-21/materials-entrypoints.md)、[状态派生](../ticket39-41-source-2026-10-21/state-and-acceptance.md)、[真实Flow模拟结果/返回组合](../ticket30-34-remaining-2026-10-21/README.md)。旧报告的“39/40/41源码未收尾”“worker loaded null”是当时时点，不再列为当前缺口。
- [已接受PDF绑定](../material15-accepted-binding-2026-10-19/verification.json)及[材料15真实批次核对](../material15-real-batch-2026-10-19/verification.json)继续复用其原范围。本轮没有重新确认既有事实、生成、编译、采用或改变该PDF；单份PDF接受不扩展为所有岗位材料或真实Submit接受。

## 当前编排调用与职责

| 34消费的调用 | 专业模块继续持有 |
| --- | --- |
| `request(start)`→`_queue`→`intake.refresh(capture_only=True)`；`_poll_mail`、`_capture_mail` | Intake/RecommendationStore的全局保存、去重及处理记录；42邮件设置/进度 |
| `_queue`→`intake.acquire/select`；`_match`→Flow分析及categorical route | 当前源取得、两库事实及匹配语义；等待时不取后岗JD |
| `_materials`→`prepare_automatic_materials/start(resume/export)` | Flow阶段/attempt及共享ResumeStore、完整LaTeX、Prism、导出/材料历史 |
| `prepare_worker`、`_start_worker`、`_current_request/continue-current` | Worker指定岗、命令队列、owner/page/intent与Runner普通动作；Flow只存batch/job引用 |
| `_observe_submission`、`_leave_current/select-current` | Worker明确结果观察；Pipeline当前岗/队列/skip/return。未知先inspect，不重放 |
| 默认展示、当前岗控制及跟随 | 41既有界面；不启用备用MaterialBatch/lab/handoff成为第二默认调度器 |

父阶段[调用清单](../ticket34-30-integration-preparation-2026-10-21/call-inventory.md)和[后继清单](../ticket30-34-remaining-2026-10-21/calls-and-remaining.md)保留原文；其中G1尚无后台、39副本仍待收尾的旧限制由后继结果替代。

原票/计划/地图字节在`before/`。独立只读审阅同意8项满足、第8部分及继续claimed；[最终读回](verification.json)记录勾选、历史保全、tracker与本轮改动范围。
