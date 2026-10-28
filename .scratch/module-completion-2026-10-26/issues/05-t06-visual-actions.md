# MC-05：JSON 交接与 Codex 原页直接接管

Type: task
Label: wayfinder:task
Status: closed
Priority: P1
Interaction: AFK
Assignee: 01a179dd-5d36-7390-b987-ffc07cb4d702/root
Created: 2026-10-26
Parent: [Module 剩余开发地图](../map.md)
Blocked by: [MC-00](00-r6-source-baseline.md)
Triage: native-and-synthetic-verified
Closure reason: verified

## 问题与范围

按用户本轮更正后的 [T06 JSON 交接契约](../../../docs/module-interfaces-and-migration-design.md#codex-takeover-json-contract)
实施：系统脚本先填写，无法处理时通过 JSON 交接进度、阻塞、未决动作及 DOM/可访问性
定位线索，由已有 Codex computer use 能力直接接续原 Page。截图仅在控件确需视觉判断
时按需使用；不继续自定义 observe_visual/act_visual/reconcile_visual 执行通道。

## 文件所有权与并行边界

沿用 Worker 的既有身份、状态与动作记录，在所属 Interface 生成交接 JSON；
Browser 只在需要时提供当前原页的有界 DOM/可访问性摘要。具体直接接管装配须核对
已有能力，不凭 metadata/只读工具或 JSON 成功假定已经可执行。共享 Worker/Browser
改动与 MC-01/MC-08 串行协调，不覆盖其他工作的修改。

## 验收条件

- [x] JSON 有版本、完整原接管引用、已证完成项、剩余工作、阻塞、未决动作、页面摘要、材料引用及下一步；结构和来源经校验，复用原业务记录。
- [x] 交接进度无需截图解释；DOM/可访问性定位线索有观察时间和文档绑定，操作前重新核对当前目标，不把 HTML 或旧坐标当作有效目标。
- [x] 脚本失败后由一个 Codex 控制者直接接续同一 Page；不增加截图判断进度的中间关卡，不另建自定义视觉动作执行通道。
- [x] 保留已有资料、人工内容和历史；unknown 不当作未执行，不能重放；撤权、在途排空、失联和保存失败均保留原结果与占用，最终 Submit 手动。
- [x] 源码与隔离合成页回归、独立审查完成；真实接管工具、安装版与真实 ATS 证据按原分层边界记录，不用低层替身关闭高层验收。

## 既有证据与限制

R6、T01–T05 和旧 valueRef 调查保留原证据范围。用户更正已取代旧视觉动作方案；
本轮未完成草稿已从活动源码/测试撤下并归档于 [superseded-visual-draft](../superseded-visual-draft/README.md)。
JSON 生成、无截图 DOM 上下文和只读 Adapter 传输已接入，验证记录见
[JSON 源码实现](../json-handoff-implementation/implementation.md)。用户已授权扩展底层原生
会话交接，源码与验证记录见[原生交接](../../native-cua-session-handover-2026-10-26/README.md)。
原[会话绑定缺口](../json-handoff-implementation/native-route-gap.md)保留为扩展前调查；
票据保持 claimed，不用源码或替身测试解除实际接管的验收条件。

关联历史范围：[原平台控件票](../../single-job-application-flow-2026-10-16/issues/18-generic-ats-controls.md)；其原状态、负责人和接受结论保留。

## Comments

### 2026-10-26 接续认领（Europe/Zurich）

用户通过 wayfinder 要求对接当前 frontier。已核对现有查询结果、父地图优先顺序、
当前交接、正式 T06 契约与 valueRef 窄复核；按地图“优先推进 T06 主链”认领本票。
MC-00 已关闭，硬前置满足；本次不接管其他旧票或其他 frontier。

本次完成认领与上下文接续，尚未开始实现、运行测试或形成 resolution。
以下是后续实施的接续点，不表示新增行为已经交付：

1. 在现有 Worker/Browser Interface 落地 observe_visual、act_visual、reconcile_visual；
   默认 v1 与页面写入关闭保持，visual/v2 仅由可信配置绑定合成授权与 policy_digest。
2. 复用已有 confirmed answer、scope 与 revision 校验，保留 OTHER 特例；
   profile-only 无合法值来源时明确等待，不调用会初始化数据的 loader 兜底。
3. 先保存 intent，再锁外原线程操作原 Page；单次 observation、callId 幂等、
   unknown 阻断及保存失败证据均按正式契约实现。
4. 用隔离合成页面证明普通填写成功、HTTP/WS 最终提交接收为零，
   并重验 T04/T05 的撤权、在途排空、失联、导航及保存失败竞争，再独立审查。

本次未修改产品源码、测试或运行配置，未调用真实模型、安装 App 或操作真实 ATS。
验收复选框不变；本票未解决，后续 MC-06 仍被阻塞。

### 2026-10-26 用户更正与 JSON 格式确认（Europe/Zurich）

用户澄清原流程为“脚本填写，无法处理时 Codex computer use 直接接管”，并明确同意
进度与 DOM 定位线索分开表达，交接信息必须使用 JSON。当前技术细节以正式设计中的
[T06 JSON 交接与原页直接接管](../../../docs/module-interfaces-and-migration-design.md#codex-takeover-json-contract)
为准；此前认领记录和自定义视觉动作尝试仅为历史，不再作为实施要求。

未完成的视觉草稿已归档，三份活动生产文件恢复至实施前 R6 的精确字节；
JSON 与直接接管尚未实现，不关闭本票。未更新安装 App 或操作真实申请。

### 2026-10-26 JSON 交接实施进展（未解决整票）

按用户“继续开发”指令完成 Worker JSON 投影、原页无截图 DOM 摘要和 Adapter 单一
JSON 文本结果接线，复用既有身份、事件泵与停止机制。四项独立审查问题已补反例并修复，
当前验证见[实现与证据](../json-handoff-implementation/implementation.md)。

源码核对同时确认，当前原生 CLI/CuaDriver 不提供现成的原 Worker 会话移交入口。
JSON 交付不等于原页直接接管。该剩余条件未满足，因此本票未解决，后续依赖继续保留；
不启动旧自定义动作通道，也不修改全局工具配置、安装 App 或操作真实 ATS。

### 2026-10-26 用户授权扩展底层原生会话交接

用户明确选择“扩展到底层原生会话交接（推荐）”。已在保留原修复的独立 CuaDriver
源码副本中补充原 host 到专用 Codex proxy 的活连接交接，沿用原生浏览器工具、资源
namespace 和原 Page 身份。Worker、Adapter 与驱动之间保存 JSON 意图和回执；Python
不执行页面动作。旧只读引用不能升级，默认模式与现用 Driver 保留。

原生 CLI 350 项、核心 999 项回归通过；1 项需人工允许的真实浏览器连接案例未运行。
候选已构建、核对 1,118 个源码摘要，并通过实际 MCP 工具清单的只读 schema 检查。
独立审查发现的问题已修正并复核。详细来源、范围、候选、反例和日志见
[原生交接记录](../../native-cua-session-handover-2026-10-26/README.md)及
[审查记录](../../native-cua-session-handover-2026-10-26/review.md)。

第一轮 Python 整批回归发现 2 项默认启动调用兼容失败。已改为仅在启用原生模式时
传递新增参数，相关 31 项回归通过；最终整批 7,681 passed、2 skipped，随后相关隔离
浏览器 49 passed。同一 663 文件受验快照运行前后不变，1,118 个 native 源码和候选摘要
汇总复核一致。失败批次原样保留；浏览器首次被外层沙箱阻止启动，自动审查允许相同
源码重跑后通过。
原 HTTP/WS 和最终 Submit 守卫保留。当前原生控件源码不包含导航、上传或可靠填写完成
交回；这些仍属 T07/T08。本票维持 claimed，实际 native 原页输入未用替身证据关闭。

### 2026-10-26 全部剩余工单目标下接续（Europe/Zurich）

用户明确要求继续推进剩余全部 tickets。本会话已通过应用读取核对原负责人会话
`01a17870-e7c1-7743-a2c0-5f0622ce4bde` 最后实施轮为 completed、当前 notLoaded；
本次接续认领，原负责人、实现和失败记录保留在此前 Comments 与原证据中。
当前无另一个活动实施轮，也不把文件锁或旧运行记录当成仍在运行的证明。

先核对并完成真实 native 原页输入与既有停止/unknown/保存失败边界，证据与计划见
[剩余工单接续](../../remaining-tickets-2026-10-26/README.md)。后续按原依赖推进，
不以底层替身或仅完成源码代替本票及分层验收；最终 Submit 手动。

### 2026-10-26 实际 native tracer 与重新核验

当前接续已运行固定旧候选及真实 native daemon/proxy。真实集成依次暴露工具目录
返回对象、重复 browser_type 清单、trusted-session idle 上限与旧校验不一致三处
启动问题；Python 已修正，177 项相关替身协议/模块回归通过。随后真实原页快照
返回空字段 value=null，实际 browser_type 被 handoff_existing_content 拒绝。
此项实际 RED 及各阶段原始日志均保留，见
[bootstrap](../../remaining-tickets-2026-10-26/mc05-native/bootstrap.md)与
[实际 tracer 记录](../../remaining-tickets-2026-10-26/mc05-native/tracer-old-candidate-red/README.md)。

源码复核发现动作前目标语义及命中位置仍需补证，因此第二项复选框重新置为未完成；
JSON 无截图交付及原文档绑定的既有证据保留。后继原生源码正在补结构、当前值、
语义与命中复核，原封存候选不变。当前没有 native 输入成功结论，不关闭本票。

### 2026-10-26 后继真实输入通过，未知结果反例仍失败

R1 后继完成 native core 1,015 passed / 1 既有 ignored、CLI 358 passed、格式与
独立复核，并固定 1,118 个源码摘要。真实原页输入 tracer 1 passed：同一 Page 写入
并回读，input 事件为 1，Submit 为 0，正常停止确认 drained/return_ready，资源清理
完成；见[实际通过记录](../../remaining-tickets-2026-10-26/mc05-native/tracer-r1-green/README.md)。

随后实际 unknown 反例暴露 P1：输入后页面改写值，browser_input_incomplete 经过
MCP 规范化后未保留 unknown；同一 RPC ID 没有重放，但 fresh ref 与新 ID 导致第二次
实际输入。native ledger 错记两条 observed，Worker semantic_unknown=false。
这是实际失败，不能用此前单元回归通过关闭本票；见
[失败及精确现场](../../remaining-tickets-2026-10-26/mc05-native/tracer-r1-unknown/README.md)。
全部相关进程/profile/socket 已清理，原失败 runtime 记录原样保留。R1 source/candidate
已封存；修复仅在 source-r2 后继进行，随后须对原反例取得真实 GREEN。

### 2026-10-27 R2 未知结果真实反例通过，边界验收继续

R2 原生 core 1,025 passed / 1 既有 ignored、CLI 361 passed、SDK 107 passed，
格式和独立审查通过。候选来自构建前后不变的 1,118 文件源码快照，摘要为
`f78a5b3f10574a6e96b3c9dd05175acbe80853c82f7594f043a422664ba56aa7`；
仅更新专用 native pin，默认 driver 与安装 App 不变。详见
[R2 源码验证](../../remaining-tickets-2026-10-26/mc05-native/r2-native/README.md)。

正常原页输入通过。未知结果反例首轮暴露测试轮询顺序问题，原始失败记录保留；
独立复核后仅修复测试终态检查，再次实际运行通过。
[真实效果记录](../../remaining-tickets-2026-10-26/mc05-native/tracer-r2-unknown-retry/effect.json)
证明同 ID 返回缓存、fresh ref 与新 ID 确实发出并被
`handoff_native_effect_unresolved` 拒绝，实际 input=1、Submit=0，
原 Page/文档保持。native unknown 和 Worker semantic_unknown 保留，停止后
新接管拒绝；所有重试阶段实际达到，没有用撤权前未发送的请求替代证据。

其余点击保护、HTTP/WS Submit 守卫、保存失败及在途停止仍在串行实际验证。
最终冻结的完整 offline/browser 回归尚未完成；本票仍 claimed，后继依赖不变。
以上使用受控 app-server peer 和隔离合成页，不是真实模型、安装版或 ATS 验收。

### 2026-10-27 原生保存失败修复与退出检查剩余项

R3 修复原退出后写入竞态，platform 573 passed / 6 既有 ignored、core 1025 passed /
1 既有 ignored、CLI 361 passed、SDK 107 passed；真实网络守卫与焦点保护开发案例通过。
随后真实保存失败暴露 Adapter 会丢失持久化错误。最小修复保留真实 native completed
与 observed，同时持续保留业务 unknown 和精确保存错误，不允许新接管或动作重放。
206 项合成回归及独立审查通过。

[实际修复复验](../../remaining-tickets-2026-10-26/mc05-native/tracer-r3-save-after-adapter-fix/)
的业务断言已通过，但结果为 **1 passed + 1 teardown error**：退出查询返回 EPERM，
驱动按保守规则完整保留自有 profile。原始失败与 runtime.closed=false 保留；
后续只读查询表明进程和组已退出，不能倒推当时的查询错误无效。现正修复有界退出等待，
不把权限未知视为已退出。实际在途停止和最终同一冻结版本的整批验证仍待完成。
本票保持 claimed，不关闭依赖；受控 peer 证据不代替真实模型、安装 App 或 ATS。

### 2026-10-27 有界读取修复与当前 R5 兼容工作

R4 修复退出查询的暂时不确定状态，实际 save-after 案例已完整通过并自动清理。
原在途停止案例随后挂起；独立 A/B 诊断定位到 SIGALRM 会破坏 Playwright dispatcher。
有界 CDP 读取、迟到资源回收和事件泵期限处理已完成 359 项 focused offline、4 项
实际隔离浏览器测试与独立审查。原失败和中断记录保留；见
[有界读取证据](../../remaining-tickets-2026-10-26/mc05-native/inflight-pump/safe-cdp/README.md)。

原生在途复验在输入前遇到 bundle-path 拒绝，未验证到在途阶段。独立 daemon 内部
诊断证实，原次进程路径包含 `Google Chrome.app.bundle/Contents/MacOS/`，原解析器
仅接受 `.app/Contents/MacOS/`。R5 正在增加受限兼容：实际文件与既有浏览器候选
身份匹配、实际签名与 plist 核对、前后文件及进程代际复查，并处理新增读取和签名
调用的资源界限。当前中间平台测试通过不等于最终冻结验收，候选尚未构建。

最新事实与剩余门禁见
[接续记录](../../remaining-tickets-2026-10-26/ACTIVE-HANDOFF.md)和
[验收草稿](../../remaining-tickets-2026-10-26/mc05-native/acceptance-summary-draft.md)。
本票仍 claimed，复选框和后继依赖不变；未运行真实模型、安装 App 或真实 ATS。

### 2026-10-27 R5 实际停止通过与最终回归启动

R5 已构建并完成独立源码及 Python pin 审查。实际 owner-read 和原 8 秒在途停止
分别通过，stop 位于实际 handler 运行期间，排空后保留同一 mutation 的 unknown；
原 Page、Submit=0、自动清理与前后源码不变均有原始证据。历史确切 alias 的真实
codesign 检查另作为 OS/文件层验证，不冒充 Rust alias 分支或 transport 验收。

完整离线回归现已按 1,799 项冻结清单启动，实际收集 7,845 个测试并核对精确分区。
随后在同一冻结版本运行受影响浏览器与最终八个实际原生场景；unknown 的缓存、
fresh ref、新 ID 拒绝须逐阶段核对，不能仅据 pytest 通过闭合。见
[R5 证据预检查](../../remaining-tickets-2026-10-26/mc05-native/r5-native/final-evidence-review-precheck.md)。
本票仍 claimed，后继依赖保留；完整门禁完成前不填写最终接受结论。

### 2026-10-27 Resolution：MC05 原 T06 分层验收完成（Europe/Zurich）

按父任务授权，关闭受控 agent、合成原 Page、实际 native 工具层的原五项条件。
[最终验收](../../remaining-tickets-2026-10-26/mc05-native/final-acceptance-r5.md)与
[独立审查](../../remaining-tickets-2026-10-26/mc05-native/r5-native/final-acceptance-evidence-review.md)
绑定同一1799项快照：完整 offline 7843 passed/2显式benchmark skips，affected browser
224 passed/5显式native opt-in skips，实际 native 8 passed/0 skipped。reviewer核对
exact JUnit、121证据hash、当前1799项及1118 native，均无缺失或变化。
JSON及当前文档/目标核验、同一Page单控制者、unknown/cache/fresh-ref/new-ID不重放、
在途撤权排空、保存失败原占用、人工内容与Submit守卫均有对应证据。默认安装driver未替换。

原失败与中断、原始manifest生成时pending字样保留；两份旧静态日志同名覆盖且原字节
未恢复的例外已披露，当前独立命名静态检查通过。保存失败的新unknown不冒充已写入
故障store；public refusal不伪造内部guard stage；post-stop拒绝code未另存。
未执行实际模型/签名安装App/真实ATS验收，不关闭T07/T08、完整M4或最终AC。
本票关闭只释放MC06硬前置；最终Submit仍手动。上述早期Comments为历史截点。
