# 28：配置冻结、锁内复验与只读旧进程握手 — 2026-10-20

本轮支持原票，不改变 Status、Assignee、依赖或验收勾选。未启动原生 App、浏览器、
模型或真实申请，未读取职业材料，未改签名、TCC 或生产历史兼容白名单。

## 已修复的实际缺陷

`write_configuration()` 未冻结 `WorkerService.spawn()` 使用的 CDP 端口、fixture origin、
合成工作区及包启动身份。检查之后改变这些字段，真实 loopback resume POST 原先仍返回
200。四项 [RED](red-launch-configuration.log) 均在预期拒绝断言处失败。

现在同一既有配置 witness 绑定这些字段；包启动身份使用深拷贝，因此字典原地修改也会
在持锁复验或后续 lease heartbeat 停止。拒绝发生在保存/批准/claim/spawn 前。
六项 [GREEN](green-launch-configuration.log) 包括合法当前运行的正例及 lease 撤销反例。
不增加配置状态库或版本号宽容规则。

## 锁内原生证明反例

现有 deny-only 合成证明 seam 新增 `phase=write-locked`。普通 snapshot 不改变证明。
固定 `write_locked_snapshot` 仅从写门禁的持锁快照 helper 调用；helper 首先验证既有
application write lock 的 descriptor 已持有，再读取证明。允许的控制文件字段不变。

触发时只否定已有证明，并向既有 stdout 输出固定 event/phase/token/fault；不增加
HTTP 故障控制口，不生成权限正例。真实 loopback POST 回归独立断言锁确实持有、
只有一次锁内读取、409、业务字节不变且不 spawn。
[56 项聚焦回归通过](locked-native-fault.log)。原 after-first-read 的历史证据保留。

## 旧 worker 的只读握手工程

`controller-handoff-inspection/v1` 使用现有 `run.json` 与 commands 通道：

1. 新控制端显式 `inspect-handoff`，仅向有该 capability 且新鲜、paused 的所属原页发
   nonce challenge；无 capability/无页/未知 PID 代次/已有命令立即停止。
2. 原 worker 在既有 application lock 与原 worker lock 内回答。绑定原 run、worker
   loaded/source 身份、单岗位上下文、Page、附件摘要、intent、答案引用、nonce 和
   macOS kernel PID/UID/微秒出生代次/执行文件；确认原 lock inode 仍被持有。
3. 显式 `verify-handoff` 在既有 application lock 内重新核对完整 binding、10 秒时效、
   当前 kernel 代次、原锁 inode/持有及附件字节。结果只写诊断回执。

**回执始终为 `execution_authority=false`。不设置 process、不构造仿 Popen 对象，
不改为 managed、不准入 resume、不清理或消费 intent、不补生产 VERIFIED_WORKERS。**
实际执行接管及精确跨版本合法继续仍是未完成工程，不能转成用户确认事项或以只读
握手宣称整票完成。

Darwin 采样布局来自本机 SDK `sys/proc_info.h` 的 `proc_bsdinfo` 与
`PROC_PIDTBSDINFO=3`。其他平台与任何采样失败保留 unknown。测试只对实际当前
pytest 进程读取 kernel 身份；Page 与权限/包证明均为合成替身，不启动浏览器。
新增回归覆盖 nonce、OS 代次、source、Page、intent、锁释放/替换和附件变化。

## 主 App 后续验收入口

[run_native_matrix.py](run_native_matrix.py) 基于已有 `deny_native_post.py/native_api.py`
收敛为显式 `deny` 或 `handoff` 模式。它只使用已打开的唯一主 App 合成 session，要求
明确隔离 root 与 `--manifest disk-manifest-sha256:...`，绑定磁盘/实际 readiness 清单。

- `deny` 要求尚无 worker 的 materials_ready 任务；逐项注入缺权/nonce/责任链/过期/
  unknown 的锁内否定，实际 POST 409，独立回读业务字节并从 stdout 核对唯一 token
  的锁内事件。结束移除控制文件。
- `handoff` 要求现存 paused Page；仅请求/核验只读握手，保留原 run/Page/File/intent/
  答案边界，不发 resume 或 Submit。支持原 worker 的 capability 必须来自实际新入口。

脚本本轮未执行。主 App 包安装、固定签名、新鲜实际权限、候选清单及完整离线检查由
父会话统一进行；不能把本轮源码注入测试称作原生/TCC/跨版本执行验收。

源码已冻结。十个受影响源码/测试的 Ruff check/format 和 git diff --check 通过。
最终稳定组合日志为 [frozen-focused.log](frozen-focused.log)。较早组合期间源码并发
变化导致正例门禁拒绝；原日志全部保留，不放宽指纹或门禁来绕过它。

## 独立复核后的修正

构建的 action-free import audit 发现新增模块顶层 `import ctypes` 会触发 dlopen。
已将导入移到明确实际采样入口；没有放宽构建 audit。两种角色导入顺序的隔离 probe
均先 RED，再 GREEN；当前 kernel PID 采样也通过。日志为
[native-import-audit-red.log](native-import-audit-red.log) 与
[native-import-audit-green.log](native-import-audit-green.log)。

独立 Spec 复核另发现原实现只核对 Page handle/id/context，不能排除同页导航或 Cua
owner/transport 故障。三个反例先以 captured 假阳性失败，然后最小修复：在 clone 的
诊断 job 上复用既有 `observe_owned_page`，明确核对岗位 URL、实际 owner/transport，
捕获 URL、frame/loader、DOM、File 元数据和截图。失败只记录明确 reason，不改原 job。
对应 [RED](handoff-capture-red.log) 与 [18 项 GREEN](handoff-capture-green.log) 保留。

`verify-handoff` 的结果现为 `validated_capture_receipt`，scope 明确为已经捕获的页面
快照；`current_page_verified=false`、`execution_authority=false`。它核验短时效捕获
回执及 OS/锁/本地附件绑定，不声称捕获之后实际页面仍未改变。

原生 driver 同步使用 24 的实际 observe-page 在握手前后各捕获一次，比较文档、DOM、
owner 与 File 元数据。结果明确 `file_object_bytes_compared=false`；本地附件摘要
不能代替浏览器实际 File 对象字节证明。driver 仍未执行。

复核修正后的稳定组合结果以 [post-review-frozen-focused.log](post-review-frozen-focused.log)
为准，先前 181 项是修正前的有效历史结果，不冒充本次完整新组合验证。
