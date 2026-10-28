# MC-06：T07 交付已绑定正文与附件

Type: task
Label: wayfinder:task
Status: closed
Priority: P2
Interaction: AFK
Assignee: claude-code-367f651f/root
Created: 2026-10-26
Parent: [Module 剩余开发地图](../map.md)
Blocked by: [MC-05](05-t06-visual-actions.md)
Triage: closed-source-synthetic-native

## 问题与范围

在 T06 的新原页工具上提供当前任务的固定材料引用，复用既有文本/上传/懒构建实现。完整 M3 迁移不是硬前置；稳定现有 Interface 足够即接入。

## 文件所有权与并行边界

application_worker.py、application_worker_browser.py、application_materials.py 的工具适配；只消费既有材料所属 Interface，不搬作者状态。与 MC-03/04 按交付字段冻结接口、串行集成共享函数，不能双方新建解析器。

共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。
依赖边表示必要交付，不表示外部运行授权；测试记录中的 deselected 不抵充覆盖。

## 验收条件

- [x] 工具只接收适用固定引用；任意路径、错岗、错版本、旧材料、实际 PDF/hash/字段不符均拒绝。
- [x] 正文、懒 PDF、实际附件及回读属于同一固定交付；生成中正常等待，不重启 JD 分析或作者。
- [x] 上传响应丢失先核对原 attempt，不重传；按 JD/页面判必需性，可选明确失败带具体失败/重试项，必需失败/页面错误/unknown 不冒充完成。
- [x] 经真实新工具入口完成合成文本/附件路径和故障回归；不以旧 Workable 适配器或原 handoff 的测试代证。

## 既有证据与限制

