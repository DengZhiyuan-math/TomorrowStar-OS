# 在安装版运行完整合成准备流程

Type: task
Label: wayfinder:task
Status: closed
Triage: done
Closure reason: completed
Completion: installed-synthetic-acceptance-passed
Policy version: preparation-policy/v1.0
Priority: P1
Interaction: AFK
Assignee: 01a14a95/root
Created: 2026-10-17
Updated: 2026-10-18
Parent: [交付 Gmail 岗位筛选与专用简历稳定版](../map.md)
Publication order: 11
Blocked by: [冻结候选版本并验证整条准备链](13-offline-batch-regression.md)

**What to build:** 用户在实际安装候选中完成推荐更新、分级、PDF审阅和重开恢复的合成流程。

## Acceptance criteria

- [x] 回读磁盘包、实际加载版本和配置，证明使用了本次候选。
- [x] 隔离运行更新、分级、生成、导出、审阅、退出与恢复；冷启动与renderer证据分别记录。
- [x] 保留回退方式及旧私人资料、原页面、附件和暂停任务。
- [x] 打包成功、源码通过与安装版实际行为分别记录，安装通过不代表真实材料质量接受。

## Standing boundaries

复用已有能力和已完成研究；每票形成可独立演示或验证的用户行为。先做本票必要的最小整理，不引入推测性框架。个人材料留私有；保持真实申请暂停、未知动作停止及人工最终Submit。规划发布不授权真实邮箱／模型／ATS执行。任何代码变更均需本切片的有效验证。

## Ownership

沿用票头Status和Assignee；本次仅发布，未领取或执行。先核对frontier并写入唯一领取人，再做工作；多人共享模块时协调，不回退其他人的改动。HITL必须由用户实际参与，不能由代理代答。

## Comments

### 2026-10-18 — Resolution: installed synthetic preparation journey accepted

新增严格显式的 `--synthetic-preparation ABS_ROOT`，与其他模式／配置互斥，固定合成邮箱、完整JD和CLI模型替身；环境、资料、信息库和准备运行均在独立合成目录，填写worker全部关闭，沿用实际PDF renderer。替身Python以 `-I -B` 运行，回归确认不执行注入的sitecustomize或写入字节码。普通和旧synthetic-flow入口行为保留。

最终238文件源码候选为 `preparation-candidate-7b299a861113762f4ba5ca5317cea76a35f89360467e90ff572e11c27dcbff1b`。从该快照构建后，以独立身份安装到 `/Users/zhdeng/Applications/TomorrowStar Preparation Verified.app`；未替换原TomorrowStar或Page Recovery。包内75引擎文件、磁盘签名、主进程／后端绝对路径及合成参数均回读，运行代码 `ebda9de4ce5c67b0e719dd153fc844327580e09bdbab503aef9fcfdd69c83e74` 与安装字节重新计算一致。4个实际服务的静态资源与包内相同。[规范验证记录](../../installed-preparation-2026-10-17/verification.json)分别绑定源码、包、实际加载与配置。

通过实际安装窗口完成：更新推荐及完整JD、选一岗保存暂停批次、明确开始分析及英文草稿、查看匹配分／资格／进度／理由（无A/B等级）、暂停和逐来源审阅、明确继续实际导出A4 PDF、窗口预览和确认具体文件。批次停在 `waiting_application_record`，没有下一岗、填写或投递。[原生旅程与截图](../../installed-preparation-2026-10-17/README.md)保留操作证据；[实际renderer与逐页检查](../../installed-preparation-2026-10-17/final-run/pdf/renderer-verification.json)核对一页A4、全文、边界、视觉及采用PDF哈希。当前模板对最小合成资料保留空Education标题，未更改模板。

首次安装旅程发现退出／重开会重复记录已确认终点事件和epoch；原失败保留。最小幂等修复同时覆盖 `waiting_application_record` 和 `needs_recheck`，状态与原因一致时不再转换，控制漂移仍纠正。4种生命周期回归和相关50项通过，随后重新冻结、构建、安装并重跑完整原生链。[最终冷启动](../../installed-preparation-2026-10-17/final-run/cold-start-verification.json)证明服务会话改变，整个任务、批次、61个保存文件均完全一致，epoch保持4、终点事件仅1条，草稿及具体PDF有效。再次退出后无候选进程，端口关闭，保存字节不变。

- 完整默认离线 **2516 passed / 221 deselected**；本地合成浏览器 **41 passed / 72 deselected**；原生入口新旧80项、独立终点4项通过。Ruff、258文件格式、JS语法与diff检查通过；这些结果均在最终源码冻结后执行。
- [私人状态保全](../../installed-preparation-2026-10-17/final-run/preservation-after.json)：原两App字节及九项私人运行目录元数据不变；未读取私人正文、原页面或附件，未恢复任何旧任务。候选验收结束后已退出。回退只需退出独立候选并使用原App，不迁移私人数据。
- 首次构建未带 `-B` 导致首个快照多出缓存，严格清单正确拒绝；[事件记录](../../installed-preparation-2026-10-17/snapshot-build-cache-incident.json)保留原失败。最终构建使用 `-I -B`，构建及运行后严格清单核验通过；签名前后程序哈希分别记录，不混作实际加载哈希。
- 独立最终审查确认候选、18项证据哈希、安装／加载／PDF、冷恢复与保全一致，无剩余阻断。

**关闭范围：** 安装版合成流程及其必要修复完成，不代表真实邮箱／真实模型可用性、真实岗位／简历质量或用户接受；不关闭历史原生故障调查。[真实推荐复核](15-real-preparation-pilot.md)保持open、needs-info、Assignee none，须用户参与。本轮真实邮箱／模型／岗位源调用、上传及Submit均为0，真实申请继续暂停；未提交Git或写远端。

### 2026-10-17 — Implementation claim under policy v1.0

用户授权执行本票；前置「冻结候选版本并验证整条准备链」已closed，本票由 `01a14a95/root` 领取。先核对冻结候选，再以独立身份、独立合成运行目录验证实际安装候选的冷启动、完整准备流程、renderer及退出恢复。

保留现有安装版、进程、原页面、附件和暂停任务，留回退方法。只使用合成邮箱／资料／岗位和模型替身；不读取私人材料或真实邮箱、不调用真实模型／岗位／ATS、不修改邮箱、不上传或Submit、不恢复真实申请，不提交Git或写远端。安装与合成接受不代表真实材料质量接受。

### 2026-10-17 — Approved ticket migration

用户已批准23张拆分及迁移。此票沿用原路径和身份，采用批准后的纵向交付契约；此前内容保存在不可覆盖的历史快照中，不丢失原问题、依赖、评论或验收记录。

- [批准的逐票草案](../../tomorrowstar-ticket-consolidation-2026-10-17/drafts/11-installed-preparation.md)。
- [迁移前完整原文](../../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/gmail-resume-preparation-2026-10-17/issues/14-installed-preparation-acceptance.md)。
- [当前正式导航与全部承接关系](../../tomorrowstar-ticket-consolidation-2026-10-17/README.md)。

本次迁移不是实现完成或用户产品接受；真实申请继续暂停。