[正式 T07](../../../docs/module-interfaces-and-migration-design.md#t07-已绑定材料的文本与文件交付工具)。原 Workable 上传限制仍由旧平台票持有。

需求以[正式设计](../../../docs/module-interfaces-and-migration-design.md)为准。R6 只证明原冻结源码与合成测试范围；本票如有新实现，
须记录实际改动、对应回归和审查，不能复用 R6 关闭新行为。未知结果、人工内容、原页、
原 journal 和历史记录保留，最终 Submit 手动。

关联历史范围：[原 Workable 票](../../single-job-application-flow-2026-10-16/issues/20-workable-resume-upload.md)；其原状态、负责人和接受结论保留。

## Comments

### 2026-10-27 接续认领（Europe/Zurich）

已通过现有只读查询器及票头重新核对本票open/unassigned；MC05限定验收已关闭，
硬前置满足。按用户全部剩余工单目标与父任务授权，由当前root认领。
[MC05最终验收](../../remaining-tickets-2026-10-26/mc05-native/final-acceptance-r5.md)、
[只读材料接缝图](../../remaining-tickets-2026-10-26/mc06-readonly-map.md)与
[入口计划](../../remaining-tickets-2026-10-26/MC06-entry-plan.md)供后续实施核对。
本次仅认领，无MC06源码改动或测试运行，四项验收保持未勾选。父任务另行开始实施；
不扩展实际模型、安装或真实ATS运行权限，不把MC05控件输入证明当作T07文本/附件交付。

### 2026-10-27 架构审计补充（Europe/Zurich）

[架构审计](../../work-audit-2026-10-27/architecture-audit.md)核对实际改动范围：除本票“文件所有权”所列文件外，实施还改动了
`cua_driver.py`、`application_codex_assist.py`（python-protocol 分片）、`ashby_drafts.py`（draft-proof 分片）
及 `remaining-tickets-2026-10-26/mc06-bound-materials/native-source` 下的 Rust 源码。这些改动均有接口计划记录；
本补充只更正所有权登记，不改变状态、认领、依赖或验收条件。结案时同步更新 MC-17 的入口清单。

### 2026-10-27 11:40 用户指示转交认领（Europe/Zurich）

用户在 Claude Code 会话中明确指示“直接接管”，认领由 `01a179dd-5d36-7390-b987-ffc07cb4d702/root`
转给 `claude-code-367f651f/root`。原持有者最后可见写入：native gates 20/21 与审计目录 10:29，
ACTIVE-HANDOFF 11:15。接管时状态以 [ACTIVE-HANDOFF 05:01 检查点](../../remaining-tickets-2026-10-26/ACTIVE-HANDOFF.md#mc06-actual-progress--2026-10-27-0501-checkpoint)
与 [10:xx 审计](../../remaining-tickets-2026-10-26/mc06-bound-materials/audit-2026-10-27/README.md) 为准：
Python 分片与 runner bridge 已有定向测试，Rust gates 01–21 GREEN；接口两项最终确认、源码冻结、
候选构建、完整验收、独立审查与关票均未进行。原持有者的检查点、日志和工作目录全部保留，不重写；
原会话如仍在运行，应停止对本票文件的写入。四项验收保持未勾选。

### 2026-10-27 11:50 接管检查点（Europe/Zurich）

格式修正一处测试文件；MC06 相关离线 11 文件重跑 380 passed / 8 deselected / 0 failed。
计划两项接口决定已在分片中落地，待冻结前独立审查确认。见
[接管检查点](../../remaining-tickets-2026-10-26/mc06-bound-materials/takeover-2026-10-27/README.md)。非验收。

### 2026-10-27 范围决定：Ashby/Workable 自动上传移入 fog（Europe/Zurich）

原生开发运行发现：Chrome 不把磁盘文件内容交给请求拦截器，Worker 守卫转发 Ashby 早期上传时会发出空文件。
用户决定本票只保证普通页面的一般可用性（文件留在上传框，最终手动 Submit 由浏览器发送）；Ashby/Workable
早期上传与原生文件交付的组合移入[地图“尚未细化”](../map.md)，写明原因与候选解决办法。
`DraftSession.allows` 保持一律拦截（fail closed），新增回归；原生用例 `material_upload_lost` 标记 skip 并指向 fog。
验收条件 3 中“上传响应丢失”的远端部分随之不在本票验收范围；其余条件不变。

### Resolution（2026-10-27，Europe/Zurich）

按普通页面范围结案（Ashby/Workable 早期上传已按用户决定移入[地图 fog](../map.md)）。同一冻结
1811 文件 `e71d5d41…`、候选 candidate-r2 `550d4621…`（1118 native 源；pin 仅改一行）：

- 完整默认离线 8103：8100 passed / 3 skipped / 0 failed；受影响隔离浏览器 286：281 passed / 5 native opt-in skips / 0 failed；
  实际 native 8：01 文本、02 文件、03 篡改文件、04 错字段、05 结果未知、06 无效目标、07 中途停止 passed，08 Ashby 上传按 fog skip。
  每例一次、无重试/信号，自动清理，运行前后源码一致。见[验收记录](../../remaining-tickets-2026-10-26/mc06-bound-materials/acceptance/README.md)。
- 独立证据审查 READY-TO-CLOSE，无 P1：[final-evidence-review](../../remaining-tickets-2026-10-26/mc06-bound-materials/acceptance/final-evidence-review.md)
  （全部 1811 冻结项重算一致）；冻结前审查见 [prefreeze-review](../../remaining-tickets-2026-10-26/mc06-bound-materials/prefreeze-review/README.md)。

实际改动（均先写失败回归）：Rust `borrowed_call` 在读页前先拒绝未决调用（gates 22–24）；Worker 在原生会话交出期间只用保留的
原页句柄观察（`test_yielded_native_session_is_not_used_for_host_material_context`）；返回后的已撤权回执仍做严格核对
（`test_returned_native_receipt_still_reconciles_an_observed_material_call`）；隐藏字节上传一律拦截
（`test_upload_with_browser_hidden_file_bytes_fails_closed`）；网络许可保留停止/故障门（6 例）；harness 依原生契约修正五处。

验收条件对应：1 = native 03/04 + 离线解析/协议/代理测试；2 = native 01/02，生成中等待仅有离线证据（resolver pending/catalog）；
3 = native 05/06/07 + 离线 catalog/draft-proof/guard，可选失败带重试项与过期/错岗引用仅有离线证据，远端“上传响应丢失”随 fog 不在本票；
4 = 全部经候选驱动上的新工具 `browser_deliver_material`，未用旧 Workable 适配器代证。

限制：Ashby 页面上原生文件交付后，页面自身的早期上传被拦截并停止页面（fail closed，不支持 Ashby）。审查 P3：交出期间跳过
原生 owner 读是全局的，也作用于后端恢复的只读捕获（`application_worker_browser.py` 约 1532 行），且缺少“交出期间驱动失败/退出”的
负向回归；原生 harness 的 WorkerService 不带 Portal 的 `delivery_reader`。未运行实际模型、安装签名 App 或真实 ATS；最终 Submit 手动；
未提交 git。MC-17 入口清单已同步；MC-18 基线未变（离线套件中通过）。
